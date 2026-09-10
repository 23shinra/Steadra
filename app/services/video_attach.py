"""Extract frames (and optional audio transcript) from chat video uploads."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import current_app

MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_DURATION_SEC = 240


class VideoAttachError(ValueError):
    pass


def _run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _probe_duration(path: Path) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        timeout=20,
    )
    if result.returncode != 0:
        raise VideoAttachError("Не удалось прочитать видео.")
    try:
        data = json.loads(result.stdout.decode("utf-8", errors="replace") or "{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VideoAttachError("Не удалось определить длительность видео.") from exc
    if duration <= 0:
        raise VideoAttachError("Видео пустое или повреждено.")
    return duration


def _frame_plan(duration: float) -> list[float]:
    """Even timeline samples — denser on short clips, richer on longer ones."""
    if duration <= 12:
        count = 8
    elif duration <= 45:
        count = 10
    elif duration <= 120:
        count = 12
    else:
        count = 14
    # Keep a little head/tail margin so we don't only get black frames / fade-outs.
    pad = min(max(duration * 0.04, 0.15), 1.2)
    start = pad
    end = max(duration - pad, start + 0.25)
    if count == 1:
        return [start]
    return [start + (end - start) * (i / (count - 1)) for i in range(count)]


def _extract_frames(path: Path, duration: float, work: Path) -> list[dict]:
    frames: list[dict] = []
    for i, t in enumerate(_frame_plan(duration)):
        out = work / f"frame_{i:02d}.jpg"
        result = _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-vf",
                "scale='min(1536,iw)':-2",
                str(out),
            ],
            timeout=35,
        )
        if result.returncode != 0 or not out.exists() or out.stat().st_size < 200:
            continue
        frames.append(
            {
                "t": round(t, 2),
                "b64": base64.b64encode(out.read_bytes()).decode("ascii"),
            }
        )
    if len(frames) < 3:
        raise VideoAttachError("Мало читаемых кадров — попробуй другое видео или экспорт в mp4.")
    return frames


def _extract_transcript(path: Path, work: Path, duration: float) -> dict | None:
    """Whisper transcription with timestamps when possible."""
    audio = work / "audio.mp3"
    result = _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(audio),
        ],
        timeout=90,
    )
    if result.returncode != 0 or not audio.exists() or audio.stat().st_size < 800:
        return None
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=120.0)
        with audio.open("rb") as fh:
            raw = client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
                response_format="verbose_json",
                # Auto language; prompt biases toward startup/pitch vocabulary.
                prompt="Стартап, питч, продукт, пользователь, метрики, MVP.",
            )
        text = (getattr(raw, "text", None) or "").strip()
        segments = []
        for seg in getattr(raw, "segments", None) or []:
            if isinstance(seg, dict):
                piece = (seg.get("text") or "").strip()
                start = seg.get("start")
                end = seg.get("end")
            else:
                piece = (getattr(seg, "text", None) or "").strip()
                start = getattr(seg, "start", None)
                end = getattr(seg, "end", None)
            if not piece:
                continue
            try:
                start_f = float(start) if start is not None else None
                end_f = float(end) if end is not None else None
            except (TypeError, ValueError):
                start_f = end_f = None
            if start_f is not None and end_f is not None:
                segments.append(f"[{start_f:.0f}–{end_f:.0f}с] {piece}")
            else:
                segments.append(piece)
        timed = "\n".join(segments[:40]).strip()
        full = timed or text
        if not full:
            return None
        return {
            "text": full[:6000],
            "has_speech": True,
            "duration": round(duration, 1),
        }
    except Exception:
        current_app.logger.exception("video whisper failed")
        return None


def prepare_video_for_ai(data: bytes, filename: str = "") -> dict:
    if not data:
        raise VideoAttachError("Пустой файл.")
    if len(data) > MAX_VIDEO_BYTES:
        raise VideoAttachError("Видео больше 50 МБ — сожми или обрежь.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VideoAttachError("На сервере нет ffmpeg — видео пока недоступно.")

    suffix = Path(filename or "clip.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".webm", ".m4v", ".avi"}:
        suffix = ".mp4"

    with tempfile.TemporaryDirectory(prefix="chatvid_") as tmp:
        work = Path(tmp)
        path = work / f"input{suffix}"
        path.write_bytes(data)
        duration = _probe_duration(path)
        if duration > MAX_DURATION_SEC:
            raise VideoAttachError("Видео длиннее 4 минут — пришли ключевой фрагмент.")
        frames = _extract_frames(path, duration, work)
        transcript = _extract_transcript(path, work, duration)
        return {
            "frames": frames,
            "frames_b64": [f["b64"] for f in frames],  # backward-compatible
            "transcript": (transcript or {}).get("text"),
            "has_speech": bool((transcript or {}).get("has_speech")),
            "duration": round(duration, 1),
            "frame_count": len(frames),
            "filename": (filename or "")[:120],
        }

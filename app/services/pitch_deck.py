"""Extract slide text from founder pitch files (pptx / pdf / pasted text)."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET
from typing import Any

from werkzeug.datastructures import FileStorage

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
MAX_SLIDES = 18
MAX_SLIDE_CHARS = 700
ALLOWED_EXT = {".pptx", ".pdf", ".txt"}


class PitchDeckError(ValueError):
    pass


def _clip(text: str, limit: int = MAX_SLIDE_CHARS) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def normalize_slides(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slides = []
    for i, item in enumerate(raw[:MAX_SLIDES], 1):
        title = _clip(str(item.get("title") or f"Слайд {i}"), 80)
        body = _clip(str(item.get("text") or ""), MAX_SLIDE_CHARS)
        if not body and not item.get("title"):
            continue
        slides.append({"num": i, "title": title, "text": body or title})
    return slides


def extract_pptx(data: bytes) -> list[dict[str, Any]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PitchDeckError("Файл PPTX повреждён или это не презентация.") from exc
    names = [
        n
        for n in zf.namelist()
        if n.startswith("ppt/slides/slide") and n.endswith(".xml") and "/_rels/" not in n
    ]

    def slide_num(name: str) -> int:
        m = re.search(r"slide(\d+)\.xml$", name)
        return int(m.group(1)) if m else 0

    names.sort(key=slide_num)
    if not names:
        raise PitchDeckError("В PPTX нет слайдов с текстом.")
    slides = []
    for name in names:
        root = ET.fromstring(zf.read(name))
        parts = [node.text.strip() for node in root.iter(f"{A_NS}t") if node.text and node.text.strip()]
        title = parts[0] if parts else f"Слайд {slide_num(name)}"
        slides.append({"title": title, "text": "\n".join(parts)})
    return normalize_slides(slides)


def extract_pdf(data: bytes) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PitchDeckError("Разбор PDF недоступен на сервере.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise PitchDeckError("Не удалось прочитать PDF.") from exc
    if not reader.pages:
        raise PitchDeckError("PDF пустой.")
    slides = []
    for i, page in enumerate(reader.pages[:MAX_SLIDES], 1):
        text = (page.extract_text() or "").strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = lines[0] if lines else f"Слайд {i}"
        slides.append({"title": title, "text": text or title})
    return normalize_slides(slides)


def extract_pasted_text(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        raise PitchDeckError("Пустой текст питча.")
    chunks = re.split(r"(?im)^\s*(?:slide|слайд)\s*\d+\s*[:.\-]?\s*", text)
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
        if len(blocks) >= 3:
            chunks = blocks
        else:
            chunks = [text]
    slides = []
    for i, chunk in enumerate(chunks[:MAX_SLIDES], 1):
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        title = lines[0] if lines else f"Слайд {i}"
        slides.append({"title": title, "text": chunk})
    return normalize_slides(slides)


def extract_from_upload(upload: FileStorage) -> list[dict[str, Any]]:
    filename = (upload.filename or "").strip()
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext == ".ppt":
        raise PitchDeckError("Старый .ppt не читаем — сохрани как .pptx или PDF.")
    if ext not in ALLOWED_EXT:
        raise PitchDeckError("Нужен файл .pptx, .pdf или .txt.")
    data = upload.read()
    upload.stream.seek(0)
    if not data:
        raise PitchDeckError("Файл пустой.")
    if len(data) > 8 * 1024 * 1024:
        raise PitchDeckError("Файл больше 8 МБ.")
    if ext == ".pptx":
        return extract_pptx(data)
    if ext == ".pdf":
        return extract_pdf(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    return extract_pasted_text(text)


def slides_to_prompt(slides: list[dict[str, Any]]) -> str:
    lines = []
    for s in slides:
        lines.append(f"### Слайд {s['num']}: {s['title']}\n{s['text']}")
    return "\n\n".join(lines)

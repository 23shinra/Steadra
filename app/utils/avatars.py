from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def avatar_dir() -> Path:
    path = Path(current_app.root_path).parent / "var" / "uploads" / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def avatar_public_url(user_id: int) -> str:
    return f"/uploads/avatars/{user_id}"


def find_avatar_file(user_id: int) -> Path | None:
    directory = avatar_dir()
    for ext in ALLOWED_EXTENSIONS:
        candidate = directory / f"{user_id}{ext}"
        if candidate.is_file():
            return candidate
    return None


def delete_avatar_files(user_id: int) -> None:
    directory = avatar_dir()
    for ext in ALLOWED_EXTENSIONS:
        candidate = directory / f"{user_id}{ext}"
        if candidate.exists():
            candidate.unlink()


def save_avatar_file(user_id: int, upload: FileStorage) -> str:
    if not upload or not upload.filename:
        raise ValueError("Файл не выбран")

    filename = secure_filename(upload.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Допустимы JPG, PNG или WEBP")

    upload.stream.seek(0, 2)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size > MAX_AVATAR_BYTES:
        raise ValueError("Файл больше 2 МБ")

    delete_avatar_files(user_id)
    target = avatar_dir() / f"{user_id}{ext}"
    upload.save(target)
    return avatar_public_url(user_id)

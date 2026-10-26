"""Upload validation. Uploaded files are untrusted: never written to disk, never executed."""

from dataclasses import dataclass
from pathlib import PurePath

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    text: str
    size_bytes: int
    line_count: int


def sanitize_filename(name: str | None) -> str:
    base = PurePath((name or "upload.log").replace("\\", "/")).name
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ")[:120].strip()
    return cleaned or "upload.log"


def validate_upload(filename: str | None, data: bytes, settings: Settings) -> ValidatedUpload:
    safe_name = sanitize_filename(filename)
    ext = PurePath(safe_name).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise AppError(
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(settings.allowed_extensions)}",
            status_code=415,
        )
    size = len(data)
    if size == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.", status_code=400)
    if size > settings.max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.max_upload_mb:g} MB limit.",
            status_code=413,
            details={"max_bytes": settings.max_upload_bytes, "size_bytes": size},
        )
    if b"\x00" in data[:65536]:
        raise AppError("BINARY_CONTENT", "The file looks binary. Upload plain-text logs.", status_code=400)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(
            "INVALID_ENCODING",
            "The file is not valid UTF-8 text.",
            status_code=400,
            details={"byte_offset": exc.start},
        ) from exc
    if not text.strip():
        raise AppError("NO_LOG_CONTENT", "The file contains only whitespace.", status_code=400)
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
    if line_count > settings.max_lines:
        raise AppError(
            "TOO_MANY_LINES",
            f"File has {line_count} lines; the limit is {settings.max_lines}.",
            status_code=413,
        )
    return ValidatedUpload(filename=safe_name, text=text, size_bytes=size, line_count=line_count)

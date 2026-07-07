"""Media classification and target path helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEDIA_DIRS = {
    "photos",
    "videos",
    "audio",
    "voice",
    "video_notes",
    "documents",
}


def clean_filename(value: str, max_length: int = 90) -> str:
    """Return a filesystem-safe filename."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip().strip(".")
    if not value:
        return "media"
    return value[:max_length].rstrip(" .")


def message_datetime_utc(message: Any) -> datetime | None:
    """Return a message datetime normalized to UTC."""
    if not message.date:
        return None
    if message.date.tzinfo is None:
        return message.date.replace(tzinfo=timezone.utc)
    return message.date.astimezone(timezone.utc)


def media_kind(message: Any) -> str | None:
    """Classify supported Telegram message media into output directories."""
    if message.sticker:
        return None
    if getattr(message, "photo", None):
        return "photos"
    if getattr(message, "video_note", None):
        return "video_notes"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "video", None):
        return "videos"

    file_info = message.file
    mime_type = getattr(file_info, "mime_type", "") if file_info else ""
    if mime_type.startswith("image/"):
        return "photos"
    if mime_type.startswith("video/"):
        return "videos"
    if mime_type.startswith("audio/"):
        return "audio"
    if getattr(message, "document", None):
        return "documents"

    return None


def media_extension(message: Any, kind: str) -> str:
    """Return the best available extension for a Telegram media message."""
    file_info = message.file
    original_name = getattr(file_info, "name", None) if file_info else None
    if original_name:
        suffix = Path(original_name).suffix
        if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix):
            return suffix.lower()

    ext = getattr(file_info, "ext", None) if file_info else None
    if ext and re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext):
        return ext.lower()

    fallback = {
        "photos": ".jpg",
        "videos": ".mp4",
        "audio": ".mp3",
        "voice": ".ogg",
        "video_notes": ".mp4",
        "documents": ".bin",
    }
    return fallback.get(kind, ".bin")


def target_path_for_message(
    message: Any,
    output_dir: Path,
    kind: str,
    flat_output: bool = False,
) -> Path:
    """Build a target path for a Telegram media message."""
    file_info = message.file
    original_name = getattr(file_info, "name", None) if file_info else None
    target_dir = output_dir if flat_output else output_dir / kind

    if original_name:
        return target_dir / clean_filename(original_name, max_length=180)

    stem = kind.rstrip("s")
    timestamp = message.date.strftime("%Y%m%d_%H%M%S") if message.date else "no_date"
    ext = media_extension(message, kind)
    filename = f"{timestamp}_msg{message.id}_{stem}{ext}"
    return target_dir / filename


def temp_path_for(target_path: Path) -> Path:
    """Return an atomic-download temporary path next to the final target."""
    return target_path.with_name(f"{target_path.name}.part")

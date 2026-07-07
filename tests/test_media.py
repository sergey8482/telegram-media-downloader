"""Tests for Telegram media classification helpers."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from tg_media_dl.media import clean_filename, media_kind


@dataclass
class FileInfo:
    """Minimal fake Telethon file object."""

    mime_type: str = ""
    name: str | None = None
    ext: str | None = None
    size: int | None = None


class FakeMessage:
    """Minimal fake Telethon message object for media tests."""

    def __init__(self, **kwargs: object) -> None:
        """Set Telethon-like media attributes."""
        self.sticker = kwargs.get("sticker")
        self.photo = kwargs.get("photo")
        self.video_note = kwargs.get("video_note")
        self.voice = kwargs.get("voice")
        self.audio = kwargs.get("audio")
        self.video = kwargs.get("video")
        self.document = kwargs.get("document")
        self.file = kwargs.get("file")


class MediaTests(unittest.TestCase):
    """Media helper tests."""

    def test_clean_filename_replaces_windows_invalid_characters(self) -> None:
        """Invalid Windows filename characters should be replaced."""
        self.assertEqual(clean_filename('a<b>c:"d"/e\\f|g?h*.jpg'), "a_b_c__d__e_f_g_h_.jpg")

    def test_media_kind_detects_image_document_as_photo(self) -> None:
        """Image documents should be routed to the photos folder."""
        msg = FakeMessage(document=True, file=FileInfo(mime_type="image/jpeg"))

        self.assertEqual(media_kind(msg), "photos")

    def test_media_kind_detects_voice_before_audio(self) -> None:
        """Voice notes should not be grouped with generic audio."""
        msg = FakeMessage(voice=True, audio=True, file=FileInfo(mime_type="audio/ogg"))

        self.assertEqual(media_kind(msg), "voice")

    def test_media_kind_routes_generic_document(self) -> None:
        """Unknown documents should be routed to documents."""
        msg = FakeMessage(document=True, file=FileInfo(mime_type="application/pdf"))

        self.assertEqual(media_kind(msg), "documents")


if __name__ == "__main__":
    unittest.main()

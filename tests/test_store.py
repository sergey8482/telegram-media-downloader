"""Tests for SQLite download store behavior."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tg_media_dl.store import DownloadStore


class StoreTests(unittest.TestCase):
    """DownloadStore tests."""

    def test_downloads_are_scoped_by_chat_id(self) -> None:
        """The same message_id in different chats must not collide."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "downloads.db"
            with DownloadStore(db_path) as store:
                store.record_download(
                    chat_id=1,
                    message_id=10,
                    file_path=Path("a.jpg"),
                    file_size=100,
                )
                store.record_download(
                    chat_id=2,
                    message_id=10,
                    file_path=Path("b.jpg"),
                    file_size=200,
                )

                self.assertTrue(store.is_downloaded(1, 10))
                self.assertTrue(store.is_downloaded(2, 10))
                self.assertFalse(store.is_downloaded(1, 11))
                self.assertEqual(store.last_message_id(1), 10)
                self.assertEqual(store.last_message_id(2), 10)

    def test_old_single_message_id_primary_key_schema_is_migrated(self) -> None:
        """Older databases should migrate to a composite chat/message key."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "downloads.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE downloaded_media (
                    message_id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    downloaded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO downloaded_media
                    (message_id, chat_id, file_path, file_size, downloaded_at)
                VALUES (42, 7, 'old.jpg', 123, '2026-01-01T00:00:00+00:00')
                """
            )
            connection.commit()
            connection.close()

            with DownloadStore(db_path) as store:
                self.assertTrue(store.is_downloaded(7, 42))
                store.record_download(
                    chat_id=8,
                    message_id=42,
                    file_path=Path("new.jpg"),
                    file_size=456,
                )
                self.assertTrue(store.is_downloaded(8, 42))


if __name__ == "__main__":
    unittest.main()

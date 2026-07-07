"""SQLite persistence for incremental Telegram media downloads."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class DownloadStore(AbstractContextManager["DownloadStore"]):
    """Small SQLite wrapper for downloaded media bookkeeping."""

    def __init__(self, db_path: Path) -> None:
        """Create a store bound to a SQLite database path."""
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "DownloadStore":
        """Open the SQLite connection and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS downloaded_media (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                downloaded_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the SQLite connection."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _conn(self) -> sqlite3.Connection:
        """Return an opened SQLite connection."""
        if self.connection is None:
            raise RuntimeError("DownloadStore is not open.")
        return self.connection

    def is_downloaded(self, message_id: int) -> bool:
        """Return whether a message id was already downloaded."""
        row = self._conn().execute(
            "SELECT 1 FROM downloaded_media WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row is not None

    def last_message_id(self) -> int | None:
        """Return the highest downloaded message id, if any."""
        row = self._conn().execute(
            "SELECT MAX(message_id) FROM downloaded_media"
        ).fetchone()
        value = row[0] if row else None
        return int(value) if value is not None else None

    def record_download(
        self,
        *,
        message_id: int,
        chat_id: int,
        file_path: Path,
        file_size: int,
    ) -> None:
        """Insert or replace a downloaded media record."""
        self._conn().execute(
            """
            INSERT OR REPLACE INTO downloaded_media
                (message_id, chat_id, file_path, file_size, downloaded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message_id,
                chat_id,
                str(file_path),
                file_size,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn().commit()

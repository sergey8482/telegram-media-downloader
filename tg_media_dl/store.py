"""SQLite persistence for incremental Telegram media downloads."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path


class DownloadStore(AbstractContextManager["DownloadStore"]):
    """Small SQLite wrapper for downloaded media bookkeeping."""

    def __init__(self, db_path: Path) -> None:
        """Create a store bound to a SQLite database path."""
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> DownloadStore:
        """Open the SQLite connection and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self._ensure_schema()
        return self

    def _ensure_schema(self) -> None:
        """Create or migrate the downloaded media table."""
        conn = self._conn()
        columns = conn.execute("PRAGMA table_info(downloaded_media)").fetchall()
        if columns:
            primary_key_columns = [row[1] for row in columns if row[5] > 0]
            if primary_key_columns == ["message_id"]:
                self._migrate_message_id_primary_key()
                return

        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloaded_media (
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                downloaded_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        conn.commit()

    def _migrate_message_id_primary_key(self) -> None:
        """Migrate older databases that used message_id as the only primary key."""
        conn = self._conn()
        conn.execute("ALTER TABLE downloaded_media RENAME TO downloaded_media_old")
        conn.execute(
            """
            CREATE TABLE downloaded_media (
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                downloaded_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO downloaded_media
                (message_id, chat_id, file_path, file_size, downloaded_at)
            SELECT message_id, chat_id, file_path, file_size, downloaded_at
            FROM downloaded_media_old
            """
        )
        conn.execute("DROP TABLE downloaded_media_old")
        conn.commit()

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

    def is_downloaded(self, chat_id: int, message_id: int) -> bool:
        """Return whether a message id was already downloaded."""
        row = self._conn().execute(
            """
            SELECT 1 FROM downloaded_media
            WHERE chat_id = ? AND message_id = ?
            """,
            (chat_id, message_id),
        ).fetchone()
        return row is not None

    def last_message_id(self, chat_id: int) -> int | None:
        """Return the highest downloaded message id for one chat, if any."""
        row = self._conn().execute(
            "SELECT MAX(message_id) FROM downloaded_media WHERE chat_id = ?",
            (chat_id,),
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

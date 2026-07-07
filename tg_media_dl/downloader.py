"""Core Telegram media download workflow."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from tqdm import tqdm

from .auth import start_client
from .config import AppConfig, local_timezone
from .media import (
    media_kind,
    message_datetime_utc,
    target_path_for_message,
    temp_path_for,
)
from .store import DownloadStore

LOGGER = logging.getLogger(__name__)


class DownloadStats:
    """Mutable counters for a downloader run."""

    def __init__(self) -> None:
        """Initialize all counters to zero."""
        self.scanned = 0
        self.matched = 0
        self.downloaded = 0
        self.skipped = 0
        self.failed = 0


async def create_client(config: AppConfig) -> TelegramClient:
    """Create and authenticate a Telegram client from configuration."""
    config.session_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(
        str(config.session_dir / config.session_name),
        config.api_id,
        config.api_hash,
        proxy=config.proxy,
    )
    await start_client(
        client,
        phone=config.phone,
        login_code=config.login_code,
        login_password=config.login_password,
        force_sms=config.force_sms,
        qr_login=config.qr_login,
        qr_path=config.qr_path,
        qr_timeout=config.qr_timeout,
    )
    return client


async def list_chats(config: AppConfig) -> None:
    """List available Telegram dialogs."""
    client = await create_client(config)
    try:
        LOGGER.info("Available chats:")
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                chat_type = "channel"
            elif dialog.is_group:
                chat_type = "group"
            else:
                chat_type = "user"
            LOGGER.info("- %s [%s] id=%s", dialog.name, chat_type, dialog.id)
    finally:
        await client.disconnect()


async def find_chat(client: TelegramClient, title: str) -> Any:
    """Find a Telegram dialog by title with exact and case-insensitive matching."""
    exact_matches = []
    case_matches = []
    partial_matches = []

    async for dialog in client.iter_dialogs():
        name = dialog.name or ""
        if name == title:
            exact_matches.append(dialog)
        elif name.casefold() == title.casefold():
            case_matches.append(dialog)
        elif title.casefold() in name.casefold() or name.casefold() in title.casefold():
            partial_matches.append(dialog)

    matches = exact_matches or case_matches
    if len(matches) == 1:
        return matches[0].entity

    if len(matches) > 1:
        LOGGER.error('Found several chats named "%s":', title)
        for dialog in matches:
            LOGGER.error("- %s id=%s", dialog.name, dialog.id)
        raise SystemExit("Use --list-chats and adjust --chat to be unique.")

    LOGGER.error('Could not find a chat named "%s".', title)
    if partial_matches:
        LOGGER.error("Similar chats:")
        for dialog in partial_matches[:20]:
            LOGGER.error("- %s id=%s", dialog.name, dialog.id)
    raise SystemExit("Run with --list-chats to see exact chat titles.")


def chat_id_for(chat: Any) -> int:
    """Return a stable integer chat id from a Telegram entity."""
    return int(getattr(chat, "id", 0))


async def atomic_download(
    client: TelegramClient,
    message: Any,
    target_path: Path,
) -> bool:
    """Download one message media atomically into the target path."""
    part_path = temp_path_for(target_path)
    if part_path.exists():
        part_path.unlink()

    target_path.parent.mkdir(parents=True, exist_ok=True)
    progress = tqdm(
        total=getattr(message.file, "size", None),
        unit="B",
        unit_scale=True,
        desc=target_path.name,
        leave=False,
    )

    def on_progress(current: int, total: int) -> None:
        progress.total = total or progress.total
        progress.update(max(0, current - progress.n))

    try:
        saved_path = await client.download_media(
            message,
            file=str(part_path),
            progress_callback=on_progress,
        )
        progress.close()
        if not saved_path or not part_path.exists():
            LOGGER.warning(
                "Telegram did not return a saved path for message %s",
                message.id,
            )
            return False
        os.replace(part_path, target_path)
        return True
    except Exception:
        progress.close()
        if part_path.exists():
            part_path.unlink()
        raise


async def download_with_retries(
    client: TelegramClient,
    message: Any,
    target_path: Path,
) -> bool:
    """Download one media message, waiting and retrying on FloodWaitError."""
    while True:
        try:
            return await atomic_download(client, message, target_path)
        except FloodWaitError as exc:
            wait_seconds = int(exc.seconds) + 1
            LOGGER.warning(
                "Flood wait for %s seconds; retrying message %s",
                wait_seconds,
                message.id,
            )
            await asyncio.sleep(wait_seconds)


async def download_one(
    *,
    client: TelegramClient,
    message: Any,
    chat_id: int,
    config: AppConfig,
    store: DownloadStore,
    semaphore: asyncio.Semaphore,
    stats: DownloadStats,
) -> None:
    """Download a single media message with resilience and bookkeeping."""
    async with semaphore:
        kind = media_kind(message)
        if not kind:
            return

        target_path = target_path_for_message(
            message,
            config.output_dir,
            kind,
            config.flat_output,
        )
        if store.is_downloaded(message.id) and not config.overwrite:
            stats.skipped += 1
            LOGGER.info("Skip recorded message %s: %s", message.id, target_path)
            return
        if target_path.exists() and not config.overwrite:
            stats.skipped += 1
            LOGGER.info("Skip existing: %s", target_path)
            if not store.is_downloaded(message.id):
                store.record_download(
                    message_id=message.id,
                    chat_id=chat_id,
                    file_path=target_path,
                    file_size=target_path.stat().st_size,
                )
            return
        if config.dry_run:
            LOGGER.info("Would download: %s", target_path)
            return

        try:
            LOGGER.info("Download: %s", target_path)
            ok = await download_with_retries(client, message, target_path)
            if ok:
                stats.downloaded += 1
                store.record_download(
                    message_id=message.id,
                    chat_id=chat_id,
                    file_path=target_path,
                    file_size=target_path.stat().st_size,
                )
            else:
                stats.failed += 1
        except (asyncio.TimeoutError, OSError) as exc:
            stats.failed += 1
            LOGGER.error("Network error for message %s: %s", message.id, exc)


def message_in_date_range(message: Any, config: AppConfig) -> bool:
    """Return whether a message date is inside configured filters."""
    message_date = message_datetime_utc(message)
    if config.since and message_date and message_date < config.since:
        return False
    if config.until and message_date and message_date > config.until:
        return False
    return True


async def wait_for_tasks(tasks: set[asyncio.Task[None]]) -> None:
    """Wait for a task set and clear completed tasks."""
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        result = task.exception()
        if result:
            LOGGER.error("Download task failed: %s", result)
    tasks.clear()
    tasks.update(pending)


async def download_media(config: AppConfig) -> None:
    """Run the main Telegram media download workflow."""
    client = await create_client(config)
    try:
        if not config.chat_title:
            raise SystemExit("--chat is required when TELEGRAM_GROUP_TITLE is not set.")

        chat = await find_chat(client, config.chat_title)
        chat_id = chat_id_for(chat)
        semaphore = asyncio.Semaphore(config.concurrency)
        stats = DownloadStats()
        tasks: set[asyncio.Task[None]] = set()

        LOGGER.info('Chat: "%s"', config.chat_title)
        LOGGER.info("Output: %s", config.output_dir)
        LOGGER.info("SQLite DB: %s", config.db_path)
        LOGGER.info("Concurrency: %s", config.concurrency)
        if config.since:
            LOGGER.info("Since: %s", config.since.astimezone(local_timezone()).isoformat())
        if config.until:
            LOGGER.info("Until: %s", config.until.astimezone(local_timezone()).isoformat())

        with DownloadStore(config.db_path) as store:
            min_id = store.last_message_id() if config.resume else None
            if min_id:
                LOGGER.info("Resume enabled; requesting messages with min_id=%s", min_id)

            while True:
                try:
                    async for message in client.iter_messages(
                        chat,
                        limit=config.limit,
                        reverse=config.oldest_first,
                        min_id=min_id or 0,
                    ):
                        stats.scanned += 1
                        message_date = message_datetime_utc(message)
                        if config.since and message_date and message_date < config.since:
                            if not config.oldest_first:
                                break
                            continue
                        if not message_in_date_range(message, config):
                            continue

                        kind = media_kind(message)
                        if not kind:
                            continue
                        if config.media_type != "all" and config.media_type != kind:
                            continue

                        stats.matched += 1
                        task = asyncio.create_task(
                            download_one(
                                client=client,
                                message=message,
                                chat_id=chat_id,
                                config=config,
                                store=store,
                                semaphore=semaphore,
                                stats=stats,
                            )
                        )
                        tasks.add(task)
                        if len(tasks) >= config.concurrency * 2:
                            await wait_for_tasks(tasks)
                    break
                except FloodWaitError as exc:
                    wait_seconds = int(exc.seconds) + 1
                    LOGGER.warning("Flood wait while scanning; sleeping %s seconds", wait_seconds)
                    await asyncio.sleep(wait_seconds)
                    continue
                except (asyncio.TimeoutError, OSError) as exc:
                    stats.failed += 1
                    LOGGER.error("Network error while scanning messages: %s", exc)
                    break

            if tasks:
                done = await asyncio.gather(*tasks, return_exceptions=True)
                for result in done:
                    if isinstance(result, Exception):
                        stats.failed += 1
                        LOGGER.error("Download task failed: %s", result)

        LOGGER.info("Scanned messages: %s", stats.scanned)
        LOGGER.info("Matched media: %s", stats.matched)
        LOGGER.info("Downloaded files: %s", stats.downloaded)
        LOGGER.info("Skipped files: %s", stats.skipped)
        LOGGER.info("Failed files: %s", stats.failed)
        if config.dry_run:
            LOGGER.info("Dry run only: no files were saved.")
    finally:
        await client.disconnect()

"""Command-line interface for Telegram media downloads."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import AppConfig, load_config
from .downloader import download_media, list_chats

MEDIA_TYPES = (
    "all",
    "photos",
    "videos",
    "audio",
    "voice",
    "video_notes",
    "documents",
)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Download media from Telegram chats you can access."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with Telegram settings. Default: .env.",
    )
    parser.add_argument(
        "--chat",
        help="Telegram chat title. Required if TELEGRAM_GROUP_TITLE is not set.",
    )
    parser.add_argument(
        "--output",
        help="Download directory. Default: DOWNLOAD_DIR or downloads/telegram_media.",
    )
    parser.add_argument(
        "--flat-output",
        action="store_true",
        help="Save media directly into output instead of media-type subfolders.",
    )
    parser.add_argument(
        "--types",
        choices=MEDIA_TYPES,
        default="all",
        help="Which media to download. Default: all.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of messages to scan.",
    )
    parser.add_argument(
        "--since",
        help="Download messages from this local date/time onward.",
    )
    parser.add_argument(
        "--until",
        help="Download messages up to this local date/time.",
    )
    parser.add_argument(
        "--oldest-first",
        action="store_true",
        help="Scan messages from oldest to newest.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload existing files and overwrite SQLite records.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without saving files.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Only request messages newer than the last saved message_id in SQLite.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Concurrent downloads. Default: 3.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database path. Default: output/downloads.db.",
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL, for example socks5://user:pass@host:port.",
    )
    parser.add_argument(
        "--code",
        help="One-time Telegram login code. Warning: CLI args can be visible in process lists.",
    )
    parser.add_argument(
        "--password",
        help="Telegram 2FA password. Warning: prefer interactive input or keyring.",
    )
    parser.add_argument(
        "--password-keyring-service",
        help="Read Telegram 2FA password from this keyring service.",
    )
    parser.add_argument(
        "--password-keyring-username",
        help="Read Telegram 2FA password for this keyring username.",
    )
    parser.add_argument(
        "--force-sms",
        action="store_true",
        help="Ask Telegram to send the login code by SMS if Telegram allows it.",
    )
    parser.add_argument(
        "--qr-login",
        action="store_true",
        help="Log in by Telegram QR code instead of a one-time code.",
    )
    parser.add_argument(
        "--qr-path",
        default="telegram_login_qr.png",
        help="Where to save the QR login image.",
    )
    parser.add_argument(
        "--qr-timeout",
        type=int,
        default=240,
        help="How many seconds to wait for QR login.",
    )
    parser.add_argument(
        "--list-chats",
        action="store_true",
        help="List available Telegram chats and exit.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging level. Default: INFO.",
    )
    return parser


def setup_logging(level: str) -> None:
    """Configure process-wide logging."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def async_main(argv: list[str] | None = None) -> None:
    """Run the downloader CLI asynchronously."""
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_level)
    config: AppConfig = load_config(args)

    if args.list_chats:
        await list_chats(config)
        return

    await download_media(config)


def main(argv: list[str] | None = None) -> None:
    """Run the downloader CLI."""
    try:
        asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("Interrupted by user")
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

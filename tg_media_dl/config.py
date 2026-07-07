"""Configuration loading and date/proxy parsing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, time, timezone, tzinfo
import os
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv


DEFAULT_DOWNLOAD_DIR = "downloads/telegram_media"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for a downloader run."""

    api_id: int
    api_hash: str
    phone: str | None
    session_name: str
    session_dir: Path
    chat_title: str | None
    output_dir: Path
    flat_output: bool
    media_type: str
    limit: int | None
    since: datetime | None
    until: datetime | None
    oldest_first: bool
    overwrite: bool
    dry_run: bool
    resume: bool
    concurrency: int
    db_path: Path
    proxy: object | None
    login_code: str | None
    login_password: str | None
    force_sms: bool
    qr_login: bool
    qr_path: Path
    qr_timeout: int


def env_bool(name: str) -> bool:
    """Return an environment variable as a boolean."""
    value = os.getenv(name, "")
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def required_env(name: str) -> str:
    """Read a required environment variable or raise SystemExit."""
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}. Add it to .env or set it.")
    return value


def local_timezone() -> tzinfo:
    """Return the local timezone, falling back to UTC."""
    return datetime.now().astimezone().tzinfo or timezone.utc


def parse_datetime_filter(
    value: str | None,
    option_name: str,
    *,
    end_of_day: bool = False,
) -> datetime | None:
    """Parse a CLI date/time filter and return a UTC datetime."""
    if not value:
        return None

    normalized = value.strip().replace("T", " ", 1)
    formats = [
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%Y-%m-%d", True),
        ("%d.%m.%Y %H:%M:%S", False),
        ("%d.%m.%Y %H:%M", False),
        ("%d.%m.%Y", True),
    ]

    for fmt, date_only in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue

        if date_only and end_of_day:
            parsed = datetime.combine(parsed.date(), time.max)
        return parsed.replace(tzinfo=local_timezone()).astimezone(timezone.utc)

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid {option_name}: {value}. Use YYYY-MM-DD, DD.MM.YYYY, or add HH:MM."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone())
    return parsed.astimezone(timezone.utc)


def parse_proxy(proxy_url: str | None) -> object | None:
    """Parse a proxy URL into a Telethon-compatible PySocks tuple."""
    if not proxy_url:
        return None

    parsed = urlparse(proxy_url)
    if parsed.scheme.lower() != "socks5":
        raise SystemExit("Only socks5:// proxies are supported.")
    if not parsed.hostname or not parsed.port:
        raise SystemExit("Proxy must include host and port.")

    try:
        import socks
    except ImportError as exc:
        raise SystemExit("Install PySocks to use --proxy.") from exc

    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    return (socks.SOCKS5, parsed.hostname, parsed.port, True, username, password)


def load_config(args: argparse.Namespace) -> AppConfig:
    """Load configuration from argparse and environment variables."""
    load_dotenv(args.env_file)

    try:
        api_id = int(required_env("TELEGRAM_API_ID"))
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be a number.") from exc

    output_dir = Path(
        args.output or os.getenv("DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR)
    ).resolve()
    env_db_path = os.getenv("DOWNLOAD_DB")
    if args.db_path:
        db_path = Path(args.db_path).resolve()
    elif env_db_path:
        db_path = Path(env_db_path).resolve()
    else:
        db_path = output_dir / "downloads.db"
    chat_title = args.chat or os.getenv("TELEGRAM_GROUP_TITLE")
    if not chat_title and not args.list_chats:
        raise SystemExit("--chat is required when TELEGRAM_GROUP_TITLE is not set.")

    concurrency = max(1, args.concurrency)
    session_name = os.getenv("SESSION_NAME", "telegram_media")

    return AppConfig(
        api_id=api_id,
        api_hash=required_env("TELEGRAM_API_HASH"),
        phone=os.getenv("TELEGRAM_PHONE") or None,
        session_name=session_name,
        session_dir=Path("sessions").resolve(),
        chat_title=chat_title,
        output_dir=output_dir,
        flat_output=args.flat_output,
        media_type=args.types,
        limit=args.limit,
        since=parse_datetime_filter(args.since or os.getenv("DOWNLOAD_SINCE"), "--since"),
        until=parse_datetime_filter(
            args.until or os.getenv("DOWNLOAD_UNTIL"),
            "--until",
            end_of_day=True,
        ),
        oldest_first=args.oldest_first,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        resume=args.resume,
        concurrency=concurrency,
        db_path=db_path,
        proxy=parse_proxy(args.proxy or os.getenv("TELEGRAM_PROXY")),
        login_code=args.code or os.getenv("TELEGRAM_LOGIN_CODE") or None,
        login_password=args.password or os.getenv("TELEGRAM_2FA_PASSWORD") or None,
        force_sms=args.force_sms or env_bool("TELEGRAM_FORCE_SMS"),
        qr_login=args.qr_login,
        qr_path=Path(args.qr_path).resolve(),
        qr_timeout=args.qr_timeout,
    )

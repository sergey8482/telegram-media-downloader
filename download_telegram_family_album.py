import argparse
import asyncio
import getpass
import os
import re
import sys
from datetime import datetime, time, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


DEFAULT_GROUP_TITLE = "My Telegram Group"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download photos and videos from a Telegram group you can access."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with Telegram settings. Default: .env",
    )
    parser.add_argument(
        "--chat",
        help=f'Telegram group title. Default: "{DEFAULT_GROUP_TITLE}" or TELEGRAM_GROUP_TITLE.',
    )
    parser.add_argument(
        "--output",
        help="Download directory. Default: DOWNLOAD_DIR or downloads/telegram_family_album.",
    )
    parser.add_argument(
        "--flat-output",
        action="store_true",
        help="Save media directly into the output directory instead of photos/videos subfolders.",
    )
    parser.add_argument(
        "--types",
        choices=["all", "photos", "videos"],
        default="all",
        help="Which media to download. Default: all.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of messages to scan. Default: scan all available messages.",
    )
    parser.add_argument(
        "--since",
        help="Download messages from this local date/time onward. Examples: 2026-05-07, 07.05.2026, 2026-05-07 14:30.",
    )
    parser.add_argument(
        "--until",
        help="Download messages up to this local date/time. Examples: 2026-05-11, 11.05.2026 23:00.",
    )
    parser.add_argument(
        "--oldest-first",
        action="store_true",
        help="Scan messages from oldest to newest.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even if a file with the expected name already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without saving files.",
    )
    parser.add_argument(
        "--code",
        help="One-time Telegram login code. Prefer TELEGRAM_LOGIN_CODE for non-interactive runs.",
    )
    parser.add_argument(
        "--password",
        help="Telegram 2FA password if enabled. Prefer interactive input over storing it.",
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
        help="Where to save the QR login image. Default: telegram_login_qr.png",
    )
    parser.add_argument(
        "--qr-timeout",
        type=int,
        default=240,
        help="How many seconds to wait for QR login. Default: 240.",
    )
    parser.add_argument(
        "--list-chats",
        action="store_true",
        help="List available Telegram chats and exit. Useful if the group title is not found.",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}. Add it to .env or set it in the environment.")
    return value


def env_bool(name: str) -> bool:
    value = os.getenv(name, "")
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def parse_datetime_filter(value: str | None, option_name: str, *, end_of_day: bool = False):
    if not value:
        return None

    value = value.strip()
    formats = [
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%Y-%m-%d", True),
        ("%d.%m.%Y %H:%M:%S", False),
        ("%d.%m.%Y %H:%M", False),
        ("%d.%m.%Y", True),
    ]

    normalized = value.replace("T", " ", 1)
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


def message_datetime_utc(message):
    if not message.date:
        return None
    if message.date.tzinfo is None:
        return message.date.replace(tzinfo=timezone.utc)
    return message.date.astimezone(timezone.utc)


def noninteractive_input_error(secret_name: str) -> str:
    raise RuntimeError(
        f"Telegram requested {secret_name}, but this run cannot read interactive input. "
        f"Run the script in PowerShell yourself, or set {secret_name} temporarily for this run."
    )


def login_code_callback(code: str | None):
    if code:
        return lambda: code
    if sys.stdin.isatty():
        def read_code() -> str:
            try:
                return input("Please enter the code you received: ")
            except EOFError as exc:
                raise RuntimeError(
                    "Telegram requested TELEGRAM_LOGIN_CODE, but this run cannot read interactive input. "
                    "Run the script in PowerShell yourself, or set TELEGRAM_LOGIN_CODE temporarily for this run."
                ) from exc

        return read_code
    return lambda: noninteractive_input_error("TELEGRAM_LOGIN_CODE")


def login_password_callback(password: str | None):
    if password:
        return password
    if sys.stdin.isatty():
        def read_password() -> str:
            try:
                return getpass.getpass("Please enter your Telegram 2FA password: ")
            except EOFError as exc:
                raise RuntimeError(
                    "Telegram requested TELEGRAM_2FA_PASSWORD, but this run cannot read interactive input. "
                    "Run the script in PowerShell yourself, or set TELEGRAM_2FA_PASSWORD temporarily for this run."
                ) from exc

        return read_password
    return lambda: noninteractive_input_error("TELEGRAM_2FA_PASSWORD")


async def sign_in_with_qr(
    client: TelegramClient,
    qr_path: Path,
    timeout: int,
    password: str | None,
) -> None:
    await client.connect()
    if await client.is_user_authorized():
        return

    try:
        import qrcode
    except ImportError as exc:
        raise SystemExit("Missing qrcode package. Run: pip install -r requirements.txt") from exc

    qr_login = await client.qr_login()
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(qr_login.url)
    img.save(qr_path)

    print(f"QR login image saved: {qr_path}")
    print("Open Telegram on your phone: Settings -> Devices -> Link Desktop Device.")
    print(f"Waiting up to {timeout} seconds for QR scan...")

    try:
        await qr_login.wait(timeout=timeout)
    except SessionPasswordNeededError:
        if not password:
            raise SystemExit(
                "Telegram QR login succeeded, but your account requires a 2FA password. "
                "Run interactively, or set TELEGRAM_2FA_PASSWORD temporarily for this run."
            )
        await client.sign_in(password=password)
    except asyncio.TimeoutError as exc:
        raise SystemExit("QR login timed out. Run again to generate a fresh QR code.") from exc


def get_api_id() -> int:
    value = required_env("TELEGRAM_API_ID")
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be a number.") from exc


def clean_filename(value: str, max_length: int = 90) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip().strip(".")
    if not value:
        return "media"
    return value[:max_length].rstrip(" .")


def media_kind(message) -> str | None:
    if message.sticker:
        return None

    if message.photo:
        return "photos"

    file_info = message.file
    mime_type = getattr(file_info, "mime_type", "") if file_info else ""
    if mime_type.startswith("image/"):
        return "photos"
    if message.video or mime_type.startswith("video/"):
        return "videos"

    return None


def media_extension(message, kind: str) -> str:
    file_info = message.file
    original_name = getattr(file_info, "name", None) if file_info else None

    if original_name:
        suffix = Path(original_name).suffix
        if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix):
            return suffix.lower()

    ext = getattr(file_info, "ext", None) if file_info else None
    if ext and re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext):
        return ext.lower()

    return ".jpg" if kind == "photos" else ".mp4"


def target_path_for_message(message, output_dir: Path, kind: str, flat_output: bool = False) -> Path:
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


async def list_chats(client: TelegramClient) -> None:
    print("Available chats:")
    async for dialog in client.iter_dialogs():
        chat_type = "channel" if dialog.is_channel else "group" if dialog.is_group else "user"
        print(f"- {dialog.name} [{chat_type}] id={dialog.id}")


async def find_chat(client: TelegramClient, title: str):
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
        print(f'Found several chats named "{title}":')
        for dialog in matches:
            print(f"- {dialog.name} id={dialog.id}")
        raise SystemExit("Use --list-chats and rename the group or adjust --chat to be unique.")

    print(f'Could not find a chat named "{title}".')
    if partial_matches:
        print("Similar chats:")
        for dialog in partial_matches[:20]:
            print(f"- {dialog.name} id={dialog.id}")
    raise SystemExit("Run with --list-chats to see exact chat titles available to this account.")


async def download_media(args: argparse.Namespace) -> None:
    load_dotenv(args.env_file)

    api_id = get_api_id()
    api_hash = required_env("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE") or None
    login_code = args.code or os.getenv("TELEGRAM_LOGIN_CODE") or None
    login_password = args.password or os.getenv("TELEGRAM_2FA_PASSWORD") or None
    force_sms = args.force_sms or env_bool("TELEGRAM_FORCE_SMS")
    session_name = os.getenv("SESSION_NAME", "telegram_family_album")
    chat_title = args.chat or os.getenv("TELEGRAM_GROUP_TITLE", DEFAULT_GROUP_TITLE)
    output_dir = Path(args.output or os.getenv("DOWNLOAD_DIR", "downloads/telegram_family_album")).resolve()
    since = parse_datetime_filter(args.since or os.getenv("DOWNLOAD_SINCE"), "--since")
    until = parse_datetime_filter(args.until or os.getenv("DOWNLOAD_UNTIL"), "--until", end_of_day=True)
    session_dir = Path("sessions").resolve()
    session_dir.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(session_dir / session_name), api_id, api_hash)
    try:
        if args.qr_login:
            await sign_in_with_qr(client, Path(args.qr_path).resolve(), args.qr_timeout, login_password)
        else:
            await client.start(
                phone=phone,
                code_callback=login_code_callback(login_code),
                password=login_password_callback(login_password),
                force_sms=force_sms,
            )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        if args.list_chats:
            await list_chats(client)
            return

        chat = await find_chat(client, chat_title)
        scanned = 0
        matched = 0
        downloaded = 0
        skipped = 0

        print(f'Chat: "{chat_title}"')
        print(f"Output: {output_dir}")
        if since:
            print(f"Since: {since.astimezone(local_timezone()).isoformat()}")
        if until:
            print(f"Until: {until.astimezone(local_timezone()).isoformat()}")
        print("Scanning messages...")

        async for message in client.iter_messages(
            chat,
            limit=args.limit,
            reverse=args.oldest_first,
        ):
            scanned += 1
            message_date = message_datetime_utc(message)
            if since and message_date and message_date < since:
                if not args.oldest_first:
                    break
                continue
            if until and message_date and message_date > until:
                continue

            kind = media_kind(message)
            if not kind:
                continue
            if args.types != "all" and args.types != kind:
                continue

            matched += 1
            target_path = target_path_for_message(message, output_dir, kind, args.flat_output)

            if target_path.exists() and not args.overwrite:
                skipped += 1
                print(f"skip existing: {target_path}")
                continue

            if args.dry_run:
                print(f"would download: {target_path}")
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"download: {target_path}")
            saved_path = await client.download_media(message, file=str(target_path))
            if saved_path:
                downloaded += 1
            else:
                print(f"warning: Telegram did not return a saved path for message {message.id}")

        print()
        print(f"Scanned messages: {scanned}")
        print(f"Matched media: {matched}")
        print(f"Downloaded files: {downloaded}")
        print(f"Skipped existing files: {skipped}")
        if args.dry_run:
            print("Dry run only: no files were saved.")
    finally:
        await client.disconnect()


def main() -> None:
    args = parse_args()
    asyncio.run(download_media(args))


if __name__ == "__main__":
    main()

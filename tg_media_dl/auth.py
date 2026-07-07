"""Telegram authentication helpers."""

from __future__ import annotations

import asyncio
import getpass
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

LOGGER = logging.getLogger(__name__)


def noninteractive_input_error(secret_name: str) -> str:
    """Raise a clear error when non-interactive input is unavailable."""
    raise RuntimeError(
        f"Telegram requested {secret_name}, but this run cannot read interactive input. "
        f"Run the script in PowerShell yourself, or set {secret_name} temporarily."
    )


def login_code_callback(code: str | None) -> Callable[[], str]:
    """Return a callback that reads the Telegram login code."""
    if code:
        return lambda: code

    if not sys.stdin.isatty():
        return lambda: noninteractive_input_error("TELEGRAM_LOGIN_CODE")

    def read_code() -> str:
        try:
            return input("Please enter the code you received: ")
        except EOFError as exc:
            raise RuntimeError(
                "Telegram requested TELEGRAM_LOGIN_CODE, but this run cannot read input."
            ) from exc

    return read_code


def login_password_callback(password: str | None) -> str | Callable[[], str]:
    """Return a password value or callback for Telegram 2FA."""
    if password:
        return password

    if not sys.stdin.isatty():
        return lambda: noninteractive_input_error("TELEGRAM_2FA_PASSWORD")

    def read_password() -> str:
        try:
            return getpass.getpass("Please enter your Telegram 2FA password: ")
        except EOFError as exc:
            raise RuntimeError(
                "Telegram requested TELEGRAM_2FA_PASSWORD, but this run cannot read input."
            ) from exc

    return read_password


async def sign_in_with_qr(
    client: TelegramClient,
    qr_path: Path,
    timeout: int,
    password: str | None,
) -> None:
    """Sign in to Telegram by creating and waiting for a QR login token."""
    await client.connect()
    if await client.is_user_authorized():
        return

    try:
        import qrcode
    except ImportError as exc:
        raise SystemExit("Missing qrcode package. Run: pip install -r requirements.txt") from exc

    qr_login = await client.qr_login()
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(qr_login.url).save(qr_path)
    LOGGER.info("QR login image saved: %s", qr_path)
    LOGGER.info("Open Telegram: Settings -> Devices -> Link Desktop Device")
    LOGGER.info("Waiting up to %s seconds for QR scan", timeout)

    try:
        await qr_login.wait(timeout=timeout)
    except SessionPasswordNeededError as exc:
        if not password:
            raise SystemExit(
                "QR login succeeded, but Telegram 2FA password is required."
            ) from exc
        await client.sign_in(password=password)
    except asyncio.TimeoutError as exc:
        raise SystemExit("QR login timed out. Run again for a fresh QR code.") from exc
    finally:
        if qr_path.exists():
            qr_path.unlink()
            LOGGER.info("QR login image removed: %s", qr_path)


async def start_client(
    client: TelegramClient,
    *,
    phone: str | None,
    login_code: str | None,
    login_password: str | None,
    force_sms: bool,
    qr_login: bool,
    qr_path: Path,
    qr_timeout: int,
) -> None:
    """Connect and authenticate a Telegram client."""
    try:
        if qr_login:
            await sign_in_with_qr(client, qr_path, qr_timeout, login_password)
            return

        await client.start(
            phone=phone,
            code_callback=login_code_callback(login_code),
            password=login_password_callback(login_password),
            force_sms=force_sms,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

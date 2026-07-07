# Telegram Media Downloader

Python-скрипт для скачивания фото и видео из Telegram-группы, канала или чата, доступного вашему аккаунту.

Поддерживает:

- скачивание фото, видео, аудио, voice, video note и документов;
- фильтр по датам `--since` и `--until`;
- сохранение исходных имен файлов, если Telegram их отдаёт;
- отдельные папки `photos` / `videos` или плоскую выгрузку через `--flat-output`;
- атомарную запись через `.part` файлы;
- инкрементальную выгрузку через SQLite и `--resume`;
- параллельное скачивание через `--concurrency`;
- SOCKS5 proxy через `--proxy`;
- вход по коду Telegram или QR-коду.

## Установка / Installation

1. Получите `api_id` и `api_hash`: https://my.telegram.org/apps
2. Установите зависимости.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Или установить как пакет с console script:

```powershell
pip install -e .
tg-media-dl --help
```

3. Создайте `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Linux/macOS:

```bash
cp .env.example .env
$EDITOR .env
```

Пример:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+79991234567
TELEGRAM_GROUP_TITLE=My Telegram Group
DOWNLOAD_DIR=downloads/telegram_media
SESSION_NAME=telegram_media
```

`TELEGRAM_GROUP_TITLE` можно не задавать, но тогда передавайте `--chat`.

## Использование

Проверить, какие чаты видит аккаунт:

```powershell
tg-media-dl --list-chats
```

Скачать все фото и видео из чата, указанного в `.env`:

```powershell
tg-media-dl --chat "My Telegram Group"
```

Скачать только фото:

```powershell
tg-media-dl --chat "My Telegram Group" --types photos
```

Скачать только видео:

```powershell
tg-media-dl --chat "My Telegram Group" --types videos
```

Скачать медиа за период:

```powershell
tg-media-dl --chat "My Telegram Group" --since 2026-07-04 --until 2026-07-07
```

Скачать в конкретную папку без подпапок `photos` / `videos`:

```powershell
tg-media-dl --chat "My Telegram Group" --since 2026-07-04 --output "C:\Path\To\Folder" --flat-output
```

Продолжить только с новых сообщений, записанных после последнего `message_id` в SQLite:

```powershell
tg-media-dl --chat "My Telegram Group" --resume
```

Скачать параллельно в 5 потоков:

```powershell
tg-media-dl --chat "My Telegram Group" --concurrency 5
```

Использовать SOCKS5 proxy:

```powershell
tg-media-dl --chat "My Telegram Group" --proxy "socks5://user:pass@host:1080"
```

Linux/macOS examples use the same `tg-media-dl` arguments:

```bash
tg-media-dl --chat "My Telegram Group" --since 2026-07-04 --types photos
```

Посмотреть, что будет скачано, без сохранения файлов:

```powershell
tg-media-dl --chat "My Telegram Group" --dry-run
```

## Первый вход

При первом запуске Telegram попросит код подтверждения. Если включена двухфакторная защита, потребуется пароль 2FA. После входа файл сессии сохранится в `sessions/`.

Если скрипт запущен в неинтерактивной среде, одноразовый код можно передать только на время запуска:

```powershell
$env:TELEGRAM_LOGIN_CODE="12345"
tg-media-dl --list-chats
Remove-Item Env:\TELEGRAM_LOGIN_CODE
```

Не передавайте 2FA-пароль через `.env`. Для автоматизированного запуска используйте OS keyring:

```powershell
python -m keyring set telegram-media-downloader telegram-account-phone-or-name
tg-media-dl --chat "My Telegram Group" `
  --password-keyring-service telegram-media-downloader `
  --password-keyring-username telegram-account-phone-or-name
```

Вход по QR-коду:

```powershell
tg-media-dl --list-chats --qr-login
```

Скрипт временно сохранит `telegram_login_qr.png`, а после попытки входа удалит файл. Откройте Telegram на телефоне: `Настройки -> Устройства -> Подключить устройство`, затем отсканируйте QR-код.

## Безопасность

- Скрипт скачивает только то, что доступно вашему Telegram-аккаунту.
- Не публикуйте `.env`, `sessions/`, скачанные медиа и логи.
- `.gitignore` уже исключает секреты, сессии, медиа, QR-коды и временные файлы.
- На Linux/macOS ограничьте права на секреты:

```bash
chmod 600 .env
chmod 700 sessions
chmod 600 sessions/*.session
```

## Docker

```powershell
docker build -t telegram-media-downloader .
docker run --rm -it --env-file .env -v "${PWD}\downloads:/app/downloads" telegram-media-downloader --chat "My Telegram Group"
```

Linux/macOS:

```bash
docker build -t telegram-media-downloader .
docker run --rm -it --env-file .env -v "$PWD/downloads:/app/downloads" telegram-media-downloader --chat "My Telegram Group"
```

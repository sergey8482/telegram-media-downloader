# Telegram Media Downloader

Python-скрипт для скачивания фото и видео из Telegram-группы, канала или чата, доступного вашему аккаунту.

Поддерживает:

- скачивание фото, видео или обоих типов медиа;
- фильтр по датам `--since` и `--until`;
- сохранение исходных имен файлов, если Telegram их отдаёт;
- отдельные папки `photos` / `videos` или плоскую выгрузку через `--flat-output`;
- вход по коду Telegram или QR-коду.

## Установка

1. Получите `api_id` и `api_hash`: https://my.telegram.org/apps
2. Установите зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Создайте `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
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

## Использование

Проверить, какие чаты видит аккаунт:

```powershell
python download_telegram_family_album.py --list-chats
```

Скачать все фото и видео из чата, указанного в `.env`:

```powershell
python download_telegram_family_album.py
```

Скачать только фото:

```powershell
python download_telegram_family_album.py --types photos
```

Скачать только видео:

```powershell
python download_telegram_family_album.py --types videos
```

Скачать медиа за период:

```powershell
python download_telegram_family_album.py --since 2026-07-04 --until 2026-07-07
```

Скачать в конкретную папку без подпапок `photos` / `videos`:

```powershell
python download_telegram_family_album.py --since 2026-07-04 --output "C:\Path\To\Folder" --flat-output
```

Посмотреть, что будет скачано, без сохранения файлов:

```powershell
python download_telegram_family_album.py --dry-run
```

## Первый вход

При первом запуске Telegram попросит код подтверждения. Если включена двухфакторная защита, потребуется пароль 2FA. После входа файл сессии сохранится в `sessions/`.

Если скрипт запущен в неинтерактивной среде, одноразовый код можно передать только на время запуска:

```powershell
$env:TELEGRAM_LOGIN_CODE="12345"
python download_telegram_family_album.py --list-chats
Remove-Item Env:\TELEGRAM_LOGIN_CODE
```

Вход по QR-коду:

```powershell
python download_telegram_family_album.py --list-chats --qr-login
```

Скрипт сохранит `telegram_login_qr.png`. Откройте Telegram на телефоне: `Настройки -> Устройства -> Подключить устройство`, затем отсканируйте QR-код.

## Безопасность

- Скрипт скачивает только то, что доступно вашему Telegram-аккаунту.
- Не публикуйте `.env`, `sessions/`, скачанные медиа и логи.
- `.gitignore` уже исключает секреты, сессии, медиа, QR-коды и временные файлы.

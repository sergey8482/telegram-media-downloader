FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY tg_media_dl ./tg_media_dl
COPY download_telegram_family_album.py ./

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["tg-media-dl"]
CMD ["--help"]

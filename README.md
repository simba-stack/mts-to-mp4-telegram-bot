# Telegram-бот MTS → MP4

Бот принимает видеофайл `.mts` (и опционально `.m2ts`, `.ts`, `.avi`, `.mov`),
конвертирует его в `.mp4` (видео H.264 / аудио AAC) через `ffmpeg`
и возвращает результат пользователю. Временные файлы удаляются автоматически.

## Возможности

- Приём файлов как «документ» или «видео»
- Конвертация: `ffmpeg -i input.mts -c:v libx264 -preset medium -crf 23 -c:a aac output.mp4`
- Проверка расширения и размера файла
- Обработка ошибок: неподдерживаемый формат, повреждённый файл, превышение размера, сбой/отсутствие ffmpeg, таймаут
- UX-сообщения: «Файл принят» → «Идёт конвертация…» → «Готово, отправляю файл» / сообщение об ошибке
- Поддержка нескольких пользователей одновременно (с ограничением параллельных конвертаций через семафор)
- Логирование (модуль `logging`)
- Автоочистка временной папки при старте, ffmpeg запускается через `subprocess` без `shell=True`

## Требования

- Python 3.10+
- `ffmpeg` в системе (`ffmpeg -version` должно работать)
- Токен бота от [@BotFather](https://t.me/BotFather)

## Установка

```bash
pip install -r requirements.txt

# Установить ffmpeg:
#   Ubuntu/Debian: sudo apt install ffmpeg
#   macOS:         brew install ffmpeg
#   Windows:       https://ffmpeg.org/download.html (добавить в PATH)
```

## Запуск

```bash
export BOT_TOKEN="123456:ABC-DEF..."   # Windows: set BOT_TOKEN=...
python bot.py
```

## Переменные окружения

| Переменная            | По умолчанию | Описание                                   |
|-----------------------|--------------|--------------------------------------------|
| `BOT_TOKEN`           | —            | Токен бота (обязательно)                   |
| `MAX_FILE_SIZE`       | `524288000`  | Макс. размер файла в байтах (500 МБ)       |
| `MAX_CONCURRENT_JOBS` | `2`          | Кол-во одновременных конвертаций           |
| `FFMPEG_TIMEOUT`      | `3600`       | Таймаут конвертации одного файла (сек)     |
| `TEMP_DIR`            | системная    | Базовая папка для временных файлов          |

## ⚠️ Важно про лимит размера файла

Стандартный Telegram **Bot API позволяет боту скачивать файлы размером
не более 20 МБ**. Параметр `MAX_FILE_SIZE` (500 МБ) — это внутренний лимит
проекта; чтобы реально обрабатывать большие файлы, нужно поднять
[локальный Bot API server](https://github.com/tdlib/telegram-bot-api)
и указать боту его адрес (`base_url`/`base_file_url` в `Application.builder()`).

## Запуск в Docker

```bash
docker build -t mts2mp4-bot .
docker run -e BOT_TOKEN="123456:ABC-DEF..." mts2mp4-bot
```

## Деплой на Railway

1. Подключите этот репозиторий: **New Project → Deploy from GitHub repo**.
2. Railway автоматически соберёт образ по `Dockerfile` (ffmpeg уже включён).
3. В разделе **Variables** добавьте переменную `BOT_TOKEN` со значением токена от @BotFather.
4. Сервис запустится в режиме polling — webhook не требуется.

## Структура проекта

```
bot.py             # код бота
requirements.txt   # зависимости
Dockerfile         # образ с ffmpeg
README.md          # эта инструкция
```

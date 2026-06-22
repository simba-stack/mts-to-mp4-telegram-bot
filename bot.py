#!/usr/bin/env python3
"""
Telegram-бот для конвертации видео MTS -> MP4.

Принимает видеофайл (.mts и опционально .m2ts/.ts/.avi/.mov),
конвертирует его в .mp4 (H.264 + AAC) через ffmpeg и
возвращает результат пользователю. Временные файлы удаляются.
"""

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------------------------------------------------------------------------- #
# Конфигурация
# --------------------------------------------------------------------------- #

# Токен бота берётся из переменной окружения BOT_TOKEN
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Поддерживаемые входные расширения
SUPPORTED_EXTENSIONS = {".mts", ".m2ts", ".ts", ".avi", ".mov"}

# Максимальный размер файла (в байтах). По умолчанию 500 МБ.
# ВНИМАНИЕ: стандартный Bot API позволяет боту скачивать файлы до 20 МБ.
# Для файлов большего размера нужен локальный Bot API server (см. README).
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 500 * 1024 * 1024))

# Базовая временная папка
TEMP_DIR = Path(os.environ.get("TEMP_DIR", tempfile.gettempdir())) / "mts2mp4_bot"

# Максимум одновременных конвертаций (защита от перегрузки сервера)
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", 2))

# Таймаут на конвертацию одного файла (секунды)
FFMPEG_TIMEOUT = int(os.environ.get("FFMPEG_TIMEOUT", 60 * 60))

# --------------------------------------------------------------------------- #
# Логирование
# --------------------------------------------------------------------------- #

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
# Снижаем шум от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("mts2mp4")

# Семафор ограничивает число параллельных ffmpeg-процессов
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #

def ffmpeg_available() -> bool:
    """Проверяет наличие ffmpeg в системе."""
    return shutil.which("ffmpeg") is not None


async def convert_to_mp4(src: Path, dst: Path) -> tuple[bool, str]:
    """
    Конвертирует src -> dst через ffmpeg (subprocess, без shell=True).

    Возвращает (успех, текст_ошибки).
    """
    cmd = [
        "ffmpeg",
        "-y",                  # перезаписывать выходной файл
        "-i", str(src),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(dst),
    ]
    logger.info("Запуск ffmpeg: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "ffmpeg не найден на сервере."

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=FFMPEG_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, "Превышено время конвертации (таймаут)."

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[-1500:]
        logger.error("ffmpeg завершился с кодом %s: %s", proc.returncode, err)
        return False, "Ошибка ffmpeg при конвертации (возможно, файл повреждён)."

    if not dst.exists() or dst.stat().st_size == 0:
        return False, "Конвертация не дала результата (пустой файл)."

    return True, ""


# --------------------------------------------------------------------------- #
# Обработчики команд
# --------------------------------------------------------------------------- #

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "привет мацоня наташечка любимая девочка женушка женулька кавота милиньки\n"
        "я буду делать для тебе видева в фармате мп4 и меня написали пока ты "
        "спаалаааааааа\n\n"
        "Просто пришли мне файл .mts (также поддерживаются "
        ".m2ts, .ts, .avi, .mov) — и я верну тебе .mp4 (H.264 + AAC).\n"
        f"Максимальный размер файла: {MAX_FILE_SIZE // (1024 * 1024)} МБ.\n\n"
        "если што-то нужно будет добавить ты просто скажи кое-каму и он все "
        "сделает потому што ты его госпожа"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Отправь видеофайл документом (не как «видео», "
        "чтобы Telegram не пережал его).\n\n"
        "Поддерживаемые форматы входа: "
        + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        + "\nВыход: .mp4 (H.264 / AAC)."
    )


# --------------------------------------------------------------------------- #
# Основной обработчик файлов
# --------------------------------------------------------------------------- #

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    # Файл может прийти как document или как video
    tg_file = message.document or message.video
    if tg_file is None:
        await message.reply_text("Пришли, пожалуйста, видеофайл.")
        return

    # Имя файла и расширение
    file_name = getattr(tg_file, "file_name", None) or "input"
    ext = Path(file_name).suffix.lower()

    # 1. Проверка расширения
    if ext not in SUPPORTED_EXTENSIONS:
        await message.reply_text(
            f"❌ Неподдерживаемый формат: {ext or 'неизвестно'}.\n"
            "Поддерживаются: " + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
        return

    # 2. Проверка размера
    file_size = getattr(tg_file, "file_size", 0) or 0
    if file_size > MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ Файл слишком большой: {file_size // (1024 * 1024)} МБ. "
            f"Максимум — {MAX_FILE_SIZE // (1024 * 1024)} МБ."
        )
        return

    await message.reply_text("✅ Файл принят.")

    # Уникальная рабочая папка для этой задачи
    job_id = uuid.uuid4().hex
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    src_path = work_dir / f"input{ext}"
    dst_path = work_dir / "output.mp4"

    try:
        # 3. Скачивание файла
        try:
            file_obj = await tg_file.get_file()
            await file_obj.download_to_drive(custom_path=str(src_path))
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка скачивания файла")
            await message.reply_text(
                "❌ Не удалось скачать файл. Возможно, он превышает лимит "
                "Bot API (20 МБ для стандартного сервера)."
            )
            return

        # 4. Конвертация (с ограничением параллелизма)
        await message.reply_text("⏳ Идёт конвертация…")
        await context.bot.send_chat_action(
            chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO
        )

        async with _semaphore:
            ok, err = await convert_to_mp4(src_path, dst_path)

        if not ok:
            await message.reply_text(f"❌ {err}")
            return

        # 5. Отправка результата
        await message.reply_text("📤 Готово, отправляю файл…")
        out_name = Path(file_name).stem + ".mp4"
        with open(dst_path, "rb") as f:
            await message.reply_document(document=f, filename=out_name)

    except Exception:  # noqa: BLE001
        logger.exception("Непредвиденная ошибка при обработке файла")
        await message.reply_text("❌ Произошла непредвиденная ошибка.")
    finally:
        # 6. Удаление временных файлов
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("Временная папка удалена: %s", work_dir)


# --------------------------------------------------------------------------- #
# Очистка временной папки при старте
# --------------------------------------------------------------------------- #

def cleanup_temp_dir() -> None:
    """Удаляет остатки временных файлов от прошлых запусков."""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #

def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Переменная окружения BOT_TOKEN не задана.")

    if not ffmpeg_available():
        raise SystemExit(
            "ffmpeg не найден в системе. Установите ffmpeg и повторите запуск."
        )

    cleanup_temp_dir()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(
        MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file)
    )

    logger.info("Бот запущен. Ожидание сообщений…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

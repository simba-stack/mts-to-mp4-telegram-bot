FROM python:3.11-slim

# Устанавливаем ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Токен передаётся через переменную окружения при запуске:
#   docker run -e BOT_TOKEN=xxxxx mts2mp4-bot
ENV BOT_TOKEN=""

CMD ["python", "bot.py"]

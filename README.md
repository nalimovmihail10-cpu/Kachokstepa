# 💪 Gym Clicker

Telegram Mini App — кликер с качалкой.

## Деплой на Railway

1. Залей все файлы на GitHub
2. В Railway: New Project → Deploy from GitHub
3. Добавь переменные в Variables:
   - BOT_TOKEN = токен от @BotFather  
   - GAME_URL = https://твой-проект.up.railway.app
   - PORT = 8080
4. Railway найдёт Dockerfile и задеплоит автоматически

## Локальный запуск через Docker

    docker compose up -d

## Локальный запуск без Docker

    pip install -r requirements.txt
    BOT_TOKEN=... GAME_URL=http://localhost:8080 python main.py

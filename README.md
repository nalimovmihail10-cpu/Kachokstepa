# Gym Clicker

## Деплой Railway
1. Залей все файлы на GitHub
2. Railway → New Project → Deploy from GitHub
3. Variables: BOT_TOKEN, GAME_URL, PORT=8080
4. Railway найдёт Dockerfile автоматически

## Локальный запуск
pip install -r requirements.txt
BOT_TOKEN=xxx GAME_URL=http://localhost:8080 python main.py

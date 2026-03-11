# 💪 Gym Clicker — Telegram Mini App

## Деплой на Railway

1. Залей все файлы на GitHub
2. В Railway создай новый проект → Deploy from GitHub repo
3. В **Variables** добавь:
   - `BOT_TOKEN` = токен от @BotFather
   - `GAME_URL` = https://твой-проект.up.railway.app
   - `PORT` = 8080
4. Railway автоматически найдёт Dockerfile и задеплоит

## Запуск локально

```bash
pip install -r requirements.txt
BOT_TOKEN=... GAME_URL=http://localhost:8080 python main.py
```

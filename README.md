# 💪 Качалка Кликер — Telegram Mini App

## Файлы проекта

| Файл | Описание |
|------|----------|
| `main.py` | Всё в одном: бот + сервер + игра |
| `requirements.txt` | Зависимости Python |
| `Dockerfile` | Docker образ |
| `docker-compose.yml` | Запуск одной командой |
| `.env.example` | Пример переменных окружения |

---

## 🐳 Запуск через Docker

```bash
# 1. Создай .env
cp .env.example .env

# 2. Вставь токен и URL в .env
nano .env

# 3. Запуск
docker compose up -d
```

Игра будет доступна на `http://сервер:8080`

---

## Запуск без Docker

```bash
pip install -r requirements.txt
python main.py
```

---

## Получить токен бота

- Напиши @BotFather в Telegram → /newbot
- Скопируй токен в .env

---

## HTTPS (обязательно для Telegram Mini App)

Telegram требует HTTPS. Быстрый способ — Cloudflare Tunnel:
```bash
cloudflared tunnel --url http://localhost:8080
```
Вставь полученный URL в GAME_URL в .env

---

## Геймплей

- 💪 Клик — тыкай на монету (мультитач поддерживается!)
- ⚡ Энергия — тратится на клики, восстанавливается сама
- 📈 Пассивный доход — виден доход /сек и /ч
- 💤 Оффлайн — до 2 часов дохода пока не играешь
- 🔥 Престиж — сброс за постоянный множитель
- 🏆 16 достижений и 10 уровней (Новичок → АБСОЛЮТ)

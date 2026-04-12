# Gym Clicker

## Deploy on Railway
1. Push all files to GitHub
2. Railway -> New Project -> Deploy from GitHub
3. Set Variables: BOT_TOKEN, GAME_URL, PORT=8080
4. Railway uses Dockerfile automatically

## Local run
pip install -r requirements.txt
BOT_TOKEN=xxx GAME_URL=http://localhost:8080 python main.py

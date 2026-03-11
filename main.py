"""
main.py — Качалка Кликер
Запускает веб-сервер с игрой и Telegram бота одновременно.

Использование:
    pip install -r requirements.txt
    python main.py

Или через Docker:
    docker compose up -d
"""

import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── Настройки ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
GAME_URL  = os.environ.get("GAME_URL",  "https://ВАШ_ДОМЕН")
PORT      = int(os.environ.get("PORT", 8080))
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── HTML игры ────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>💪 Качалка Кликер</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');

  :root {
    --gold: #FFD700;
    --gold2: #FFA500;
    --dark: #0a0a12;
    --panel: #12121e;
    --panel2: #1a1a2e;
    --accent: #ff6b00;
    --accent2: #ff3c00;
    --text: #f0e6d3;
    --muted: #7a6f5e;
    --green: #39ff14;
    --red: #ff2244;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

  body {
    background: var(--dark);
    color: var(--text);
    font-family: 'Nunito', sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
    background-image: 
      radial-gradient(ellipse at 20% 0%, rgba(255,107,0,0.08) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 100%, rgba(255,215,0,0.06) 0%, transparent 60%);
  }

  /* HEADER */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px 8px;
    background: linear-gradient(180deg, rgba(18,18,30,0.98) 0%, transparent 100%);
    position: sticky;
    top: 0;
    z-index: 100;
    border-bottom: 1px solid rgba(255,215,0,0.1);
  }

  .level-badge {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .level-label {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
  }

  .level-name {
    font-family: 'Nunito', sans-serif;
    font-size: 10px;
    color: var(--gold);
    line-height: 1;
  }

  .header-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }

  .coins-display {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .cph-display {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .cph-value {
    font-family: 'Nunito', sans-serif;
    font-size: 14px;
    font-weight: 900;
    color: var(--green);
    line-height: 1;
  }

  .cph-label {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
  }

  .coins-value {
    font-family: 'Nunito', sans-serif;
    font-size: 22px;
    font-weight: 900;
    color: var(--gold);
    line-height: 1;
  }

  .coins-label {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
  }

  /* XP BAR */
  .xp-bar-container {
    padding: 6px 16px 10px;
    background: rgba(18,18,30,0.5);
  }

  .xp-info {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 4px;
  }

  .xp-bar {
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
  }

  .xp-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--gold));
    border-radius: 3px;
    transition: width 0.5s ease;
  }

  /* STATS ROW */
  .stats-row {
    display: flex;
    gap: 8px;
    padding: 10px 16px;
  }

  .stat-chip {
    flex: 1;
    background: var(--panel);
    border: 1px solid rgba(255,215,0,0.12);
    border-radius: 10px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .stat-val {
    font-family: 'Nunito', sans-serif;
    font-size: 18px;
    color: var(--gold);
    line-height: 1;
  }

  .stat-lbl {
    font-size: 10px;
    color: var(--muted);
    margin-top: 2px;
    letter-spacing: 0.5px;
  }

  /* MAIN CLICKER AREA */
  .clicker-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px 16px 10px;
    position: relative;
  }

  .energy-bar {
    width: 100%;
    max-width: 320px;
    margin-bottom: 16px;
  }

  .energy-info {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    margin-bottom: 5px;
  }

  .energy-label { color: var(--accent); font-weight: 600; letter-spacing: 1px; }
  .energy-count { color: var(--text); }

  .energy-track {
    height: 8px;
    background: rgba(255,255,255,0.07);
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid rgba(255,107,0,0.2);
  }

  .energy-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent2), var(--accent), #ffaa00);
    border-radius: 4px;
    transition: width 0.2s ease;
  }

  /* COIN BUTTON */
  .coin-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 10px 0;
  }

  .coin-glow {
    position: absolute;
    width: 220px;
    height: 220px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255,200,0,0.15) 0%, transparent 70%);
    animation: pulse-glow 2s ease-in-out infinite;
  }

  @keyframes pulse-glow {
    0%, 100% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(1.1); opacity: 1; }
  }

  .coin-btn {
    width: 180px;
    height: 180px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    position: relative;
    z-index: 10;
    background: 
      radial-gradient(circle at 35% 30%, rgba(255,255,200,0.5) 0%, transparent 50%),
      radial-gradient(circle at 70% 70%, rgba(180,100,0,0.3) 0%, transparent 50%),
      linear-gradient(135deg, #f5c518 0%, #e8a800 25%, #ffd700 50%, #cc8800 75%, #e8a800 100%);
    box-shadow:
      0 0 0 4px rgba(255,200,0,0.3),
      0 0 30px rgba(255,180,0,0.4),
      0 8px 32px rgba(0,0,0,0.6),
      inset 0 2px 8px rgba(255,255,200,0.4),
      inset 0 -4px 8px rgba(120,60,0,0.3);
    transition: transform 0.08s ease, box-shadow 0.08s ease;
    user-select: none;
    -webkit-user-select: none;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 80px;
    line-height: 1;
  }

  .coin-btn:active, .coin-btn.clicking {
    transform: scale(0.92);
    box-shadow:
      0 0 0 2px rgba(255,200,0,0.2),
      0 0 15px rgba(255,180,0,0.3),
      0 4px 16px rgba(0,0,0,0.6),
      inset 0 2px 8px rgba(255,255,200,0.2),
      inset 0 -2px 4px rgba(120,60,0,0.4);
  }

  .coin-btn.no-energy {
    filter: grayscale(0.7) brightness(0.6);
    cursor: not-allowed;
  }

  /* FLOATING TEXTS */
  .float-text {
    position: fixed;
    font-family: 'Nunito', sans-serif;
    font-size: 22px;
    font-weight: 900;
    color: var(--gold);
    text-shadow: 0 0 10px rgba(255,200,0,0.8), 0 2px 4px rgba(0,0,0,0.9);
    pointer-events: none;
    z-index: 9999;
    animation: float-up 1s ease-out forwards;
    white-space: nowrap;
  }

  @keyframes float-up {
    0% { opacity: 1; transform: translateY(0) scale(1); }
    50% { opacity: 1; transform: translateY(-40px) scale(1.2); }
    100% { opacity: 0; transform: translateY(-90px) scale(0.8); }
  }

  /* CLICK RIPPLE */
  .ripple {
    position: fixed;
    border-radius: 50%;
    background: rgba(255,200,0,0.3);
    pointer-events: none;
    z-index: 9998;
    animation: ripple-out 0.5s ease-out forwards;
  }

  @keyframes ripple-out {
    0% { transform: scale(0); opacity: 0.8; }
    100% { transform: scale(3); opacity: 0; }
  }

  /* TABS */
  .tabs {
    display: flex;
    padding: 0 16px;
    gap: 4px;
    margin-top: 10px;
  }

  .tab-btn {
    flex: 1;
    padding: 10px 6px;
    background: var(--panel);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    color: var(--muted);
    font-family: 'Nunito', sans-serif;
    font-size: 7px;
    font-weight: 600;
    letter-spacing: 1px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: center;
  }

  .tab-btn.active {
    background: linear-gradient(135deg, rgba(255,107,0,0.2), rgba(255,200,0,0.1));
    border-color: rgba(255,200,0,0.4);
    color: var(--gold);
  }

  /* CONTENT PANELS */
  .panel-content {
    padding: 12px 16px 100px;
    display: none;
  }

  .panel-content.active {
    display: block;
  }

  /* UPGRADES */
  .upgrade-card {
    background: var(--panel);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    overflow: hidden;
  }

  .upgrade-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,107,0,0) 0%, rgba(255,200,0,0) 100%);
    transition: background 0.2s;
  }

  .upgrade-card.affordable::before {
    background: linear-gradient(135deg, rgba(255,107,0,0.05) 0%, rgba(255,200,0,0.05) 100%);
  }

  .upgrade-card.affordable {
    border-color: rgba(255,200,0,0.3);
  }

  .upgrade-card.maxed {
    opacity: 0.5;
    cursor: default;
  }

  .upgrade-card:active:not(.maxed) {
    transform: scale(0.98);
  }

  .upgrade-icon {
    width: 52px;
    height: 52px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(255,107,0,0.2), rgba(255,200,0,0.1));
    border: 1px solid rgba(255,200,0,0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    flex-shrink: 0;
  }

  .upgrade-info {
    flex: 1;
    min-width: 0;
  }

  .upgrade-name {
    font-family: 'Nunito', sans-serif;
    font-size: 14px;
    color: var(--text);
    margin-bottom: 3px;
  }

  .upgrade-desc {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.3;
  }

  .upgrade-level {
    font-size: 10px;
    color: var(--accent);
    margin-top: 3px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  .upgrade-price {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    flex-shrink: 0;
  }

  .price-val {
    font-family: 'Nunito', sans-serif;
    font-size: 14px;
    color: var(--gold);
    white-space: nowrap;
  }

  .price-lbl {
    font-size: 10px;
    color: var(--muted);
  }

  .price-val.cant-afford {
    color: var(--red);
  }

  /* ACHIEVEMENTS */
  .achievement-card {
    background: var(--panel);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
    opacity: 0.4;
    transition: all 0.3s;
  }

  .achievement-card.unlocked {
    opacity: 1;
    border-color: rgba(255,200,0,0.3);
    background: linear-gradient(135deg, rgba(255,107,0,0.08), rgba(255,200,0,0.05));
  }

  .ach-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    flex-shrink: 0;
  }

  .ach-info { flex: 1; }
  .ach-name { font-family: 'Nunito', sans-serif; font-size: 13px; margin-bottom: 3px; }
  .ach-desc { font-size: 11px; color: var(--muted); }

  /* SECTION TITLE */
  .section-title {
    font-family: 'Nunito', sans-serif;
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
    margin: 16px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }

  /* NOTIFICATION */
  .notif {
    position: fixed;
    top: 70px;
    left: 50%;
    transform: translateX(-50%) translateY(-20px);
    background: linear-gradient(135deg, var(--accent), var(--gold));
    color: #000;
    font-family: 'Nunito', sans-serif;
    font-size: 13px;
    padding: 10px 20px;
    border-radius: 30px;
    z-index: 9999;
    opacity: 0;
    transition: all 0.3s;
    white-space: nowrap;
    box-shadow: 0 4px 20px rgba(255,107,0,0.5);
    pointer-events: none;
  }

  .notif.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }

  /* ACHIEVEMENT POPUP */
  .ach-popup {
    position: fixed;
    bottom: -100px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--panel2);
    border: 1px solid rgba(255,200,0,0.4);
    border-radius: 16px;
    padding: 14px 20px;
    z-index: 9999;
    display: flex;
    align-items: center;
    gap: 12px;
    transition: bottom 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    box-shadow: 0 -4px 30px rgba(255,200,0,0.15);
    min-width: 280px;
  }

  .ach-popup.show { bottom: 20px; }
  .ach-popup-icon { font-size: 36px; }
  .ach-popup-text {}
  .ach-popup-label { font-size: 10px; color: var(--gold); letter-spacing: 2px; font-weight: 600; }
  .ach-popup-name { font-family: 'Nunito', sans-serif; font-size: 14px; }

  /* PRESTIGE SECTION */
  .prestige-box {
    background: linear-gradient(135deg, rgba(255,107,0,0.1), rgba(255,200,0,0.08));
    border: 1px solid rgba(255,200,0,0.25);
    border-radius: 16px;
    padding: 20px;
    text-align: center;
    margin-bottom: 16px;
  }

  .prestige-title {
    font-family: 'Nunito', sans-serif;
    font-size: 20px;
    color: var(--gold);
    margin-bottom: 8px;
  }

  .prestige-desc {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
    margin-bottom: 16px;
  }

  .prestige-btn {
    background: linear-gradient(135deg, var(--accent), var(--gold));
    border: none;
    border-radius: 12px;
    padding: 14px 30px;
    font-family: 'Nunito', sans-serif;
    font-size: 16px;
    color: #000;
    cursor: pointer;
    transition: transform 0.1s, box-shadow 0.1s;
    box-shadow: 0 4px 20px rgba(255,107,0,0.4);
  }

  .prestige-btn:active { transform: scale(0.97); }
  .prestige-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* STATS PAGE */
  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 16px;
  }

  .stat-card {
    background: var(--panel);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 14px;
  }

  .stat-card-val {
    font-family: 'Nunito', sans-serif;
    font-size: 20px;
    color: var(--gold);
  }

  .stat-card-lbl {
    font-size: 11px;
    color: var(--muted);
    margin-top: 4px;
  }

  /* OFFLINE POPUP */
  .offline-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.85);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(6px);
  }
  .offline-modal {
    background: var(--panel2);
    border: 1px solid rgba(255,215,0,0.35);
    border-radius: 24px;
    padding: 32px 28px;
    text-align: center;
    max-width: 320px;
    width: 90%;
    box-shadow: 0 0 60px rgba(255,200,0,0.15), 0 20px 60px rgba(0,0,0,0.6);
    animation: modal-in 0.4s cubic-bezier(0.175,0.885,0.32,1.275);
  }
  @keyframes modal-in {
    0% { transform: scale(0.7); opacity: 0; }
    100% { transform: scale(1); opacity: 1; }
  }
  .offline-icon {
    font-size: 56px;
    margin-bottom: 12px;
    animation: snore 2s ease-in-out infinite;
  }
  @keyframes snore {
    0%,100% { transform: translateY(0); }
    50% { transform: translateY(-6px); }
  }
  .offline-title {
    font-family: 'Nunito', sans-serif;
    font-size: 16px;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 6px;
  }
  .offline-time {
    font-family: 'Nunito', sans-serif;
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 20px;
  }
  .offline-earned-label {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 6px;
    letter-spacing: 1px;
  }
  .offline-earned {
    font-family: 'Nunito', sans-serif;
    font-size: 42px;
    font-weight: 900;
    color: var(--gold);
    text-shadow: 0 0 30px rgba(255,200,0,0.5);
    margin-bottom: 10px;
    line-height: 1;
  }
  .offline-note {
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 24px;
    line-height: 1.4;
  }
  .offline-btn {
    width: 100%;
    padding: 16px;
    background: linear-gradient(135deg, var(--accent), var(--gold));
    border: none;
    border-radius: 14px;
    font-family: 'Nunito', sans-serif;
    font-size: 17px;
    font-weight: 900;
    color: #000;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(255,150,0,0.4);
    transition: transform 0.1s;
  }
  .offline-btn:active { transform: scale(0.97); }
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="level-badge">
    <span class="level-label">Уровень <span id="levelNum">1</span></span>
    <span class="level-name" id="levelName">Новичок</span>
  </div>
  <div class="header-right">
    <div class="coins-display">
      <span class="coins-value" id="coinsDisplay">0</span>
      <span class="coins-label">💰 МОНЕТ</span>
    </div>
    <div class="cph-display">
      <span class="cph-value" id="cphDisplay">0</span>
      <span class="cph-label">📈 В ЧАС</span>
    </div>
  </div>
</div>

<!-- XP BAR -->
<div class="xp-bar-container">
  <div class="xp-info">
    <span style="color:var(--accent);font-weight:600;letter-spacing:1px;font-size:11px;">ОПЫТ</span>
    <span id="xpInfo">0 / 100</span>
  </div>
  <div class="xp-bar">
    <div class="xp-fill" id="xpFill" style="width:0%"></div>
  </div>
</div>

<!-- STATS ROW -->
<div class="stats-row">
  <div class="stat-chip">
    <span class="stat-val" id="cpcDisplay">+1</span>
    <span class="stat-lbl">за клик</span>
  </div>
  <div class="stat-chip">
    <span class="stat-val" id="cpsDisplay">0</span>
    <span class="stat-lbl">/ сек</span>
  </div>
  <div class="stat-chip">
    <span class="stat-val" id="prestigeDisplay">×1.0</span>
    <span class="stat-lbl">множитель</span>
  </div>
</div>

<!-- CLICKER -->
<div class="clicker-area">
  <div class="energy-bar">
    <div class="energy-info">
      <span class="energy-label">⚡ ЭНЕРГИЯ</span>
      <span class="energy-count" id="energyCount">100 / 100</span>
    </div>
    <div class="energy-track">
      <div class="energy-fill" id="energyFill" style="width:100%"></div>
    </div>
  </div>
  <div class="coin-wrapper">
    <div class="coin-glow"></div>
    <button class="coin-btn" id="coinBtn">💪</button>
  </div>
</div>

<!-- TABS -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('click')">🖱 КЛИК</button>
  <button class="tab-btn" onclick="switchTab('passive')">⏱ ПАССИВ</button>
  <button class="tab-btn" onclick="switchTab('stats')">📊 СТАТ</button>
  <button class="tab-btn" onclick="switchTab('ach')">🏆 АЧИВ</button>
</div>

<!-- CLICK UPGRADES -->
<div class="panel-content active" id="panel-click">
  <div class="section-title">Усиления клика</div>
  <div id="clickUpgradesList"></div>

  <div class="section-title" style="margin-top:20px">Энергия</div>
  <div id="energyUpgradesList"></div>
</div>

<!-- PASSIVE UPGRADES -->
<div class="panel-content" id="panel-passive">
  <div class="section-title">Пассивный доход</div>
  <div id="passiveUpgradesList"></div>

  <div class="section-title" style="margin-top:20px">Престиж</div>
  <div class="prestige-box">
    <div class="prestige-title">🔥 ПРЕСТИЖ</div>
    <div class="prestige-desc">
      Сбрось прогресс и получи постоянный<br>множитель к монетам.<br>
      Нужно: <strong id="prestigeReq" style="color:var(--gold)">100,000</strong> монет всего
    </div>
    <button class="prestige-btn" id="prestigeBtn" onclick="doPrestige()" disabled>НАЖАТЬ</button>
  </div>
  <div id="prestigeList"></div>
</div>

<!-- STATS -->
<div class="panel-content" id="panel-stats">
  <div class="section-title">Статистика</div>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-card-val" id="s-totalCoins">0</div>
      <div class="stat-card-lbl">Всего монет</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-val" id="s-totalClicks">0</div>
      <div class="stat-card-lbl">Кликов</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-val" id="s-prestiges">0</div>
      <div class="stat-card-lbl">Престижей</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-val" id="s-playTime">0м</div>
      <div class="stat-card-lbl">Время игры</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-val" id="s-maxCps">0</div>
      <div class="stat-card-lbl">Макс. /сек</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-val" id="s-maxCpc">+1</div>
      <div class="stat-card-lbl">Макс. за клик</div>
    </div>
  </div>
</div>

<!-- ACHIEVEMENTS -->
<div class="panel-content" id="panel-ach">
  <div class="section-title">Достижения</div>
  <div id="achievementsList"></div>
</div>

<!-- OFFLINE EARNINGS POPUP -->
<div class="offline-overlay" id="offlineOverlay" style="display:none">
  <div class="offline-modal">
    <div class="offline-icon">💤</div>
    <div class="offline-title">Пока тебя не было...</div>
    <div class="offline-time" id="offlineTime"></div>
    <div class="offline-earned-label">Качалка заработала:</div>
    <div class="offline-earned" id="offlineEarned">+0</div>
    <div class="offline-note">Оффлайн доход считается до 2 часов</div>
    <button class="offline-btn" onclick="closeOfflinePopup()">ЗАБРАТЬ 💰</button>
  </div>
</div>

<!-- NOTIFICATION -->
<div class="notif" id="notif"></div>

<!-- ACHIEVEMENT POPUP -->
<div class="ach-popup" id="achPopup">
  <div class="ach-popup-icon" id="achPopupIcon">🏆</div>
  <div class="ach-popup-text">
    <div class="ach-popup-label">ДОСТИЖЕНИЕ!</div>
    <div class="ach-popup-name" id="achPopupName">-</div>
  </div>
</div>

<script>
// ==================== GAME DATA ====================
const CLICK_UPGRADES = [
  { id:'cu1', name:'Протеиновый шейк', icon:'🥤', desc:'Больше сил в руках', basePrice:25, priceGrowth:2.1, maxLevel:30, effect:'cpc', value:1 },
  { id:'cu2', name:'Спортивные перчатки', icon:'🥊', desc:'Точный удар по монете', basePrice:120, priceGrowth:2.2, maxLevel:25, effect:'cpc', value:3 },
  { id:'cu3', name:'Предтрен', icon:'⚡', desc:'Взрывная сила удара', basePrice:600, priceGrowth:2.3, maxLevel:20, effect:'cpc', value:10 },
  { id:'cu4', name:'Анаболики', icon:'💉', desc:'Сила зашкаливает', basePrice:4000, priceGrowth:2.4, maxLevel:15, effect:'cpc', value:40 },
  { id:'cu5', name:'Режим зверя', icon:'🦁', desc:'Ты непобедим', basePrice:30000, priceGrowth:2.5, maxLevel:12, effect:'cpc', value:200 },
  { id:'cu6', name:'Бог качалки', icon:'🏛️', desc:'Запредельная мощь', basePrice:300000, priceGrowth:2.6, maxLevel:10, effect:'cpc', value:1200 },
];

const ENERGY_UPGRADES = [
  { id:'eu1', name:'Расширенный запас', icon:'🔋', desc:'Больше энергии', basePrice:150, priceGrowth:2.2, maxLevel:15, effect:'maxEnergy', value:50 },
  { id:'eu2', name:'Быстрое восстановление', icon:'🔄', desc:'Энергия восст. быстрее', basePrice:400, priceGrowth:2.3, maxLevel:15, effect:'energyRegen', value:1 },
  { id:'eu3', name:'Энергетик', icon:'🟡', desc:'Мощный буст восст.', basePrice:3000, priceGrowth:2.5, maxLevel:10, effect:'energyRegen', value:5 },
];

const PASSIVE_UPGRADES = [
  { id:'pu1', name:'Новичок в зале', icon:'🚶', desc:'Парень качается за тебя', basePrice:50, priceGrowth:1.8, maxLevel:50, effect:'cps', value:0.5 },
  { id:'pu2', name:'Личный тренер', icon:'👨‍🏫', desc:'Профи с программой тренировок', basePrice:300, priceGrowth:1.9, maxLevel:40, effect:'cps', value:2 },
  { id:'pu3', name:'Мини-качалка', icon:'🏋️', desc:'Своя маленькая качалка', basePrice:1500, priceGrowth:2.0, maxLevel:35, effect:'cps', value:8 },
  { id:'pu4', name:'Спортзал', icon:'🏟️', desc:'Целый зал работает на тебя', basePrice:8000, priceGrowth:2.1, maxLevel:30, effect:'cps', value:30 },
  { id:'pu5', name:'Сеть клубов', icon:'🌐', desc:'Клубы по всему городу', basePrice:50000, priceGrowth:2.2, maxLevel:20, effect:'cps', value:150 },
  { id:'pu6', name:'Фитнес-империя', icon:'👑', desc:'Ты контролируешь рынок', basePrice:500000, priceGrowth:2.3, maxLevel:15, effect:'cps', value:800 },
];

const LEVELS = [
  { name:'Новичок', xp:0 },
  { name:'Любитель', xp:100 },
  { name:'Спортсмен', xp:300 },
  { name:'Атлет', xp:700 },
  { name:'Культурист', xp:1500 },
  { name:'Чемпион', xp:3500 },
  { name:'Мастер', xp:8000 },
  { name:'Легенда', xp:20000 },
  { name:'Бог Железа', xp:50000 },
  { name:'АБСОЛЮТ', xp:120000 },
];

const ACHIEVEMENTS = [
  { id:'a1', name:'Первый клик', icon:'👆', desc:'Нажми на монету', check: s => s.totalClicks >= 1 },
  { id:'a2', name:'100 кликов', icon:'💪', desc:'Сделай 100 кликов', check: s => s.totalClicks >= 100 },
  { id:'a3', name:'1000 кликов', icon:'🔥', desc:'Сделай 1000 кликов', check: s => s.totalClicks >= 1000 },
  { id:'a4', name:'10000 кликов', icon:'💥', desc:'Машина для кликов!', check: s => s.totalClicks >= 10000 },
  { id:'a5', name:'100 монет', icon:'💰', desc:'Накопи 100 монет', check: s => s.totalCoins >= 100 },
  { id:'a6', name:'1000 монет', icon:'💎', desc:'Накопи 1000 монет', check: s => s.totalCoins >= 1000 },
  { id:'a7', name:'10000 монет', icon:'🪙', desc:'Накопи 10k монет', check: s => s.totalCoins >= 10000 },
  { id:'a8', name:'100000 монет', icon:'🏦', desc:'Серьёзные деньги!', check: s => s.totalCoins >= 100000 },
  { id:'a9', name:'Первый апгрейд', icon:'⬆️', desc:'Купи улучшение', check: s => s.totalUpgrades >= 1 },
  { id:'a10', name:'10 апгрейдов', icon:'🛒', desc:'Купи 10 улучшений', check: s => s.totalUpgrades >= 10 },
  { id:'a11', name:'Пассивный доход', icon:'😴', desc:'Получай монеты пассивно', check: s => s.cps >= 1 },
  { id:'a12', name:'Стахановец', icon:'⭐', desc:'10 монет в секунду', check: s => s.cps >= 10 },
  { id:'a13', name:'Первый престиж', icon:'🔥', desc:'Сделай престиж', check: s => s.prestiges >= 1 },
  { id:'a14', name:'Ветеран', icon:'🎖️', desc:'3 престижа', check: s => s.prestiges >= 3 },
  { id:'a15', name:'Уровень 5', icon:'🏅', desc:'Достигни 5-го уровня', check: s => s.level >= 5 },
  { id:'a16', name:'АБСОЛЮТ', icon:'👑', desc:'Достигни макс. уровня', check: s => s.level >= 10 },
];

// ==================== STATE ====================
let state = {
  coins: 0,
  totalCoins: 0,
  totalClicks: 0,
  totalUpgrades: 0,
  prestiges: 0,
  prestigeMultiplier: 1.0,
  level: 1,
  xp: 0,
  energy: 100,
  maxEnergy: 100,
  energyRegen: 2,
  cpc: 1,
  cps: 0,
  cpsRaw: 0,
  playTime: 0,
  maxCps: 0,
  maxCpc: 1,
  upgradeLevels: {},
  unlockedAchs: [],
};

function loadState() {
  try {
    const raw = localStorage.getItem('gymClickerState');
    if (raw) {
      const saved = JSON.parse(raw);
      Object.assign(state, saved);
    }
  } catch(e) {}
}

function saveState() {
  state.lastSeen = Date.now();
  localStorage.setItem('gymClickerState', JSON.stringify(state));
}

function getUpgradeLevel(id) {
  return state.upgradeLevels[id] || 0;
}

function getUpgradePrice(upg) {
  const lvl = getUpgradeLevel(upg.id);
  return Math.floor(upg.basePrice * Math.pow(upg.priceGrowth, lvl));
}

function recalcStats() {
  let cpc = 1;
  let cps = 0;
  let maxEnergy = 100;
  let energyRegen = 2;

  for (const upg of CLICK_UPGRADES) {
    const lvl = getUpgradeLevel(upg.id);
    if (lvl > 0) cpc += upg.value * lvl;
  }

  for (const upg of ENERGY_UPGRADES) {
    const lvl = getUpgradeLevel(upg.id);
    if (lvl > 0) {
      if (upg.effect === 'maxEnergy') maxEnergy += upg.value * lvl;
      if (upg.effect === 'energyRegen') energyRegen += upg.value * lvl;
    }
  }

  for (const upg of PASSIVE_UPGRADES) {
    const lvl = getUpgradeLevel(upg.id);
    if (lvl > 0) cps += upg.value * lvl;
  }

  state.cpc = Math.floor(cpc * state.prestigeMultiplier);
  state.cpsRaw = cps;
  state.cps = parseFloat((cps * state.prestigeMultiplier).toFixed(1));
  state.maxEnergy = maxEnergy;
  state.energyRegen = energyRegen;
  if (state.energy > state.maxEnergy) state.energy = state.maxEnergy;
  if (state.cps > state.maxCps) state.maxCps = state.cps;
  if (state.cpc > state.maxCpc) state.maxCpc = state.cpc;
}

// ==================== RENDER ====================
function formatNum(n) {
  if (n >= 1e12) return (n/1e12).toFixed(1) + 'T';
  if (n >= 1e9) return (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(1) + 'K';
  return Math.floor(n).toString();
}

function updateHUD() {
  document.getElementById('coinsDisplay').textContent = formatNum(state.coins);
  document.getElementById('cpcDisplay').textContent = '+' + formatNum(state.cpc);
  document.getElementById('cpsDisplay').textContent = formatNum(state.cps);
  document.getElementById('prestigeDisplay').textContent = '×' + state.prestigeMultiplier.toFixed(1);
  const cph = state.cps * 3600;
  document.getElementById('cphDisplay').textContent = formatNum(cph);

  const energyPct = (state.energy / state.maxEnergy) * 100;
  document.getElementById('energyFill').style.width = energyPct + '%';
  document.getElementById('energyCount').textContent = Math.floor(state.energy) + ' / ' + state.maxEnergy;

  const lvl = state.level - 1;
  const nextLvl = lvl + 1;
  const curXpReq = LEVELS[lvl] ? LEVELS[lvl].xp : 0;
  const nextXpReq = LEVELS[nextLvl] ? LEVELS[nextLvl].xp : LEVELS[LEVELS.length-1].xp + 999999;
  const xpInLevel = state.xp - curXpReq;
  const xpNeeded = nextXpReq - curXpReq;
  const pct = Math.min(100, (xpInLevel / xpNeeded) * 100);
  document.getElementById('xpFill').style.width = pct + '%';
  document.getElementById('xpInfo').textContent = formatNum(xpInLevel) + ' / ' + formatNum(xpNeeded);
  document.getElementById('levelNum').textContent = state.level;
  document.getElementById('levelName').textContent = LEVELS[state.level-1]?.name || 'АБСОЛЮТ';

  // prestige
  const prestigeReq = getPrestigeReq();
  document.getElementById('prestigeReq').textContent = formatNum(prestigeReq);
  document.getElementById('prestigeBtn').disabled = state.totalCoins < prestigeReq;

  // stats page
  document.getElementById('s-totalCoins').textContent = formatNum(state.totalCoins);
  document.getElementById('s-totalClicks').textContent = formatNum(state.totalClicks);
  document.getElementById('s-prestiges').textContent = state.prestiges;
  const mins = Math.floor(state.playTime / 60);
  const hrs = Math.floor(mins / 60);
  document.getElementById('s-playTime').textContent = hrs > 0 ? hrs + 'ч' : mins + 'м';
  document.getElementById('s-maxCps').textContent = formatNum(state.maxCps);
  document.getElementById('s-maxCpc').textContent = '+' + formatNum(state.maxCpc);
}

function renderUpgrades() {
  renderUpgradeList('clickUpgradesList', CLICK_UPGRADES);
  renderUpgradeList('energyUpgradesList', ENERGY_UPGRADES);
  renderUpgradeList('passiveUpgradesList', PASSIVE_UPGRADES);
  renderPrestige();
  renderAchievements();
}

function renderUpgradeList(containerId, upgrades) {
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  for (const upg of upgrades) {
    const lvl = getUpgradeLevel(upg.id);
    const price = getUpgradePrice(upg);
    const maxed = lvl >= upg.maxLevel;
    const affordable = !maxed && state.coins >= price;
    
    let effectText = '';
    if (upg.effect === 'cpc') effectText = `+${upg.value} за клик`;
    if (upg.effect === 'cps') {
      const perHour = upg.value * 3600;
      effectText = `+${upg.value}/сек · +${formatNum(perHour)}/ч`;
    }
    if (upg.effect === 'maxEnergy') effectText = `+${upg.value} энергии`;
    if (upg.effect === 'energyRegen') effectText = `+${upg.value} восст./сек`;

    el.innerHTML += `
      <div class="upgrade-card ${affordable?'affordable':''} ${maxed?'maxed':''}" onclick="buyUpgrade('${upg.id}')">
        <div class="upgrade-icon">${upg.icon}</div>
        <div class="upgrade-info">
          <div class="upgrade-name">${upg.name}</div>
          <div class="upgrade-desc">${upg.desc} • ${effectText}</div>
          <div class="upgrade-level">Уровень ${lvl} / ${upg.maxLevel}</div>
        </div>
        <div class="upgrade-price">
          ${maxed 
            ? '<span class="price-val" style="color:var(--green)">МАКС</span>'
            : `<span class="price-val ${affordable?'':'cant-afford'}">${formatNum(price)}</span>
               <span class="price-lbl">монет</span>`
          }
        </div>
      </div>`;
  }
}

function renderPrestige() {
  const el = document.getElementById('prestigeList');
  el.innerHTML = '<div class="section-title">Ваши престижи</div>';
  if (state.prestiges === 0) {
    el.innerHTML += '<div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">Ещё не делал престиж</div>';
    return;
  }
  el.innerHTML += `<div class="upgrade-card affordable">
    <div class="upgrade-icon">🔥</div>
    <div class="upgrade-info">
      <div class="upgrade-name">Ветеран Зала</div>
      <div class="upgrade-desc">Ты прошёл ${state.prestiges} раз</div>
      <div class="upgrade-level">Множитель: ×${state.prestigeMultiplier.toFixed(1)}</div>
    </div>
  </div>`;
}

function renderAchievements() {
  const el = document.getElementById('achievementsList');
  el.innerHTML = '';
  for (const ach of ACHIEVEMENTS) {
    const unlocked = state.unlockedAchs.includes(ach.id);
    el.innerHTML += `
      <div class="achievement-card ${unlocked?'unlocked':''}">
        <div class="ach-icon">${ach.icon}</div>
        <div class="ach-info">
          <div class="ach-name">${ach.name}</div>
          <div class="ach-desc">${unlocked ? ach.desc : '???'}</div>
        </div>
      </div>`;
  }
}

// ==================== ACTIONS ====================
function handleClick(x, y) {
  if (state.energy < 1) {
    showNotif('⚡ Нет энергии!');
    return;
  }
  state.energy = Math.max(0, state.energy - 1);
  const earned = state.cpc;
  state.coins += earned;
  state.totalCoins += earned;
  state.totalClicks++;
  state.xp += 1;

  checkLevelUp();
  checkAchievements();

  spawnFloatText('+' + formatNum(earned), x, y);
  spawnRipple(x, y);

  updateHUD();
  renderUpgrades();
}

function setupCoinButton() {
  const btn = document.getElementById('coinBtn');

  // Мультитач — каждый палец считается отдельным кликом
  btn.addEventListener('touchstart', (e) => {
    e.preventDefault(); // блокируем скролл и задержку 300ms
    const btn = e.currentTarget;
    btn.classList.add('clicking');
    setTimeout(() => btn.classList.remove('clicking'), 80);

    for (const touch of e.changedTouches) {
      handleClick(touch.clientX, touch.clientY);
    }
  }, { passive: false });

  // Фолбэк для мыши на десктопе
  btn.addEventListener('mousedown', (e) => {
    handleClick(e.clientX, e.clientY);
    btn.classList.add('clicking');
    setTimeout(() => btn.classList.remove('clicking'), 80);
  });
}

function spawnFloatText(txt, x, y) {
  const el = document.createElement('div');
  el.className = 'float-text';
  el.textContent = txt;
  el.style.left = (x - 20 + Math.random()*40 - 20) + 'px';
  el.style.top = (y - 20) + 'px';
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1000);
}

function spawnRipple(x, y) {
  const el = document.createElement('div');
  el.className = 'ripple';
  el.style.left = (x - 25) + 'px';
  el.style.top = (y - 25) + 'px';
  el.style.width = '50px';
  el.style.height = '50px';
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 500);
}

function buyUpgrade(id) {
  const allUpgrades = [...CLICK_UPGRADES, ...ENERGY_UPGRADES, ...PASSIVE_UPGRADES];
  const upg = allUpgrades.find(u => u.id === id);
  if (!upg) return;
  const lvl = getUpgradeLevel(id);
  if (lvl >= upg.maxLevel) return;
  const price = getUpgradePrice(upg);
  if (state.coins < price) {
    showNotif('💸 Недостаточно монет!');
    return;
  }
  state.coins -= price;
  state.upgradeLevels[id] = lvl + 1;
  state.totalUpgrades++;
  state.xp += 10;
  recalcStats();
  checkLevelUp();
  checkAchievements();
  updateHUD();
  renderUpgrades();
  showNotif(`✅ ${upg.name} — Ур.${lvl+1}`);
}

function getPrestigeReq() {
  return 100000 * Math.pow(5, state.prestiges);
}

function doPrestige() {
  const req = getPrestigeReq();
  if (state.totalCoins < req) return;
  state.prestiges++;
  state.prestigeMultiplier = 1 + state.prestiges * 0.5;
  state.coins = 0;
  state.xp = 0;
  state.level = 1;
  state.energy = state.maxEnergy;
  state.upgradeLevels = {};
  recalcStats();
  checkAchievements();
  updateHUD();
  renderUpgrades();
  showNotif('🔥 ПРЕСТИЖ! Множитель ×' + state.prestigeMultiplier.toFixed(1));
}

function checkLevelUp() {
  while (state.level < LEVELS.length) {
    const next = LEVELS[state.level];
    if (!next) break;
    if (state.xp >= next.xp) {
      state.level++;
      showNotif('🎉 Уровень ' + state.level + ' — ' + LEVELS[state.level-1].name);
    } else break;
  }
}

function checkAchievements() {
  for (const ach of ACHIEVEMENTS) {
    if (state.unlockedAchs.includes(ach.id)) continue;
    const checkState = {
      totalClicks: state.totalClicks,
      totalCoins: state.totalCoins,
      prestiges: state.prestiges,
      level: state.level,
      cps: state.cps,
      totalUpgrades: state.totalUpgrades,
    };
    if (ach.check(checkState)) {
      state.unlockedAchs.push(ach.id);
      showAchPopup(ach);
    }
  }
}

// ==================== NOTIFICATIONS ====================
let notifTimer = null;
function showNotif(msg) {
  const el = document.getElementById('notif');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(notifTimer);
  notifTimer = setTimeout(() => el.classList.remove('show'), 2000);
}

let achQueue = [];
let achShowing = false;
function showAchPopup(ach) {
  achQueue.push(ach);
  if (!achShowing) processAchQueue();
}
function processAchQueue() {
  if (achQueue.length === 0) { achShowing = false; return; }
  achShowing = true;
  const ach = achQueue.shift();
  const popup = document.getElementById('achPopup');
  document.getElementById('achPopupIcon').textContent = ach.icon;
  document.getElementById('achPopupName').textContent = ach.name;
  popup.classList.add('show');
  setTimeout(() => {
    popup.classList.remove('show');
    setTimeout(processAchQueue, 400);
  }, 2500);
}

// ==================== TABS ====================
function switchTab(id) {
  document.querySelectorAll('.tab-btn').forEach((b,i) => {
    b.classList.toggle('active', ['click','passive','stats','ach'][i] === id);
  });
  document.querySelectorAll('.panel-content').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
}

// ==================== GAME LOOP ====================
let lastTick = Date.now();
setInterval(() => {
  const now = Date.now();
  const dt = (now - lastTick) / 1000;
  lastTick = now;

  // Passive income
  if (state.cps > 0) {
    const earned = state.cps * dt;
    state.coins += earned;
    state.totalCoins += earned;
    state.xp += earned * 0.1;
    checkLevelUp();
  }

  // Energy regen
  state.energy = Math.min(state.maxEnergy, state.energy + state.energyRegen * dt);

  // No energy indicator
  const btn = document.getElementById('coinBtn');
  btn.classList.toggle('no-energy', state.energy < 1);

  state.playTime += dt;
  updateHUD();
}, 100);

// Save every 5s
setInterval(() => saveState(), 5000);

// Re-render upgrades every 1s (for affordability highlight)
setInterval(() => renderUpgrades(), 1000);

// ==================== OFFLINE EARNINGS ====================
function calcOfflineEarnings() {
  if (!state.lastSeen || state.cps <= 0) return;
  const now = Date.now();
  const elapsed = (now - state.lastSeen) / 1000; // seconds
  const MIN_OFFLINE = 30; // меньше 30 сек — не показываем
  const MAX_OFFLINE = 2 * 60 * 60; // 2 часа макс
  if (elapsed < MIN_OFFLINE) return;
  const seconds = Math.min(elapsed, MAX_OFFLINE);
  const earned = Math.floor(state.cps * seconds);
  if (earned <= 0) return;

  // Format time string
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  let timeStr = '';
  if (hrs > 0) timeStr += hrs + ' ч ';
  if (mins > 0) timeStr += mins + ' мин ';
  if (hrs === 0 && secs > 0) timeStr += secs + ' сек';

  document.getElementById('offlineTime').textContent = 'Отсутствовал: ' + timeStr.trim();
  document.getElementById('offlineEarned').textContent = '+' + formatNum(earned);
  document.getElementById('offlineOverlay').style.display = 'flex';

  // Store earned amount to apply on close
  window._offlineEarned = earned;
}

function closeOfflinePopup() {
  const earned = window._offlineEarned || 0;
  state.coins += earned;
  state.totalCoins += earned;
  state.xp += earned * 0.05;
  checkLevelUp();
  checkAchievements();
  updateHUD();
  renderUpgrades();
  document.getElementById('offlineOverlay').style.display = 'none';
  showNotif('💰 Получено ' + formatNum(earned) + ' монет!');
}

// Save timestamp when user leaves
window.addEventListener('beforeunload', () => saveState());
document.addEventListener('visibilitychange', () => {
  if (document.hidden) saveState();
  else {
    // Came back — check offline earnings
    recalcStats();
    calcOfflineEarnings();
  }
});

// ==================== INIT ====================
loadState();
recalcStats();
calcOfflineEarnings();
setupCoinButton();
updateHUD();
renderUpgrades();

// Telegram WebApp init
if (window.Telegram && window.Telegram.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}
</script>
</body>
</html>
"""

# ─── Веб-сервер ───────────────────────────────────────────────────────────────
class GameHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Frame-Options", "ALLOWALL")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def log_message(self, fmt, *args):
        logger.info("[WEB] %s - %s", self.address_string(), fmt % args)


def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), GameHandler)
    logger.info("[WEB] Игра запущена на http://0.0.0.0:%s", PORT)
    server.serve_forever()


# ─── Telegram бот ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("💪 Играть в Качалку!", web_app=WebAppInfo(url=GAME_URL))]]
    await update.message.reply_text(
        f"Привет, {user.first_name}! 💪\n\n"
        "🏋️ *Качалка Кликер* — прокачай своего качка!\n\n"
        "• Тыкай на монету с бицепсом 💪\n"
        "• Покупай улучшения для больших монет\n"
        "• Разблокируй пассивный доход\n"
        "• Делай престиж для множителей 🔥\n\n"
        "Нажми кнопку ниже чтобы начать!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏋️ *Как играть:*\n\n"
        "1. Нажимай на монету 💪 — тратит энергию, даёт монеты\n"
        "2. Вкладка *КЛИК* — больше монет за тык\n"
        "3. Вкладка *ПАССИВ* — монеты капают сами (виден доход /ч)\n"
        "4. Вкладка *СТАТ* — твоя статистика\n"
        "5. Вкладка *АЧИВ* — 16 достижений\n\n"
        "🔥 Накопи 100.000 монет → делай *Престиж* для множителя!\n"
        "💤 Оффлайн доход — до 2 часов пока не играешь",
        parse_mode="Markdown",
    )


def run_bot():
    if BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        logger.error("Укажи BOT_TOKEN в .env файле!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    logger.info("[BOT] Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# ─── Точка входа ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Веб-сервер в фоновом потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    # Бот в основном потоке
    run_bot()

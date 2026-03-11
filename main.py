"""
main.py — Качалка Кликер Telegram Mini App
Запуск: pip install -r requirements.txt && python main.py
Docker: docker compose up -d
"""
import os, json, logging, sqlite3, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Настройки ─────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
GAME_URL  = os.environ.get("GAME_URL",  "https://ВАШ_ДОМЕН")
PORT      = int(os.environ.get("PORT", 8080))
DB_PATH   = os.environ.get("DB_PATH",  "leaderboard.db")
# ──────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── HTML игры ─────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>💪 Качалка</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0; padding: 0;
  -webkit-tap-highlight-color: transparent;
}
:root {
  --bg:      #0d0d16;
  --panel:   #161624;
  --panel2:  #1e1e30;
  --gold:    #ffd700;
  --gold2:   #ff9900;
  --orange:  #ff6200;
  --green:   #39ff14;
  --red:     #ff2244;
  --text:    #f0e6d3;
  --muted:   #6b6480;
  --font:    'Nunito', sans-serif;
}
html, body {
  width: 100%; min-height: 100vh;
  background: var(--bg); color: var(--text);
  font-family: var(--font); overflow-x: hidden;
}

/* ── HEADER ── */
#header {
  position: sticky; top: 0; z-index: 50;
  background: rgba(13,13,22,0.97);
  border-bottom: 1px solid rgba(255,215,0,0.08);
  padding: 10px 14px 8px;
  display: flex; justify-content: space-between; align-items: center;
}
.hdr-left { display:flex; flex-direction:column; }
.hdr-lvl-label { font-size:10px; color:var(--muted); letter-spacing:2px; text-transform:uppercase; }
.hdr-lvl-name  { font-size:17px; font-weight:900; color:var(--gold); line-height:1.1; }
.hdr-right { display:flex; flex-direction:column; align-items:flex-end; gap:1px; }
.hdr-coins { font-size:22px; font-weight:900; color:var(--gold); line-height:1; }
.hdr-coins-lbl { font-size:10px; color:var(--muted); }
.hdr-cph   { font-size:13px; font-weight:800; color:var(--green); }
.hdr-cph-lbl { font-size:10px; color:var(--muted); }

/* ── XP BAR ── */
#xpbar {
  padding: 5px 14px 8px;
  background: rgba(13,13,22,0.7);
}
.xp-row { display:flex; justify-content:space-between; font-size:10px; color:var(--muted); margin-bottom:4px; }
.xp-track { height:5px; background:rgba(255,255,255,0.07); border-radius:3px; overflow:hidden; }
.xp-fill  { height:100%; background:linear-gradient(90deg,var(--orange),var(--gold)); border-radius:3px; transition:width .4s ease; }

/* ── STATS ROW ── */
#statsrow {
  display:flex; gap:8px; padding:8px 14px;
}
.stat-chip {
  flex:1; background:var(--panel);
  border:1px solid rgba(255,215,0,0.1); border-radius:10px;
  padding:8px 6px; text-align:center;
}
.stat-chip-val { font-size:16px; font-weight:900; color:var(--gold); line-height:1; }
.stat-chip-lbl { font-size:10px; color:var(--muted); margin-top:2px; }

/* ── CLICKER AREA ── */
#clicker {
  display:flex; flex-direction:column; align-items:center;
  padding:14px 14px 8px;
}
.energy-row { width:100%; max-width:320px; margin-bottom:14px; }
.energy-top { display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px; }
.energy-lbl { color:var(--orange); font-weight:800; letter-spacing:1px; }
.energy-val { color:var(--text); }
.energy-track { height:7px; background:rgba(255,255,255,0.07); border-radius:4px; overflow:hidden; border:1px solid rgba(255,100,0,0.15); }
.energy-fill  { height:100%; background:linear-gradient(90deg,#ff3c00,var(--orange),#ffaa00); border-radius:4px; transition:width .15s linear; }

/* ── COIN BUTTON ── */
.coin-wrap { position:relative; display:flex; align-items:center; justify-content:center; margin:4px 0; }
.coin-glow {
  position:absolute; width:210px; height:210px; border-radius:50%; pointer-events:none;
  background:radial-gradient(circle,rgba(255,200,0,0.18) 0%,transparent 70%);
  animation:glowpulse 2s ease-in-out infinite;
}
@keyframes glowpulse {
  0%,100%{transform:scale(1);opacity:.8;}
  50%{transform:scale(1.12);opacity:1;}
}
#coinBtn {
  width:175px; height:175px; border-radius:50%; border:none;
  cursor:pointer; position:relative; z-index:10;
  font-size:78px; line-height:1;
  display:flex; align-items:center; justify-content:center;
  touch-action:manipulation;
  -webkit-user-select:none; user-select:none;
  /* default gold skin */
  background:
    radial-gradient(circle at 35% 30%, rgba(255,255,180,0.55) 0%, transparent 50%),
    radial-gradient(circle at 70% 72%, rgba(170,90,0,0.3) 0%, transparent 50%),
    linear-gradient(135deg,#f5c518 0%,#e8a800 25%,#ffd700 50%,#cc8800 75%,#e8a800 100%);
  box-shadow:
    0 0 0 4px rgba(255,200,0,.28),
    0 0 30px rgba(255,175,0,.4),
    0 8px 30px rgba(0,0,0,.6),
    inset 0 3px 8px rgba(255,255,180,.4),
    inset 0 -4px 8px rgba(120,55,0,.3);
  transition:transform .08s ease, filter .2s ease;
}
#coinBtn.tap  { transform:scale(.9); }
#coinBtn.nrg  { filter:grayscale(.7) brightness(.5); }

@keyframes abounce { 0%,100%{transform:scale(1) rotate(0)} 30%{transform:scale(1.08) rotate(-4deg)} 70%{transform:scale(1.08) rotate(4deg)} }
@keyframes aspin   { from{transform:rotate(0)} to{transform:rotate(360deg)} }
@keyframes apulse  { 0%,100%{transform:scale(1)} 50%{transform:scale(1.07)} }
@keyframes ashake  { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-5px) rotate(-2deg)} 75%{transform:translateX(5px) rotate(2deg)} }
#coinBtn.anim-bounce.tap { animation:abounce .3s ease; transform:none; }
#coinBtn.anim-spin.tap   { animation:aspin .4s linear; transform:none; }
#coinBtn.anim-pulse.tap  { animation:apulse .25s ease; transform:none; }
#coinBtn.anim-shake.tap  { animation:ashake .3s ease; transform:none; }

/* ── FLOAT TEXT ── */
.floatxt {
  position:fixed; pointer-events:none; z-index:9999;
  font-size:20px; font-weight:900; color:var(--gold);
  text-shadow:0 0 10px rgba(255,200,0,.9),0 2px 4px rgba(0,0,0,.9);
  animation:floatup .9s ease-out forwards;
}
@keyframes floatup {
  0%{opacity:1;transform:translateY(0) scale(1);}
  50%{opacity:1;transform:translateY(-38px) scale(1.15);}
  100%{opacity:0;transform:translateY(-80px) scale(.8);}
}
.ripple {
  position:fixed; pointer-events:none; z-index:9998; border-radius:50%;
  background:rgba(255,200,0,.25); animation:ripout .45s ease-out forwards;
}
@keyframes ripout { 0%{transform:scale(0);opacity:.8;} 100%{transform:scale(3.5);opacity:0;} }

/* ── TABS ── */
#tabs {
  display:flex; gap:3px; padding:8px 14px 0; overflow-x:auto;
  scrollbar-width:none;
}
#tabs::-webkit-scrollbar { display:none; }
.tab {
  flex-shrink:0; padding:9px 10px;
  background:var(--panel); border:1px solid rgba(255,255,255,0.07); border-radius:10px;
  color:var(--muted); font-family:var(--font); font-size:11px; font-weight:700;
  cursor:pointer; transition:all .2s; white-space:nowrap;
}
.tab.on {
  background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,215,0,.1));
  border-color:rgba(255,215,0,.4); color:var(--gold);
}

/* ── PANELS ── */
.panel { display:none; padding:12px 14px 120px; }
.panel.on { display:block; }
.sec-title {
  font-size:10px; font-weight:800; letter-spacing:2.5px; color:var(--muted);
  text-transform:uppercase; margin:14px 0 10px;
  padding-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.05);
}
.sec-title:first-child { margin-top:4px; }

/* ── UPGRADE CARD ── */
.upg-card {
  background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:13px; padding:13px 12px;
  display:flex; align-items:center; gap:11px;
  margin-bottom:9px; cursor:pointer;
  transition:transform .15s, border-color .15s;
  position:relative; overflow:hidden;
}
.upg-card.can { border-color:rgba(255,215,0,.28); }
.upg-card.can::before {
  content:''; position:absolute; inset:0;
  background:linear-gradient(135deg,rgba(255,100,0,.04),rgba(255,215,0,.04));
}
.upg-card.maxed { opacity:.45; cursor:default; }
.upg-card:active:not(.maxed) { transform:scale(.975); }
.upg-ico  { width:50px; height:50px; border-radius:11px; flex-shrink:0; font-size:26px; display:flex; align-items:center; justify-content:center; background:rgba(255,215,0,.07); border:1px solid rgba(255,215,0,.12); }
.upg-info { flex:1; min-width:0; }
.upg-name { font-size:13px; font-weight:800; color:var(--text); margin-bottom:3px; }
.upg-desc { font-size:11px; color:var(--muted); line-height:1.3; }
.upg-lvl  { font-size:10px; color:var(--orange); font-weight:700; margin-top:3px; }
.upg-price { flex-shrink:0; text-align:right; }
.upg-pval { font-size:13px; font-weight:900; color:var(--gold); }
.upg-pval.no { color:var(--red); }
.upg-plbl { font-size:10px; color:var(--muted); }

/* ── PRESTIGE BOX ── */
.prestige-box {
  background:linear-gradient(135deg,rgba(255,100,0,.1),rgba(255,215,0,.07));
  border:1px solid rgba(255,215,0,.2); border-radius:15px;
  padding:18px; text-align:center; margin-bottom:14px;
}
.prestige-title { font-size:18px; font-weight:900; color:var(--gold); margin-bottom:6px; }
.prestige-desc  { font-size:12px; color:var(--muted); line-height:1.5; margin-bottom:14px; }
.prestige-btn {
  background:linear-gradient(135deg,var(--orange),var(--gold));
  border:none; border-radius:12px; padding:13px 28px;
  font-family:var(--font); font-size:15px; font-weight:900; color:#000;
  cursor:pointer; box-shadow:0 4px 18px rgba(255,100,0,.4);
  transition:transform .1s;
}
.prestige-btn:active { transform:scale(.97); }
.prestige-btn:disabled { opacity:.35; cursor:not-allowed; }

/* ── STATS GRID ── */
.stats-grid { display:grid; grid-template-columns:1fr 1fr; gap:9px; }
.stat-card { background:var(--panel); border:1px solid rgba(255,255,255,.05); border-radius:12px; padding:13px; }
.stat-card-val { font-size:19px; font-weight:900; color:var(--gold); }
.stat-card-lbl { font-size:11px; color:var(--muted); margin-top:3px; }

/* ── ACHIEVEMENTS ── */
.ach-card {
  background:var(--panel); border:1px solid rgba(255,255,255,.05);
  border-radius:13px; padding:12px; margin-bottom:8px;
  display:flex; align-items:center; gap:11px; opacity:.35;
}
.ach-card.done { opacity:1; border-color:rgba(255,215,0,.25); background:linear-gradient(135deg,rgba(255,100,0,.06),rgba(255,215,0,.04)); }
.ach-ico  { font-size:26px; flex-shrink:0; }
.ach-name { font-size:13px; font-weight:800; }
.ach-desc { font-size:11px; color:var(--muted); margin-top:2px; }

/* ── LEADERBOARD ── */
.lb-myrow {
  background:rgba(57,255,20,.06); border:1px solid rgba(57,255,20,.2);
  border-radius:12px; padding:11px 14px; margin-bottom:12px;
  display:flex; justify-content:space-between; align-items:center;
}
.lb-mylbl { font-size:11px; color:var(--green); font-weight:800; letter-spacing:1px; }
.lb-myval { font-size:16px; font-weight:900; color:var(--gold); }
.lb-refresh {
  width:100%; padding:11px; border-radius:11px; border:1px solid rgba(255,100,0,.3);
  background:rgba(255,100,0,.1); color:var(--orange); font-family:var(--font);
  font-size:13px; font-weight:700; cursor:pointer; margin-bottom:12px;
  transition:background .15s;
}
.lb-refresh:active { background:rgba(255,100,0,.22); }

/* podium */
.podium-wrap { text-align:center; padding:6px 0 18px; }
.podium-htitle { font-size:10px; font-weight:800; letter-spacing:3px; color:var(--muted); text-transform:uppercase; margin-bottom:14px; }
.podium-stage { display:flex; align-items:flex-end; justify-content:center; gap:6px; margin-bottom:4px; }
.podium-slot  { display:flex; flex-direction:column; align-items:center; flex:1; max-width:105px; }
.podium-crown { font-size:16px; margin-bottom:2px; min-height:20px; }
.podium-circle {
  border-radius:50%; display:flex; align-items:center; justify-content:center;
  box-shadow:0 4px 14px rgba(0,0,0,.5); margin-bottom:5px; flex-shrink:0;
}
.p1 .podium-circle { width:78px; height:78px; font-size:42px; background:linear-gradient(135deg,#f5c518,#ffd700,#d4a010); box-shadow:0 0 22px rgba(255,200,0,.55),0 4px 14px rgba(0,0,0,.5); }
.p2 .podium-circle { width:62px; height:62px; font-size:32px; background:linear-gradient(135deg,#bdbdbd,#e0e0e0,#9e9e9e); box-shadow:0 0 14px rgba(200,200,200,.4),0 4px 12px rgba(0,0,0,.5); }
.p3 .podium-circle { width:54px; height:54px; font-size:28px; background:linear-gradient(135deg,#bf7b3b,#d4924a,#9e5e1e); box-shadow:0 0 12px rgba(200,130,60,.4),0 4px 12px rgba(0,0,0,.5); }
.podium-name { font-size:11px; font-weight:800; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; width:100%; margin-bottom:2px; }
.podium-cph  { font-size:10px; color:var(--gold); font-weight:700; }
.podium-block { border-radius:9px 9px 0 0; width:100%; height:0; display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:900; color:rgba(0,0,0,.35); }
.p1 .podium-block { height:66px; background:linear-gradient(180deg,#c49a00,#a07800); }
.p2 .podium-block { height:48px; background:linear-gradient(180deg,#8f8f8f,#6e6e6e); }
.p3 .podium-block { height:36px; background:linear-gradient(180deg,#8f5a18,#6a3e0c); }
.podium-divider { height:1px; background:rgba(255,255,255,.05); margin:2px 0 14px; }

.lb-row {
  background:var(--panel); border:1px solid rgba(255,255,255,.05); border-radius:11px;
  padding:11px 13px; margin-bottom:7px; display:flex; align-items:center; gap:10px;
}
.lb-row.me { border-color:rgba(57,255,20,.35); background:linear-gradient(135deg,rgba(57,255,20,.06),transparent); }
.lb-rank   { width:28px; text-align:center; font-size:14px; font-weight:900; color:var(--muted); flex-shrink:0; }
.lb-name   { flex:1; font-size:13px; font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.lb-row.me .lb-name { color:var(--green); }
.lb-rcph   { font-size:13px; font-weight:900; color:var(--gold); flex-shrink:0; }
.lb-prestige { font-size:10px; color:var(--muted); text-align:right; }
.lb-empty  { text-align:center; padding:36px 20px; color:var(--muted); font-size:13px; line-height:1.7; }

/* ── SKINS ── */
.skin-grid { display:grid; grid-template-columns:1fr 1fr; gap:9px; }
.skin-card {
  background:var(--panel); border:2px solid rgba(255,255,255,.06); border-radius:14px;
  padding:13px 10px; display:flex; flex-direction:column; align-items:center; gap:7px;
  cursor:pointer; position:relative; overflow:hidden; transition:transform .15s, border-color .15s;
}
.skin-card.can      { border-color:rgba(255,215,0,.28); }
.skin-card.owned    { border-color:rgba(57,255,20,.3); }
.skin-card.equipped { border-color:rgba(57,255,20,.75); background:linear-gradient(135deg,rgba(57,255,20,.07),transparent); }
.skin-card.locked   { opacity:.5; }
.skin-card:active:not(.locked) { transform:scale(.97); }
.skin-preview { width:68px; height:68px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:34px; flex-shrink:0; }
.skin-name  { font-size:12px; font-weight:800; text-align:center; color:var(--text); line-height:1.2; }
.skin-price { font-size:11px; font-weight:700; color:var(--gold); }
.skin-price.no { color:var(--red); }
.skin-badge { position:absolute; top:5px; right:5px; font-size:9px; font-weight:800; padding:2px 6px; border-radius:20px; letter-spacing:.5px; }
.badge-eq   { background:rgba(57,255,20,.2); color:var(--green); }
.badge-own  { background:rgba(57,255,20,.12); color:var(--green); }
.badge-lock { background:rgba(255,255,255,.07); color:var(--muted); }

/* ── NOTIFICATION ── */
#notif {
  position:fixed; top:66px; left:50%; transform:translateX(-50%) translateY(-14px);
  background:linear-gradient(135deg,var(--orange),var(--gold));
  color:#000; font-weight:900; font-size:13px;
  padding:9px 20px; border-radius:30px; z-index:9999;
  opacity:0; pointer-events:none; transition:all .25s;
  white-space:nowrap; box-shadow:0 4px 18px rgba(255,100,0,.45);
}
#notif.show { opacity:1; transform:translateX(-50%) translateY(0); }

/* ── ACH POPUP ── */
#achpop {
  position:fixed; bottom:-90px; left:50%; transform:translateX(-50%);
  background:var(--panel2); border:1px solid rgba(255,215,0,.35);
  border-radius:16px; padding:13px 20px;
  display:flex; align-items:center; gap:12px;
  z-index:9999; transition:bottom .35s cubic-bezier(.175,.885,.32,1.275);
  box-shadow:0 -4px 26px rgba(255,200,0,.12); min-width:270px;
}
#achpop.show { bottom:18px; }
#achpop-icon { font-size:34px; }
.achpop-lbl  { font-size:10px; color:var(--gold); letter-spacing:2px; font-weight:800; }
.achpop-name { font-size:14px; font-weight:900; }

/* ── OFFLINE POPUP ── */
#offpop {
  position:fixed; inset:0; z-index:99998; display:none;
  align-items:center; justify-content:center;
  background:rgba(0,0,0,.85); backdrop-filter:blur(7px);
}
#offpop.show { display:flex; }
.offmodal {
  background:var(--panel2); border:1px solid rgba(255,215,0,.3);
  border-radius:22px; padding:30px 26px; text-align:center;
  width:88%; max-width:320px;
  box-shadow:0 0 50px rgba(255,200,0,.12),0 20px 50px rgba(0,0,0,.65);
  animation:popin .35s cubic-bezier(.175,.885,.32,1.275);
}
@keyframes popin { from{transform:scale(.7);opacity:0;} to{transform:scale(1);opacity:1;} }
.off-icon  { font-size:52px; margin-bottom:10px; animation:snore 2s ease-in-out infinite; }
@keyframes snore { 0%,100%{transform:translateY(0);} 50%{transform:translateY(-5px);} }
.off-title { font-size:15px; font-weight:900; margin-bottom:4px; }
.off-time  { font-size:12px; color:var(--muted); margin-bottom:16px; }
.off-earn-lbl { font-size:11px; color:var(--muted); letter-spacing:1px; margin-bottom:4px; }
.off-earn { font-size:40px; font-weight:900; color:var(--gold); text-shadow:0 0 24px rgba(255,200,0,.5); margin-bottom:8px; line-height:1; }
.off-note { font-size:11px; color:var(--muted); margin-bottom:20px; }
.off-btn {
  width:100%; padding:15px; border:none; border-radius:13px;
  background:linear-gradient(135deg,var(--orange),var(--gold));
  font-family:var(--font); font-size:16px; font-weight:900; color:#000;
  cursor:pointer; box-shadow:0 4px 18px rgba(255,140,0,.4); transition:transform .1s;
}
.off-btn:active { transform:scale(.97); }

/* ── NICKNAME POPUP ── */
#nickpop {
  position:fixed; inset:0; z-index:99999; display:none;
  align-items:center; justify-content:center;
  background:rgba(0,0,0,.9); backdrop-filter:blur(8px);
}
#nickpop.show { display:flex; }
.nickmodal {
  background:var(--panel2); border:1px solid rgba(255,215,0,.28);
  border-radius:22px; padding:32px 26px 26px; text-align:center;
  width:88%; max-width:330px;
  box-shadow:0 0 50px rgba(255,200,0,.1),0 20px 50px rgba(0,0,0,.7);
  animation:popin .35s cubic-bezier(.175,.885,.32,1.275);
}
.nick-icon  { font-size:56px; margin-bottom:10px; }
.nick-title { font-size:21px; font-weight:900; color:var(--gold); margin-bottom:5px; }
.nick-sub   { font-size:13px; color:var(--muted); margin-bottom:18px; line-height:1.4; }
.nick-input {
  width:100%; padding:13px 15px; border-radius:11px; outline:none;
  background:rgba(255,255,255,.06); border:2px solid rgba(255,215,0,.18);
  color:var(--text); font-family:var(--font); font-size:16px; font-weight:700;
  text-align:center; margin-bottom:7px; transition:border-color .2s;
  -webkit-appearance:none;
}
.nick-input:focus { border-color:rgba(255,215,0,.5); }
.nick-input::placeholder { color:var(--muted); font-weight:400; }
.nick-hint { font-size:11px; color:var(--red); min-height:16px; margin-bottom:14px; }
.nick-btn {
  width:100%; padding:15px; border:none; border-radius:13px;
  background:linear-gradient(135deg,var(--orange),var(--gold));
  font-family:var(--font); font-size:16px; font-weight:900; color:#000;
  cursor:pointer; box-shadow:0 4px 18px rgba(255,140,0,.4); transition:transform .1s;
}
.nick-btn:active { transform:scale(.97); }
</style>
</head>
<body>

<!-- HEADER -->
<div id="header">
  <div class="hdr-left">
    <span class="hdr-lvl-label">Уровень <span id="hLvlNum">1</span></span>
    <span class="hdr-lvl-name" id="hLvlName">Новичок</span>
  </div>
  <div class="hdr-right">
    <span class="hdr-coins" id="hCoins">0</span>
    <span class="hdr-coins-lbl">💰 МОНЕТ</span>
    <span class="hdr-cph" id="hCph">0</span>
    <span class="hdr-cph-lbl">📈 В ЧАС</span>
  </div>
</div>

<!-- XP -->
<div id="xpbar">
  <div class="xp-row">
    <span style="color:var(--orange);font-weight:800;letter-spacing:1px">ОПЫТ</span>
    <span id="xpTxt">0 / 100</span>
  </div>
  <div class="xp-track"><div class="xp-fill" id="xpFill" style="width:0%"></div></div>
</div>

<!-- STATS CHIPS -->
<div id="statsrow">
  <div class="stat-chip"><div class="stat-chip-val" id="sCpc">+1</div><div class="stat-chip-lbl">за клик</div></div>
  <div class="stat-chip"><div class="stat-chip-val" id="sCps">0</div><div class="stat-chip-lbl">/ сек</div></div>
  <div class="stat-chip"><div class="stat-chip-val" id="sMult">×1.0</div><div class="stat-chip-lbl">множитель</div></div>
</div>

<!-- CLICKER -->
<div id="clicker">
  <div class="energy-row">
    <div class="energy-top">
      <span class="energy-lbl">⚡ ЭНЕРГИЯ</span>
      <span class="energy-val" id="eCount">100 / 100</span>
    </div>
    <div class="energy-track"><div class="energy-fill" id="eFill" style="width:100%"></div></div>
  </div>
  <div class="coin-wrap">
    <div class="coin-glow" id="coinGlow"></div>
    <button id="coinBtn">💪</button>
  </div>
</div>

<!-- TABS -->
<div id="tabs">
  <button class="tab on"  data-tab="click">🖱 КЛИК</button>
  <button class="tab"     data-tab="passive">⏱ ПАССИВ</button>
  <button class="tab"     data-tab="stats">📊 СТАТ</button>
  <button class="tab"     data-tab="ach">🏆 АЧИВ</button>
  <button class="tab"     data-tab="top">👑 ТОП</button>
  <button class="tab"     data-tab="skins">🎨 СКИНЫ</button>
</div>

<!-- PANEL: CLICK -->
<div class="panel on" id="panel-click">
  <div class="sec-title">Усиления клика</div>
  <div id="list-click"></div>
  <div class="sec-title">Энергия</div>
  <div id="list-energy"></div>
</div>

<!-- PANEL: PASSIVE -->
<div class="panel" id="panel-passive">
  <div class="sec-title">Пассивный доход</div>
  <div id="list-passive"></div>
  <div class="sec-title">Престиж</div>
  <div class="prestige-box">
    <div class="prestige-title">🔥 ПРЕСТИЖ</div>
    <div class="prestige-desc">Сбрось прогресс и получи постоянный множитель.<br>Нужно: <strong id="presReq" style="color:var(--gold)">100,000</strong> монет всего</div>
    <button class="prestige-btn" id="presBtn" onclick="doPrestige()" disabled>ПРЕСТИЖ</button>
  </div>
</div>

<!-- PANEL: STATS -->
<div class="panel" id="panel-stats">
  <div class="sec-title">Статистика</div>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-card-val" id="st-tc">0</div><div class="stat-card-lbl">Всего монет</div></div>
    <div class="stat-card"><div class="stat-card-val" id="st-cl">0</div><div class="stat-card-lbl">Кликов</div></div>
    <div class="stat-card"><div class="stat-card-val" id="st-pr">0</div><div class="stat-card-lbl">Престижей</div></div>
    <div class="stat-card"><div class="stat-card-val" id="st-pt">0м</div><div class="stat-card-lbl">Время игры</div></div>
    <div class="stat-card"><div class="stat-card-val" id="st-mcps">0</div><div class="stat-card-lbl">Макс /сек</div></div>
    <div class="stat-card"><div class="stat-card-val" id="st-mcpc">+1</div><div class="stat-card-lbl">Макс за клик</div></div>
  </div>
</div>

<!-- PANEL: ACH -->
<div class="panel" id="panel-ach">
  <div class="sec-title">Достижения</div>
  <div id="list-ach"></div>
</div>

<!-- PANEL: TOP -->
<div class="panel" id="panel-top">
  <div class="lb-myrow" style="margin-top:6px">
    <span class="lb-mylbl">📈 МОЙ ДОХОД / ЧАС</span>
    <span class="lb-myval" id="lbMy">0</span>
  </div>
  <button class="lb-refresh" onclick="loadLB()">🔄 Обновить</button>
  <div id="lbPodium"></div>
  <div id="lbList"></div>
</div>

<!-- PANEL: SKINS -->
<div class="panel" id="panel-skins">
  <div class="sec-title">Скины монеты</div>
  <div class="skin-grid" id="skinList"></div>
</div>

<!-- NOTIFICATION -->
<div id="notif"></div>

<!-- ACH POPUP -->
<div id="achpop">
  <div id="achpop-icon">🏆</div>
  <div><div class="achpop-lbl">ДОСТИЖЕНИЕ!</div><div class="achpop-name" id="achpop-name">-</div></div>
</div>

<!-- OFFLINE POPUP -->
<div id="offpop">
  <div class="offmodal">
    <div class="off-icon">💤</div>
    <div class="off-title">Пока тебя не было...</div>
    <div class="off-time" id="offTime"></div>
    <div class="off-earn-lbl">КАЧАЛКА ЗАРАБОТАЛА:</div>
    <div class="off-earn" id="offEarn">+0</div>
    <div class="off-note">Оффлайн доход — максимум 2 часа</div>
    <button class="off-btn" onclick="claimOffline()">ЗАБРАТЬ 💰</button>
  </div>
</div>

<!-- NICKNAME POPUP -->
<div id="nickpop">
  <div class="nickmodal">
    <div class="nick-icon">💪</div>
    <div class="nick-title">Добро пожаловать!</div>
    <div class="nick-sub">Введи никнейм для таблицы лидеров</div>
    <input class="nick-input" id="nickInput" type="text" maxlength="20" placeholder="Твой никнейм..." autocomplete="off">
    <div class="nick-hint" id="nickHint"></div>
    <button class="nick-btn" onclick="saveNick()">В КАЧАЛКУ! 💪</button>
  </div>
</div>

<script>
// ═══════════════════════════════════════════
// DATA
// ═══════════════════════════════════════════
const LEVELS = [
  {name:'Новичок',xp:0},{name:'Любитель',xp:100},{name:'Спортсмен',xp:300},
  {name:'Атлет',xp:700},{name:'Культурист',xp:1500},{name:'Чемпион',xp:3500},
  {name:'Мастер',xp:8000},{name:'Легенда',xp:20000},{name:'Бог Железа',xp:50000},{name:'АБСОЛЮТ',xp:120000}
];

const UPG_CLICK = [
  {id:'c1',name:'Протеиновый шейк',ico:'🥤',desc:'Больше сил',bp:25,   pg:2.1,max:30,eff:'cpc',val:1},
  {id:'c2',name:'Спортперчатки',   ico:'🥊',desc:'Точный удар',bp:120,  pg:2.2,max:25,eff:'cpc',val:3},
  {id:'c3',name:'Предтрен',        ico:'⚡',desc:'Взрывная сила',bp:600, pg:2.3,max:20,eff:'cpc',val:10},
  {id:'c4',name:'Анаболики',       ico:'💉',desc:'Сила зашкаливает',bp:4000,pg:2.4,max:15,eff:'cpc',val:40},
  {id:'c5',name:'Режим зверя',     ico:'🦁',desc:'Ты непобедим',bp:30000,pg:2.5,max:12,eff:'cpc',val:200},
  {id:'c6',name:'Бог качалки',     ico:'🏛️',desc:'Запредельная мощь',bp:300000,pg:2.6,max:10,eff:'cpc',val:1200},
];
const UPG_ENERGY = [
  {id:'e1',name:'Расширенный запас',ico:'🔋',desc:'Больше энергии',bp:150,pg:2.2,max:15,eff:'maxE',val:50},
  {id:'e2',name:'Быстрое восст.',  ico:'🔄',desc:'Энергия восст. быстрее',bp:400,pg:2.3,max:15,eff:'regenE',val:1},
  {id:'e3',name:'Энергетик',       ico:'🟡',desc:'Мощный буст',bp:3000,pg:2.5,max:10,eff:'regenE',val:5},
];
const UPG_PASSIVE = [
  {id:'p1',name:'Новичок в зале',ico:'🚶',desc:'Парень качается за тебя',bp:50,   pg:1.8,max:50,eff:'cps',val:0.5},
  {id:'p2',name:'Личный тренер', ico:'👨‍🏫',desc:'Профи с программой',bp:300,   pg:1.9,max:40,eff:'cps',val:2},
  {id:'p3',name:'Мини-качалка',  ico:'🏋️',desc:'Своя маленькая качалка',bp:1500, pg:2.0,max:35,eff:'cps',val:8},
  {id:'p4',name:'Спортзал',      ico:'🏟️',desc:'Целый зал работает',bp:8000,  pg:2.1,max:30,eff:'cps',val:30},
  {id:'p5',name:'Сеть клубов',   ico:'🌐',desc:'Клубы по всему городу',bp:50000, pg:2.2,max:20,eff:'cps',val:150},
  {id:'p6',name:'Фитнес-империя',ico:'👑',desc:'Ты контролируешь рынок',bp:500000,pg:2.3,max:15,eff:'cps',val:800},
];
const ALL_UPG = [...UPG_CLICK,...UPG_ENERGY,...UPG_PASSIVE];

const ACHS = [
  {id:'a1', ico:'👆',name:'Первый клик',   desc:'Нажми на монету',      check:s=>s.clicks>=1},
  {id:'a2', ico:'💪',name:'100 кликов',    desc:'Сделай 100 кликов',    check:s=>s.clicks>=100},
  {id:'a3', ico:'🔥',name:'1000 кликов',   desc:'Сделай 1000 кликов',   check:s=>s.clicks>=1000},
  {id:'a4', ico:'💥',name:'10000 кликов',  desc:'Машина для кликов!',   check:s=>s.clicks>=10000},
  {id:'a5', ico:'💰',name:'100 монет',     desc:'Накопи 100 монет',     check:s=>s.allCoins>=100},
  {id:'a6', ico:'💎',name:'1000 монет',    desc:'Накопи 1000 монет',    check:s=>s.allCoins>=1000},
  {id:'a7', ico:'🪙',name:'10000 монет',   desc:'Накопи 10k монет',     check:s=>s.allCoins>=10000},
  {id:'a8', ico:'🏦',name:'100000 монет',  desc:'Серьёзные деньги!',    check:s=>s.allCoins>=100000},
  {id:'a9', ico:'⬆️',name:'Первый апгрейд',desc:'Купи улучшение',       check:s=>s.allUpg>=1},
  {id:'a10',ico:'🛒',name:'10 апгрейдов',  desc:'Купи 10 улучшений',    check:s=>s.allUpg>=10},
  {id:'a11',ico:'😴',name:'Пассивный доход',desc:'Получай монеты пассивно',check:s=>s.cps>=1},
  {id:'a12',ico:'⭐',name:'Стахановец',    desc:'10 монет в секунду',   check:s=>s.cps>=10},
  {id:'a13',ico:'🔥',name:'Первый престиж',desc:'Сделай престиж',       check:s=>s.prestiges>=1},
  {id:'a14',ico:'🎖️',name:'Ветеран',       desc:'3 престижа',           check:s=>s.prestiges>=3},
  {id:'a15',ico:'🏅',name:'Уровень 5',     desc:'Достигни 5-го уровня', check:s=>s.level>=5},
  {id:'a16',ico:'👑',name:'АБСОЛЮТ',       desc:'Достигни макс. уровня',check:s=>s.level>=10},
];

const SKINS = [
  {id:'default',name:'Золотая\\nКлассика',emoji:'💪',price:0,
   bg:'radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),radial-gradient(circle at 70% 72%,rgba(170,90,0,.3) 0%,transparent 50%),linear-gradient(135deg,#f5c518 0%,#e8a800 25%,#ffd700 50%,#cc8800 75%,#e8a800 100%)',
   sh:'0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4),0 8px 30px rgba(0,0,0,.6),inset 0 3px 8px rgba(255,255,180,.4)',
   anim:'',glow:'rgba(255,200,0,.18)'},
  {id:'fire',name:'Огненный\\nАтлет',emoji:'🔥',price:5000,
   bg:'radial-gradient(circle at 35% 25%,rgba(255,200,100,.5) 0%,transparent 50%),linear-gradient(135deg,#ff4500 0%,#ff6b00 30%,#ff0000 60%,#cc2200 100%)',
   sh:'0 0 0 4px rgba(255,80,0,.4),0 0 35px rgba(255,60,0,.6),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-shake',glow:'rgba(255,80,0,.2)'},
  {id:'ice',name:'Ледяной\\nКолосс',emoji:'❄️',price:5000,
   bg:'radial-gradient(circle at 35% 25%,rgba(200,240,255,.6) 0%,transparent 50%),linear-gradient(135deg,#00c8ff 0%,#0080cc 30%,#004488 60%,#0060aa 100%)',
   sh:'0 0 0 4px rgba(0,180,255,.4),0 0 35px rgba(0,180,255,.5),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-pulse',glow:'rgba(0,180,255,.18)'},
  {id:'toxic',name:'Токсичный\\nДоза',emoji:'☢️',price:12000,
   bg:'radial-gradient(circle at 40% 30%,rgba(180,255,100,.5) 0%,transparent 50%),linear-gradient(135deg,#39ff14 0%,#22cc00 35%,#009900 65%,#007700 100%)',
   sh:'0 0 0 4px rgba(57,255,20,.4),0 0 40px rgba(57,255,20,.6),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-bounce',glow:'rgba(57,255,20,.2)'},
  {id:'galaxy',name:'Галактика\\nСилы',emoji:'🌌',price:25000,
   bg:'radial-gradient(circle at 30% 25%,rgba(200,150,255,.5) 0%,transparent 50%),linear-gradient(135deg,#6600cc 0%,#9933ff 30%,#3300aa 60%,#cc00ff 100%)',
   sh:'0 0 0 4px rgba(180,0,255,.4),0 0 40px rgba(150,0,255,.6),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-spin',glow:'rgba(150,0,255,.2)'},
  {id:'diamond',name:'Бриллиантовый\\nБог',emoji:'💎',price:50000,
   bg:'radial-gradient(circle at 30% 20%,rgba(255,255,255,.9) 0%,transparent 40%),linear-gradient(135deg,#a8d8ff 0%,#e0f4ff 25%,#b8e8ff 50%,#5cb8ff 75%,#c8ecff 100%)',
   sh:'0 0 0 4px rgba(150,210,255,.5),0 0 50px rgba(100,200,255,.7),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-pulse',glow:'rgba(150,220,255,.25)'},
  {id:'lava',name:'Магма\\nАбсолют',emoji:'🌋',price:100000,
   bg:'radial-gradient(circle at 35% 25%,rgba(255,220,100,.6) 0%,transparent 45%),linear-gradient(135deg,#ff8c00 0%,#cc2200 25%,#ff4400 50%,#881100 75%,#ff6600 100%)',
   sh:'0 0 0 4px rgba(255,100,0,.5),0 0 50px rgba(255,80,0,.7),0 8px 30px rgba(0,0,0,.7)',
   anim:'anim-shake',glow:'rgba(255,80,0,.25)'},
  {id:'rainbow',name:'Радужный\\nКоролевич',emoji:'🦄',price:250000,
   bg:'linear-gradient(135deg,#ff0080 0%,#ff8c00 16%,#ffed00 33%,#00c800 50%,#0080ff 66%,#8000ff 83%,#ff0080 100%)',
   sh:'0 0 0 4px rgba(255,0,128,.4),0 0 50px rgba(128,0,255,.5),0 8px 30px rgba(0,0,0,.6)',
   anim:'anim-spin',glow:'rgba(200,0,200,.2)'},
];

// ═══════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════
const DEFAULT_STATE = {
  coins:0, allCoins:0, clicks:0, allUpg:0,
  prestiges:0, mult:1.0, level:1, xp:0,
  energy:100, maxE:100, regenE:2,
  cpc:1, cps:0, playTime:0, maxCps:0, maxCpc:1,
  upgLvl:{}, achs:[], ownedSkins:['default'], skin:'default',
  lastSeen:null,
};
let G = {...DEFAULT_STATE};

function load() {
  try {
    const raw = localStorage.getItem('gymv2');
    if (raw) { const s = JSON.parse(raw); Object.assign(G, s); }
  } catch(e) {}
}
function save() {
  G.lastSeen = Date.now();
  localStorage.setItem('gymv2', JSON.stringify(G));
}

// ═══════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════
function fmt(n) {
  n = Math.floor(n);
  if (n>=1e12) return (n/1e12).toFixed(1)+'T';
  if (n>=1e9)  return (n/1e9).toFixed(1)+'B';
  if (n>=1e6)  return (n/1e6).toFixed(1)+'M';
  if (n>=1000) return (n/1000).toFixed(1)+'K';
  return n.toString();
}
function upgLvl(id) { return G.upgLvl[id]||0; }
function upgPrice(u) { return Math.floor(u.bp * Math.pow(u.pg, upgLvl(u.id))); }

function recalc() {
  let cpc=1, cps=0, maxE=100, regenE=2;
  for (const u of UPG_CLICK)    { const l=upgLvl(u.id); if(l) cpc+=u.val*l; }
  for (const u of UPG_ENERGY)   { const l=upgLvl(u.id); if(l) { if(u.eff==='maxE') maxE+=u.val*l; else regenE+=u.val*l; } }
  for (const u of UPG_PASSIVE)  { const l=upgLvl(u.id); if(l) cps+=u.val*l; }
  G.cpc   = Math.max(1, Math.floor(cpc * G.mult));
  G.cps   = parseFloat((cps * G.mult).toFixed(2));
  G.maxE  = maxE;
  G.regenE= regenE;
  if (G.energy > G.maxE) G.energy = G.maxE;
  if (G.cps > G.maxCps) G.maxCps = G.cps;
  if (G.cpc > G.maxCpc) G.maxCpc = G.cpc;
}

function checkLevel() {
  while (G.level < LEVELS.length) {
    const next = LEVELS[G.level];
    if (!next || G.xp < next.xp) break;
    G.level++;
    notify('🎉 Уровень ' + G.level + ' — ' + LEVELS[G.level-1].name);
  }
}

function checkAchs() {
  const snap = {clicks:G.clicks,allCoins:G.allCoins,prestiges:G.prestiges,level:G.level,cps:G.cps,allUpg:G.allUpg};
  for (const a of ACHS) {
    if (!G.achs.includes(a.id) && a.check(snap)) {
      G.achs.push(a.id);
      showAchPop(a);
    }
  }
}

function prestigeReq() { return 100000 * Math.pow(5, G.prestiges); }

function doPrestige() {
  if (G.allCoins < prestigeReq()) return;
  G.prestiges++;
  G.mult = 1 + G.prestiges * 0.5;
  G.coins=0; G.xp=0; G.level=1; G.energy=G.maxE; G.upgLvl={};
  recalc(); checkAchs(); updateHUD(); renderAll();
  notify('🔥 ПРЕСТИЖ! Множитель ×' + G.mult.toFixed(1));
}

// ═══════════════════════════════════════════
// HUD
// ═══════════════════════════════════════════
function updateHUD() {
  document.getElementById('hCoins').textContent = fmt(G.coins);
  document.getElementById('hCph').textContent   = fmt(G.cps*3600) + '/ч';
  document.getElementById('sCpc').textContent   = '+' + fmt(G.cpc);
  document.getElementById('sCps').textContent   = fmt(G.cps);
  document.getElementById('sMult').textContent  = '×' + G.mult.toFixed(1);

  document.getElementById('eCount').textContent = Math.floor(G.energy) + ' / ' + G.maxE;
  document.getElementById('eFill').style.width  = (G.energy/G.maxE*100) + '%';

  const lvl   = G.level - 1;
  const curXp = LEVELS[lvl]?.xp || 0;
  const nxtXp = LEVELS[G.level]?.xp ?? (LEVELS[LEVELS.length-1].xp + 999999);
  const pct   = Math.min(100, ((G.xp-curXp)/(nxtXp-curXp))*100);
  document.getElementById('xpFill').style.width = pct + '%';
  document.getElementById('xpTxt').textContent  = fmt(G.xp-curXp) + ' / ' + fmt(nxtXp-curXp);
  document.getElementById('hLvlNum').textContent = G.level;
  document.getElementById('hLvlName').textContent = LEVELS[G.level-1]?.name || 'АБСОЛЮТ';

  document.getElementById('presReq').textContent = fmt(prestigeReq());
  document.getElementById('presBtn').disabled = G.allCoins < prestigeReq();

  // stats
  document.getElementById('st-tc').textContent = fmt(G.allCoins);
  document.getElementById('st-cl').textContent = fmt(G.clicks);
  document.getElementById('st-pr').textContent = G.prestiges;
  const mins=Math.floor(G.playTime/60), hrs=Math.floor(mins/60);
  document.getElementById('st-pt').textContent = hrs>0 ? hrs+'ч' : mins+'м';
  document.getElementById('st-mcps').textContent = fmt(G.maxCps);
  document.getElementById('st-mcpc').textContent = '+'+fmt(G.maxCpc);

  // no-energy
  document.getElementById('coinBtn').classList.toggle('nrg', G.energy < 1);

  // lb my val
  document.getElementById('lbMy').textContent = fmt(G.cps*3600) + '/ч';
}

// ═══════════════════════════════════════════
// RENDER UPGRADES
// ═══════════════════════════════════════════
function renderUpgList(containerId, list) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = list.map(u => {
    const lvl  = upgLvl(u.id);
    const maxed = lvl >= u.max;
    const price = upgPrice(u);
    const can   = !maxed && G.coins >= price;
    let eff='';
    if (u.eff==='cpc')   eff=`+${u.val} за клик`;
    if (u.eff==='cps')   eff=`+${u.val}/сек · +${fmt(u.val*3600)}/ч`;
    if (u.eff==='maxE')  eff=`+${u.val} энергии`;
    if (u.eff==='regenE') eff=`+${u.val} восст./сек`;
    return `<div class="upg-card${can?' can':''}${maxed?' maxed':''}" onclick="buyUpg('${u.id}')">
      <div class="upg-ico">${u.ico}</div>
      <div class="upg-info">
        <div class="upg-name">${u.name}</div>
        <div class="upg-desc">${u.desc} · ${eff}</div>
        <div class="upg-lvl">Ур. ${lvl} / ${u.max}</div>
      </div>
      <div class="upg-price">
        ${maxed
          ? '<div class="upg-pval" style="color:var(--green)">МАКС</div>'
          : `<div class="upg-pval${can?'':' no'}">${fmt(price)}</div><div class="upg-plbl">монет</div>`}
      </div>
    </div>`;
  }).join('');
}

function renderAchs() {
  const el = document.getElementById('list-ach');
  if (!el) return;
  el.innerHTML = ACHS.map(a => {
    const done = G.achs.includes(a.id);
    return `<div class="ach-card${done?' done':''}">
      <div class="ach-ico">${a.ico}</div>
      <div><div class="ach-name">${a.name}</div><div class="ach-desc">${done?a.desc:'???'}</div></div>
    </div>`;
  }).join('');
}

function renderSkins() {
  const el = document.getElementById('skinList');
  if (!el) return;
  el.innerHTML = SKINS.map(sk => {
    const owned    = G.ownedSkins.includes(sk.id);
    const equipped = G.skin === sk.id;
    const can      = !owned && G.coins >= sk.price;
    let badge = '';
    if (equipped)     badge = '<span class="skin-badge badge-eq">✓ НАДЕТ</span>';
    else if (owned)   badge = '<span class="skin-badge badge-own">КУПЛЕН</span>';
    else if (sk.price>0) badge = '<span class="skin-badge badge-lock">🔒</span>';
    let priceHtml = '';
    if (sk.price===0)     priceHtml = '<div class="skin-price" style="color:var(--green)">БЕСПЛАТНО</div>';
    else if (owned)       priceHtml = equipped
      ? '<div class="skin-price" style="color:var(--green)">НАДЕТ</div>'
      : '<div class="skin-price" style="color:var(--orange)">НАДЕТЬ</div>';
    else priceHtml = `<div class="skin-price${can?'':' no'}">${fmt(sk.price)} 💰</div>`;
    return `<div class="skin-card${equipped?' equipped':owned?' owned':can?' can':' locked'}" onclick="tapSkin('${sk.id}')">
      ${badge}
      <div class="skin-preview" style="background:${sk.bg};box-shadow:${sk.sh}">${sk.emoji}</div>
      <div class="skin-name">${sk.name.replace('\\n','<br>')}</div>
      ${priceHtml}
    </div>`;
  }).join('');
}

function renderAll() {
  renderUpgList('list-click',   UPG_CLICK);
  renderUpgList('list-energy',  UPG_ENERGY);
  renderUpgList('list-passive', UPG_PASSIVE);
  renderAchs();
  renderSkins();
}

// ═══════════════════════════════════════════
// ACTIONS
// ═══════════════════════════════════════════
function doClick(x, y) {
  if (G.energy < 1) { notify('⚡ Нет энергии!'); return; }
  G.energy = Math.max(0, G.energy - 1);
  G.coins    += G.cpc;
  G.allCoins += G.cpc;
  G.clicks++;
  G.xp += 1;
  checkLevel(); checkAchs();
  spawnFloat('+' + fmt(G.cpc), x, y);
  spawnRipple(x, y);
  updateHUD();
}

function buyUpg(id) {
  const u = ALL_UPG.find(x=>x.id===id);
  if (!u) return;
  const lvl = upgLvl(id);
  if (lvl >= u.max) return;
  const price = upgPrice(u);
  if (G.coins < price) { notify('💸 Недостаточно монет!'); return; }
  G.coins -= price;
  G.upgLvl[id] = lvl + 1;
  G.allUpg++;
  G.xp += 10;
  recalc(); checkLevel(); checkAchs();
  updateHUD(); renderAll();
  notify(`✅ ${u.name} — Ур.${lvl+1}`);
}

function tapSkin(id) {
  const sk = SKINS.find(s=>s.id===id);
  if (!sk) return;
  if (G.ownedSkins.includes(id)) {
    G.skin = id; applySkin(id); save(); renderSkins();
    notify('✅ Скин надет: ' + sk.name.replace('\\n',' '));
  } else {
    if (G.coins < sk.price) { notify('💸 Недостаточно монет!'); return; }
    G.coins -= sk.price;
    G.ownedSkins.push(id);
    G.skin = id; applySkin(id);
    G.allCoins; // no change needed
    save(); updateHUD(); renderSkins();
    notify('🎉 Скин куплен и надет!');
  }
}

function applySkin(id) {
  const sk = SKINS.find(s=>s.id===id) || SKINS[0];
  const btn  = document.getElementById('coinBtn');
  const glow = document.getElementById('coinGlow');
  btn.style.background  = sk.bg;
  btn.style.boxShadow   = sk.sh;
  btn.textContent       = sk.emoji;
  btn.className = btn.className.replace(/anim-\\w+/g,'').trim();
  if (sk.anim) btn.classList.add(sk.anim);
  if (glow) glow.style.background = `radial-gradient(circle,${sk.glow} 0%,transparent 70%)`;
}

// ═══════════════════════════════════════════
// COIN BUTTON — MULTITOUCH
// ═══════════════════════════════════════════
function initCoin() {
  const btn = document.getElementById('coinBtn');

  btn.addEventListener('touchstart', function(e) {
    e.preventDefault();
    this.classList.add('tap');
    setTimeout(()=>this.classList.remove('tap'), 300);
    for (const t of e.changedTouches) doClick(t.clientX, t.clientY);
  }, {passive:false});

  btn.addEventListener('mousedown', function(e) {
    this.classList.add('tap');
    setTimeout(()=>this.classList.remove('tap'), 300);
    doClick(e.clientX, e.clientY);
  });
}

// ═══════════════════════════════════════════
// PARTICLES
// ═══════════════════════════════════════════
function spawnFloat(txt, x, y) {
  const el = document.createElement('div');
  el.className = 'floatxt';
  el.textContent = txt;
  el.style.left = (x + (Math.random()*40-20)) + 'px';
  el.style.top  = (y - 10) + 'px';
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), 900);
}
function spawnRipple(x, y) {
  const el = document.createElement('div');
  el.className = 'ripple';
  el.style.cssText = `left:${x-25}px;top:${y-25}px;width:50px;height:50px`;
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), 450);
}

// ═══════════════════════════════════════════
// NOTIFICATIONS
// ═══════════════════════════════════════════
let notifT = null;
function notify(msg) {
  const el = document.getElementById('notif');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(notifT);
  notifT = setTimeout(()=>el.classList.remove('show'), 2000);
}

let achQ = [], achBusy = false;
function showAchPop(a) { achQ.push(a); if (!achBusy) nextAch(); }
function nextAch() {
  if (!achQ.length) { achBusy=false; return; }
  achBusy = true;
  const a = achQ.shift();
  document.getElementById('achpop-icon').textContent = a.ico;
  document.getElementById('achpop-name').textContent = a.name;
  document.getElementById('achpop').classList.add('show');
  setTimeout(()=>{ document.getElementById('achpop').classList.remove('show'); setTimeout(nextAch,400); }, 2500);
}

// ═══════════════════════════════════════════
// TABS
// ═══════════════════════════════════════════
const TAB_IDS = ['click','passive','stats','ach','top','skins'];
document.getElementById('tabs').addEventListener('click', function(e) {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  const id = btn.dataset.tab;
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on', b.dataset.tab===id));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on', p.id==='panel-'+id));
  if (id==='top')   loadLB();
  if (id==='skins') renderSkins();
  if (id==='ach')   renderAchs();
});

// ═══════════════════════════════════════════
// OFFLINE EARNINGS
// ═══════════════════════════════════════════
let _offlineEarned = 0;
function checkOffline() {
  if (!G.lastSeen || G.cps <= 0) return;
  const sec = Math.min((Date.now()-G.lastSeen)/1000, 7200);
  if (sec < 30) return;
  _offlineEarned = Math.floor(G.cps * sec);
  if (_offlineEarned <= 0) return;
  const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=Math.floor(sec%60);
  let t = h>0?h+'ч ':'' ; t += m>0?m+'мин ':''; t += (h===0&&s>0)?s+'сек':'';
  document.getElementById('offTime').textContent = 'Отсутствовал: ' + t.trim();
  document.getElementById('offEarn').textContent = '+' + fmt(_offlineEarned);
  document.getElementById('offpop').classList.add('show');
}
function claimOffline() {
  G.coins    += _offlineEarned;
  G.allCoins += _offlineEarned;
  G.xp       += Math.floor(_offlineEarned * 0.05);
  checkLevel(); checkAchs(); updateHUD();
  document.getElementById('offpop').classList.remove('show');
  notify('💰 Получено ' + fmt(_offlineEarned) + ' монет!');
}

// ═══════════════════════════════════════════
// NICKNAME
// ═══════════════════════════════════════════
function getMyNick() {
  const s = localStorage.getItem('gymNick');
  if (s) return s;
  if (window.Telegram?.WebApp?.initDataUnsafe?.user) {
    const u = Telegram.WebApp.initDataUnsafe.user;
    return u.username || u.first_name || ('user'+u.id);
  }
  return null;
}
function getMyId() {
  if (window.Telegram?.WebApp?.initDataUnsafe?.user)
    return String(Telegram.WebApp.initDataUnsafe.user.id);
  let id = localStorage.getItem('gymId');
  if (!id) { id='anon_'+Date.now(); localStorage.setItem('gymId',id); }
  return id;
}
function checkNick() {
  if (!getMyNick()) {
    document.getElementById('nickpop').classList.add('show');
    setTimeout(()=>document.getElementById('nickInput').focus(), 350);
  }
}
function saveNick() {
  const v = document.getElementById('nickInput').value.trim();
  const hint = document.getElementById('nickHint');
  if (v.length < 2)  { hint.textContent='Минимум 2 символа!'; return; }
  if (v.length > 20) { hint.textContent='Максимум 20 символов!'; return; }
  if (!/^[a-zA-Zа-яА-ЯёЁ0-9_\\- ]+$/.test(v)) { hint.textContent='Только буквы, цифры, _ и -'; return; }
  localStorage.setItem('gymNick', v);
  document.getElementById('nickpop').classList.remove('show');
  notify('👋 Привет, ' + v + '!');
  pushScore();
}
document.getElementById('nickInput').addEventListener('keydown', e=>{ if(e.key==='Enter') saveNick(); });

// ═══════════════════════════════════════════
// LEADERBOARD
// ═══════════════════════════════════════════
const API = window.location.origin;

async function pushScore() {
  const nick = getMyNick();
  if (!nick || G.cps <= 0) return;
  try {
    await fetch(API+'/api/score', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({user_id:getMyId(), username:nick, cph:Math.floor(G.cps*3600), prestiges:G.prestiges})
    });
  } catch(e) {}
}

function buildPodium(rows) {
  const el = document.getElementById('lbPodium');
  if (!rows?.length) { el.innerHTML=''; return; }
  const myNick = getMyNick();
  const top3 = rows.slice(0,3);
  // display order: 2nd | 1st | 3rd
  const order = top3.length>=2 ? [top3[1],top3[0],top3[2]].filter(Boolean) : [top3[0]];
  const cls   = top3.length>=2 ? ['p2','p1','p3'] : ['p1'];
  const nums  = top3.length>=2 ? [2,1,3] : [1];

  el.innerHTML = `<div class="podium-wrap">
    <div class="podium-htitle">🏆 Зал Славы</div>
    <div class="podium-stage">
      ${order.map((r,i)=>{
        const isMe = r.username===myNick;
        const crown = nums[i]===1 ? '<div class="podium-crown">👑</div>' : '<div class="podium-crown"></div>';
        return `<div class="podium-slot ${cls[i]}">
          ${crown}
          <div class="podium-circle">💪</div>
          <div class="podium-name" style="${isMe?'color:var(--green)':''}">${r.username}${isMe?' 👈':''}</div>
          <div class="podium-cph">${fmt(r.cph)}/ч</div>
          <div class="podium-block">${nums[i]}</div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

async function loadLB() {
  const el = document.getElementById('lbList');
  el.innerHTML = '<div class="lb-empty">Загрузка...</div>';
  document.getElementById('lbPodium').innerHTML = '';
  try {
    const res  = await fetch(API+'/api/leaderboard');
    const rows = await res.json();
    buildPodium(rows);
    const rest = rows.slice(3);
    if (!rest.length) { el.innerHTML=''; return; }
    const myNick = getMyNick();
    el.innerHTML = '<div class="podium-divider"></div>' + rest.map((r,i)=>{
      const isMe = r.username===myNick;
      return `<div class="lb-row${isMe?' me':''}">
        <div class="lb-rank">${i+4}</div>
        <div class="lb-name">${r.username}${isMe?' 👈':''}</div>
        <div style="text-align:right;flex-shrink:0">
          <div class="lb-rcph">${fmt(r.cph)}/ч</div>
          ${r.prestiges>0?`<div class="lb-prestige">🔥${r.prestiges} престиж</div>`:''}
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('lbPodium').innerHTML = '';
    el.innerHTML = '<div class="lb-empty">Ошибка загрузки.<br>Проверь соединение.</div>';
  }
}

setInterval(pushScore, 30000);

// ═══════════════════════════════════════════
// GAME LOOP
// ═══════════════════════════════════════════
let lastTick = Date.now();
function tick() {
  const now = Date.now();
  const dt  = Math.min((now - lastTick) / 1000, 0.5);
  lastTick  = now;

  if (G.cps > 0) {
    const earned = G.cps * dt;
    G.coins    += earned;
    G.allCoins += earned;
    G.xp       += earned * 0.1;
    checkLevel();
  }
  G.energy = Math.min(G.maxE, G.energy + G.regenE * dt);
  G.playTime += dt;
  updateHUD();
}
setInterval(tick,     100);
setInterval(save,     5000);
setInterval(renderAll,1000);
setInterval(checkAchs, 2000);

// ═══════════════════════════════════════════
// SAVE ON HIDE
// ═══════════════════════════════════════════
document.addEventListener('visibilitychange', ()=>{
  if (document.hidden) save();
});
window.addEventListener('pagehide', save);

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
load();
recalc();
initCoin();
applySkin(G.skin || 'default');
updateHUD();
renderAll();
checkOffline();
checkNick();

if (window.Telegram?.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}
</script>
</body>
</html>
"""

# ── База данных ───────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS lb (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        cph REAL,
        prestiges INTEGER,
        updated INTEGER
    )""")
    con.commit(); con.close()
    log.info("[DB] Ready: %s", DB_PATH)

def upsert(uid, name, cph, pres):
    con = sqlite3.connect(DB_PATH)
    con.execute("""INSERT INTO lb(user_id,username,cph,prestiges,updated)
        VALUES(?,?,?,?,strftime('%s','now'))
        ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, cph=excluded.cph,
        prestiges=excluded.prestiges, updated=excluded.updated
    """, (str(uid), name[:32], float(cph), int(pres)))
    con.commit(); con.close()

def get_top(n=20):
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT username,cph,prestiges FROM lb ORDER BY cph DESC LIMIT ?", (n,)).fetchall()
    con.close()
    return [{"username":r[0],"cph":r[1],"prestiges":r[2]} for r in rows]

# ── Веб-сервер ────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Frame-Options", "ALLOWALL")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/leaderboard":
            data = json.dumps(get_top()).encode()
            self.send_response(200); self._cors()
            self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(data)
        else:
            data = HTML.encode("utf-8")
            self.send_response(200); self._cors()
            self.send_header("Content-Type","text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/score":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length))
                upsert(body["user_id"], body.get("username","?"), body.get("cph",0), body.get("prestiges",0))
                self.send_response(200); self._cors()
                self.send_header("Content-Type","application/json"); self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                log.warning("[API] score error: %s", e)
                self.send_response(400); self._cors(); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, fmt, *args):
        log.info("[WEB] %s - %s", self.address_string(), fmt % args)

def run_web():
    s = HTTPServer(("0.0.0.0", PORT), Handler)
    log.info("[WEB] http://0.0.0.0:%s", PORT)
    s.serve_forever()

# ── Telegram бот ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    kb = [[InlineKeyboardButton("💪 Играть в Качалку!", web_app=WebAppInfo(url=GAME_URL))]]
    await update.message.reply_text(
        f"Привет, {u.first_name}! 💪\n\n"
        "🏋️ *Качалка Кликер* — прокачай своего качка!\n\n"
        "• Тыкай на монету 💪 (мультитач!)\n"
        "• Покупай улучшения клика и пассивный доход\n"
        "• Меняй скины монеты 🎨\n"
        "• Делай Престиж для множителей 🔥\n"
        "• Соревнуйся в таблице лидеров 👑",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏋️ *Как играть:*\n\n"
        "• *КЛИК* — улучши силу удара\n"
        "• *ПАССИВ* — монеты капают сами\n"
        "• *СКИНЫ* — купи новый вид монеты\n"
        "• *ТОП* — таблица лидеров с пьедесталом\n"
        "• *СТАТ* / *АЧИВ* — статистика и достижения\n\n"
        "💤 Оффлайн доход — до 2 часов пока не играешь\n"
        "🔥 Престиж — сброс за постоянный множитель",
        parse_mode="Markdown"
    )

def run_bot():
    if BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        log.error("Укажи BOT_TOKEN в .env!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    log.info("[BOT] Started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ── Точка входа ───────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()

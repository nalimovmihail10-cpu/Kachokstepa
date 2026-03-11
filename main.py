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
import json
import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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


# ─── База данных ──────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "leaderboard.db")

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            user_id   TEXT PRIMARY KEY,
            username  TEXT,
            cph       REAL,
            prestiges INTEGER,
            updated   INTEGER
        )
    """)
    con.commit()
    con.close()
    logger.info("[DB] База данных готова: %s", DB_PATH)

def upsert_score(user_id, username, cph, prestiges):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO leaderboard (user_id, username, cph, prestiges, updated)
        VALUES (?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username  = excluded.username,
            cph       = excluded.cph,
            prestiges = excluded.prestiges,
            updated   = excluded.updated
    """, (str(user_id), username, cph, prestiges))
    con.commit()
    con.close()

def get_top(limit=20):
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("""
        SELECT username, cph, prestiges
        FROM leaderboard
        ORDER BY cph DESC
        LIMIT ?
    """, (limit,)).fetchall()
    con.close()
    return [{"username": r[0], "cph": r[1], "prestiges": r[2]} for r in rows]

# ──────────────────────────────────────────────────────────────────────────────
# ─── HTML игры ────────────────────────────────────────────────────────────────
HTML = """

<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Качалка</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{
  --bg:#0d0d16;--c1:#161624;--c2:#1c1c2e;
  --gd:#ffd700;--or:#ff6200;--gn:#39ff14;--rd:#ff2244;--bl:#00c8ff;
  --tx:#f0e6d3;--mt:#6b6480
}
body{min-height:100vh;background:var(--bg);color:var(--tx);font-family:'Nunito',sans-serif;overflow-x:hidden}

/* HEADER */
#hdr{position:sticky;top:0;z-index:80;background:rgba(13,13,22,.97);border-bottom:1px solid rgba(255,215,0,.08);padding:10px 14px 8px;display:flex;align-items:center;gap:10px}
#btnProf{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--or),var(--gd));border:2px solid rgba(255,215,0,.3);font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 0 14px rgba(255,200,0,.2);transition:transform .12s}
#btnProf:active{transform:scale(.88)}
.h-mid{flex:1;text-align:center}
.h-coins{font-size:24px;font-weight:900;color:var(--gd);line-height:1}
.h-clbl{font-size:10px;color:var(--mt)}
.h-right{display:flex;flex-direction:column;align-items:flex-end}
.h-cph{font-size:14px;font-weight:800;color:var(--gn)}
.h-cphl{font-size:10px;color:var(--mt)}

/* XP BAR */
#xpbar{padding:5px 14px 8px;background:rgba(13,13,22,.7)}
.xp-row{display:flex;justify-content:space-between;font-size:10px;color:var(--mt);margin-bottom:4px}
.xp-track{height:5px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden}
.xp-fill{height:100%;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:3px;transition:width .4s}

/* CHIPS */
#chips{display:flex;gap:6px;padding:8px 14px}
.chip{flex:1;background:var(--c1);border:1px solid rgba(255,215,0,.1);border-radius:10px;padding:7px 4px;text-align:center}
.chip-v{font-size:14px;font-weight:900;color:var(--gd);line-height:1}
.chip-l{font-size:9px;color:var(--mt);margin-top:2px}

/* CLICKER */
#clicker{display:flex;flex-direction:column;align-items:center;padding:10px 14px 6px}
.nrg-wrap{width:100%;max-width:320px;margin-bottom:12px}
.nrg-top{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
.nrg-lbl{color:var(--or);font-weight:800;letter-spacing:1px}
.nrg-bar{height:7px;background:rgba(255,255,255,.07);border-radius:4px;overflow:hidden;border:1px solid rgba(255,100,0,.15)}
.nrg-fill{height:100%;background:linear-gradient(90deg,#ff3c00,var(--or),#ffa500);border-radius:4px;transition:width .12s linear}
.coin-wrap{position:relative;display:flex;align-items:center;justify-content:center;margin:2px 0}
.glow{position:absolute;width:210px;height:210px;border-radius:50%;pointer-events:none;background:radial-gradient(circle,rgba(255,200,0,.18) 0%,transparent 70%);animation:gp 2s ease-in-out infinite}
@keyframes gp{0%,100%{transform:scale(1);opacity:.8}50%{transform:scale(1.12);opacity:1}}
#btn{width:175px;height:175px;border-radius:50%;border:none;cursor:pointer;position:relative;z-index:10;font-size:82px;line-height:1;display:flex;align-items:center;justify-content:center;touch-action:manipulation;user-select:none;-webkit-user-select:none;
  background:radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),radial-gradient(circle at 70% 72%,rgba(170,90,0,.3) 0%,transparent 50%),linear-gradient(135deg,#f5c518,#e8a800,#ffd700,#cc8800,#e8a800);
  box-shadow:0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4),0 8px 30px rgba(0,0,0,.6),inset 0 3px 8px rgba(255,255,180,.4);
  transition:transform .08s,filter .2s}
#btn.tap{transform:scale(.88)}
#btn.dead{filter:grayscale(.7) brightness(.5)}
@keyframes bounce{0%,100%{transform:scale(1) rotate(0)}30%{transform:scale(1.08) rotate(-4deg)}70%{transform:scale(1.08) rotate(4deg)}}
@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-5px) rotate(-2deg)}75%{transform:translateX(5px) rotate(2deg)}}
#btn.ab.tap{animation:bounce .3s ease;transform:none}
#btn.as.tap{animation:spin .4s linear;transform:none}
#btn.ap.tap{animation:pulse .25s ease;transform:none}
#btn.ak.tap{animation:shake .3s ease;transform:none}

/* FLOAT / RIPPLE */
.ftxt{position:fixed;pointer-events:none;z-index:9999;font-size:20px;font-weight:900;color:var(--gd);text-shadow:0 0 10px rgba(255,200,0,.9),0 2px 4px rgba(0,0,0,.9);animation:fup .9s ease-out forwards}
@keyframes fup{0%{opacity:1;transform:translateY(0) scale(1)}50%{opacity:1;transform:translateY(-38px) scale(1.15)}100%{opacity:0;transform:translateY(-80px) scale(.8)}}
.rip{position:fixed;pointer-events:none;z-index:9998;border-radius:50%;background:rgba(255,200,0,.25);animation:ro .45s ease-out forwards}
@keyframes ro{0%{transform:scale(0);opacity:.8}100%{transform:scale(3.5);opacity:0}}

/* TABS */
#tabs{display:flex;gap:4px;padding:8px 14px 0;overflow-x:auto;scrollbar-width:none}
#tabs::-webkit-scrollbar{display:none}
.tab{flex-shrink:0;padding:10px 14px;background:var(--c1);border:1px solid rgba(255,255,255,.07);border-radius:10px;color:var(--mt);font-family:'Nunito',sans-serif;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;transition:all .2s}
.tab.on{background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,215,0,.1));border-color:rgba(255,215,0,.4);color:var(--gd)}

/* PANELS */
.panel{display:none;padding:10px 14px 120px}
.panel.on{display:block}
.sec{font-size:10px;font-weight:800;letter-spacing:2.5px;color:var(--mt);text-transform:uppercase;margin:14px 0 10px;padding-bottom:5px;border-bottom:1px solid rgba(255,255,255,.05)}
.sec:first-child{margin-top:4px}

/* BIG UPGRADE CARD */
.upg{background:var(--c1);border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:16px;display:flex;align-items:center;gap:14px;margin-bottom:10px;cursor:pointer;position:relative;overflow:hidden;transition:transform .12s,border-color .15s}
.upg.ok{border-color:rgba(255,215,0,.3)}
.upg.ok::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,100,0,.05),rgba(255,215,0,.05))}
.upg.mx{opacity:.38;cursor:default}
.upg:active:not(.mx){transform:scale(.972)}
.upg-i{width:58px;height:58px;border-radius:14px;flex-shrink:0;font-size:28px;display:flex;align-items:center;justify-content:center;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.14)}
.upg-b{flex:1;min-width:0}
.upg-n{font-size:14px;font-weight:800;color:var(--tx);margin-bottom:3px}
.upg-d{font-size:11px;color:var(--mt);line-height:1.35}
.upg-e{font-size:11px;color:var(--bl);font-weight:700;margin-top:3px}
.upg-l{font-size:10px;color:var(--or);font-weight:700;margin-top:3px}
.upg-p{flex-shrink:0;text-align:right;min-width:58px}
.upg-pv{font-size:14px;font-weight:900;color:var(--gd)}
.upg-pv.no{color:var(--rd)}
.upg-pl{font-size:10px;color:var(--mt);margin-top:1px}

/* PRESTIGE */
.pbox{background:linear-gradient(135deg,rgba(255,100,0,.1),rgba(255,215,0,.07));border:1px solid rgba(255,215,0,.2);border-radius:16px;padding:20px;text-align:center;margin-bottom:14px}
.pbox-t{font-size:20px;font-weight:900;color:var(--gd);margin-bottom:6px}
.pbox-d{font-size:12px;color:var(--mt);line-height:1.6;margin-bottom:16px}
.pbox-btn{background:linear-gradient(135deg,var(--or),var(--gd));border:none;border-radius:12px;padding:14px 32px;font-family:'Nunito',sans-serif;font-size:15px;font-weight:900;color:#000;cursor:pointer;box-shadow:0 4px 18px rgba(255,100,0,.4);transition:transform .1s}
.pbox-btn:active{transform:scale(.97)}
.pbox-btn:disabled{opacity:.35;cursor:not-allowed}

/* LEADERBOARD */
.lb-me{background:rgba(57,255,20,.06);border:1px solid rgba(57,255,20,.2);border-radius:12px;padding:12px 14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}
.lb-mel{font-size:11px;color:var(--gn);font-weight:800;letter-spacing:1px}
.lb-mev{font-size:16px;font-weight:900;color:var(--gd)}
.lb-ref{width:100%;padding:11px;border-radius:10px;border:1px solid rgba(255,100,0,.3);background:rgba(255,100,0,.1);color:var(--or);font-family:'Nunito',sans-serif;font-size:13px;font-weight:700;cursor:pointer;margin-bottom:10px}
.lb-ref:active{background:rgba(255,100,0,.2)}
/* podium */
.pod{text-align:center;padding:4px 0 18px}
.pod-t{font-size:10px;font-weight:800;letter-spacing:3px;color:var(--mt);text-transform:uppercase;margin-bottom:14px}
.pod-s{display:flex;align-items:flex-end;justify-content:center;gap:8px}
.pod-sl{display:flex;flex-direction:column;align-items:center;flex:1;max-width:110px}
.pod-cr{font-size:18px;margin-bottom:2px;min-height:22px}
.pod-ci{border-radius:50%;display:flex;align-items:center;justify-content:center;margin-bottom:5px;flex-shrink:0}
.p1 .pod-ci{width:80px;height:80px;font-size:44px;background:linear-gradient(135deg,#f5c518,#ffd700,#d4a010);box-shadow:0 0 22px rgba(255,200,0,.6),0 4px 14px rgba(0,0,0,.5)}
.p2 .pod-ci{width:64px;height:64px;font-size:34px;background:linear-gradient(135deg,#bdbdbd,#e0e0e0,#9e9e9e);box-shadow:0 0 14px rgba(200,200,200,.4)}
.p3 .pod-ci{width:56px;height:56px;font-size:30px;background:linear-gradient(135deg,#bf7b3b,#d4924a,#9e5e1e);box-shadow:0 0 12px rgba(200,130,60,.4)}
.pod-nm{font-size:11px;font-weight:800;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;width:100%;margin-bottom:2px}
.pod-cp{font-size:10px;color:var(--gd);font-weight:700}
.pod-bk{border-radius:9px 9px 0 0;width:100%;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:rgba(0,0,0,.35)}
.p1 .pod-bk{height:68px;background:linear-gradient(180deg,#c49a00,#a07800)}
.p2 .pod-bk{height:50px;background:linear-gradient(180deg,#8f8f8f,#6e6e6e)}
.p3 .pod-bk{height:38px;background:linear-gradient(180deg,#8f5a18,#6a3e0c)}
.pod-div{height:1px;background:rgba(255,255,255,.05);margin:8px 0 14px}
.lb-row{background:var(--c1);border:1px solid rgba(255,255,255,.05);border-radius:12px;padding:12px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px}
.lb-row.me{border-color:rgba(57,255,20,.4);background:linear-gradient(135deg,rgba(57,255,20,.07),transparent)}
.lb-rk{width:28px;text-align:center;font-size:14px;font-weight:900;color:var(--mt);flex-shrink:0}
.lb-nm{flex:1;font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lb-row.me .lb-nm{color:var(--gn)}
.lb-cp{font-size:14px;font-weight:900;color:var(--gd);flex-shrink:0}
.lb-em{text-align:center;padding:30px 20px;color:var(--mt);font-size:13px;line-height:1.8}

/* ====== PROFILE DRAWER LEFT ====== */
#ov{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,0);pointer-events:none;transition:background .3s}
#ov.on{background:rgba(0,0,0,.65);pointer-events:all}
#dr{position:fixed;top:0;left:-105%;width:88%;max-width:380px;height:100vh;z-index:201;background:var(--c2);border-right:1px solid rgba(255,215,0,.12);display:flex;flex-direction:column;transition:left .35s cubic-bezier(.25,.46,.45,.94)}
#dr.on{left:0}
.dr-top{flex-shrink:0;padding:20px 18px 0;background:linear-gradient(180deg,rgba(255,100,0,.1),transparent);border-bottom:1px solid rgba(255,215,0,.1)}
.dr-head{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.dr-ava{width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,var(--or),var(--gd));display:flex;align-items:center;justify-content:center;font-size:32px;flex-shrink:0;border:3px solid rgba(255,215,0,.4);box-shadow:0 0 20px rgba(255,200,0,.3)}
.dr-info{flex:1;min-width:0}
.dr-name{font-size:19px;font-weight:900;color:var(--gd);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dr-sub{font-size:12px;color:var(--mt);margin-top:3px}
.dr-close{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.07);border:none;color:var(--mt);font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.dr-close:active{background:rgba(255,255,255,.14)}
.nick-row{display:flex;gap:8px;margin-bottom:16px}
.nick-in{flex:1;padding:10px 13px;border-radius:10px;border:1.5px solid rgba(255,215,0,.2);background:rgba(255,255,255,.06);color:var(--tx);font-family:'Nunito',sans-serif;font-size:14px;font-weight:700;outline:none;-webkit-appearance:none}
.nick-in:focus{border-color:rgba(255,215,0,.5)}
.nick-btn{padding:10px 16px;border-radius:10px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;color:#000;cursor:pointer}
.dr-tabs{display:flex;background:rgba(0,0,0,.3);border-bottom:1px solid rgba(255,215,0,.08);flex-shrink:0}
.dr-tab{flex:1;padding:13px 6px;background:transparent;border:none;color:var(--mt);font-family:'Nunito',sans-serif;font-size:11px;font-weight:700;cursor:pointer;text-align:center;border-bottom:2px solid transparent;transition:all .2s}
.dr-tab.on{color:var(--gd);border-bottom-color:var(--gd)}
.dr-body{flex:1;overflow-y:auto;padding:14px 18px 40px;scrollbar-width:none}
.dr-body::-webkit-scrollbar{display:none}
.drpan{display:none}.drpan.on{display:block}

/* BIG STAT CARDS */
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:4px}
.sc{background:var(--c1);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:15px}
.sc-v{font-size:20px;font-weight:900;color:var(--gd)}
.sc-l{font-size:10px;color:var(--mt);margin-top:3px}

/* BIG ACHIEVEMENT CARD */
.ach{background:var(--c1);border:1px solid rgba(255,255,255,.05);border-radius:16px;padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:13px;opacity:.35;transition:opacity .25s}
.ach.on{opacity:1;border-color:rgba(255,215,0,.18);background:linear-gradient(135deg,rgba(255,100,0,.06),rgba(255,215,0,.04))}
.ach-i{font-size:30px;flex-shrink:0;width:44px;text-align:center}
.ach-b{flex:1;min-width:0}
.ach-n{font-size:14px;font-weight:800}
.ach-d{font-size:11px;color:var(--mt);margin-top:2px;line-height:1.3}
.ach-r{font-size:10px;color:var(--bl);font-weight:700;margin-top:5px}
.ach-btn{background:linear-gradient(135deg,var(--or),var(--gd));border:none;border-radius:9px;padding:8px 13px;font-family:'Nunito',sans-serif;font-size:11px;font-weight:900;color:#000;cursor:pointer;white-space:nowrap;flex-shrink:0}
.ach-got{font-size:11px;color:var(--gn);font-weight:700;flex-shrink:0}

/* BIG SKIN CARD */
.sgd{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sk{background:var(--c1);border:2px solid rgba(255,255,255,.07);border-radius:16px;padding:16px 12px;display:flex;flex-direction:column;align-items:center;gap:9px;cursor:pointer;position:relative;overflow:hidden;transition:transform .12s,border-color .15s}
.sk.ok{border-color:rgba(255,215,0,.3)}
.sk.own{border-color:rgba(57,255,20,.3)}
.sk.eq{border-color:rgba(57,255,20,.75);background:linear-gradient(135deg,rgba(57,255,20,.08),transparent)}
.sk.lk{opacity:.5}.sk.ak{opacity:.55;cursor:default}
.sk:active:not(.lk):not(.ak){transform:scale(.97)}
.sk-prev{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:36px;flex-shrink:0}
.sk-n{font-size:12px;font-weight:800;text-align:center;color:var(--tx);line-height:1.3}
.sk-p{font-size:12px;font-weight:700;color:var(--gd);text-align:center}
.sk-p.no{color:var(--rd)}.sk-p.ac{color:var(--bl);font-size:10px}
.sk-bdg{position:absolute;top:6px;right:6px;font-size:9px;font-weight:800;padding:2px 6px;border-radius:20px}
.b-eq{background:rgba(57,255,20,.2);color:var(--gn)}
.b-own{background:rgba(57,255,20,.12);color:var(--gn)}
.b-lk{background:rgba(255,255,255,.07);color:var(--mt)}
.b-ac{background:rgba(0,200,255,.15);color:var(--bl)}

/* NOTIF */
#notif{position:fixed;top:66px;left:50%;transform:translateX(-50%) translateY(-14px);background:linear-gradient(135deg,var(--or),var(--gd));color:#000;font-weight:900;font-size:13px;padding:9px 20px;border-radius:30px;z-index:9999;opacity:0;pointer-events:none;transition:all .25s;white-space:nowrap;box-shadow:0 4px 18px rgba(255,100,0,.45)}
#notif.on{opacity:1;transform:translateX(-50%) translateY(0)}

/* ACH POPUP */
#apop{position:fixed;bottom:-100px;left:50%;transform:translateX(-50%);background:var(--c2);border:1px solid rgba(255,215,0,.35);border-radius:16px;padding:14px 20px;display:flex;align-items:center;gap:12px;z-index:9999;transition:bottom .35s cubic-bezier(.175,.885,.32,1.275);box-shadow:0 -4px 26px rgba(255,200,0,.12);min-width:270px}
#apop.on{bottom:18px}
#apop-i{font-size:34px}
.ap-l{font-size:10px;color:var(--gd);letter-spacing:2px;font-weight:800}
.ap-n{font-size:14px;font-weight:900}
.ap-r{font-size:11px;color:var(--bl);margin-top:2px}

/* OFFLINE POPUP */
#offpop{position:fixed;inset:0;z-index:99998;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.85);backdrop-filter:blur(7px)}
#offpop.on{display:flex}
.offmod{background:var(--c2);border:1px solid rgba(255,215,0,.3);border-radius:22px;padding:30px 26px;text-align:center;width:88%;max-width:320px;animation:popin .35s cubic-bezier(.175,.885,.32,1.275)}
@keyframes popin{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
.off-ico{font-size:52px;margin-bottom:10px;animation:sn 2s ease-in-out infinite}
@keyframes sn{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
.off-btn{width:100%;padding:15px;border:none;border-radius:13px;background:linear-gradient(135deg,var(--or),var(--gd));font-family:'Nunito',sans-serif;font-size:16px;font-weight:900;color:#000;cursor:pointer;margin-top:18px;transition:transform .1s}
.off-btn:active{transform:scale(.97)}

/* NICK POPUP */
#nickpop{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.9);backdrop-filter:blur(8px)}
#nickpop.on{display:flex}
.nmod{background:var(--c2);border:1px solid rgba(255,215,0,.28);border-radius:22px;padding:32px 26px 26px;text-align:center;width:88%;max-width:330px;animation:popin .35s cubic-bezier(.175,.885,.32,1.275)}
.nin{width:100%;padding:13px 15px;border-radius:11px;outline:none;background:rgba(255,255,255,.06);border:2px solid rgba(255,215,0,.18);color:var(--tx);font-family:'Nunito',sans-serif;font-size:16px;font-weight:700;text-align:center;margin-bottom:7px;transition:border-color .2s;-webkit-appearance:none}
.nin:focus{border-color:rgba(255,215,0,.5)}
.nin::placeholder{color:var(--mt);font-weight:400}
.nhint{font-size:11px;color:var(--rd);min-height:16px;margin-bottom:14px}
.nbtn{width:100%;padding:15px;border:none;border-radius:13px;background:linear-gradient(135deg,var(--or),var(--gd));font-family:'Nunito',sans-serif;font-size:16px;font-weight:900;color:#000;cursor:pointer;transition:transform .1s}
.nbtn:active{transform:scale(.97)}
</style>
</head>
<body>

<div id="hdr">
  <button id="btnProf" onclick="openDr()">💪</button>
  <div class="h-mid">
    <div class="h-coins" id="hCoins">0</div>
    <div class="h-clbl">💰 МОНЕТ</div>
  </div>
  <div class="h-right">
    <div class="h-cph" id="hCph">0/ч</div>
    <div class="h-cphl">📈 В ЧАС</div>
  </div>
</div>

<div id="xpbar">
  <div class="xp-row">
    <span style="color:var(--or);font-weight:800">⭐ <span id="hLvlN">Новичок</span> — Ур.<span id="hLvlI">1</span></span>
    <span id="xpTxt">0/100</span>
  </div>
  <div class="xp-track"><div class="xp-fill" id="xpFill" style="width:0%"></div></div>
</div>

<div id="chips">
  <div class="chip"><div class="chip-v" id="cCpc">+1</div><div class="chip-l">за клик</div></div>
  <div class="chip"><div class="chip-v" id="cCps">0</div><div class="chip-l">/ сек</div></div>
  <div class="chip"><div class="chip-v" id="cMlt">x1.0</div><div class="chip-l">множитель</div></div>
  <div class="chip"><div class="chip-v" id="cCrt">0%</div><div class="chip-l">крит</div></div>
</div>

<div id="clicker">
  <div class="nrg-wrap">
    <div class="nrg-top"><span class="nrg-lbl">⚡ ЭНЕРГИЯ</span><span id="nrgTxt">100/100</span></div>
    <div class="nrg-bar"><div class="nrg-fill" id="nrgFill" style="width:100%"></div></div>
  </div>
  <div class="coin-wrap">
    <div class="glow" id="glw"></div>
    <button id="btn">💪</button>
  </div>
</div>

<div id="tabs">
  <button class="tab on" data-t="click">🖱 КЛИК</button>
  <button class="tab" data-t="passive">⏱ ПАССИВ</button>
  <button class="tab" data-t="boost">🚀 БУСТ</button>
  <button class="tab" data-t="top">👑 ТОП</button>
</div>

<div class="panel on" id="panel-click">
  <div class="sec">Сила удара</div><div id="lClick"></div>
  <div class="sec">Энергия</div><div id="lEnergy"></div>
  <div class="sec">Критический удар</div><div id="lCrit"></div>
</div>

<div class="panel" id="panel-passive">
  <div class="sec">Пассивный доход</div><div id="lPassive"></div>
  <div class="sec">Глобальные множители</div><div id="lMulti"></div>
  <div class="sec">Престиж</div>
  <div class="pbox">
    <div class="pbox-t">🔥 ПРЕСТИЖ</div>
    <div class="pbox-d">Сбрось прогресс — получи постоянный множитель.<br>Нужно всего: <strong id="presReq" style="color:var(--gd)">100,000</strong></div>
    <button class="pbox-btn" id="presBtn" onclick="prestige()" disabled>ПРЕСТИЖ</button>
  </div>
</div>

<div class="panel" id="panel-boost">
  <div class="sec">Авто-кликер</div><div id="lAuto"></div>
  <div class="sec">Оффлайн доход</div><div id="lOffline"></div>
  <div class="sec">Специальные</div><div id="lSpecial"></div>
</div>

<div class="panel" id="panel-top">
  <div class="lb-me" style="margin-top:6px">
    <span class="lb-mel">📈 МОЙ ДОХОД / ЧАС</span>
    <span class="lb-mev" id="lbMe">0</span>
  </div>
  <button class="lb-ref" onclick="loadLB()">🔄 Обновить</button>
  <div id="lbPod"></div>
  <div id="lbList"></div>
</div>

<div id="notif"></div>

<div id="apop">
  <div id="apop-i">🏆</div>
  <div><div class="ap-l">ДОСТИЖЕНИЕ!</div><div class="ap-n" id="apN">-</div><div class="ap-r" id="apR"></div></div>
</div>

<div id="offpop">
  <div class="offmod">
    <div class="off-ico">💤</div>
    <div style="font-size:15px;font-weight:900;margin-bottom:4px">Пока тебя не было...</div>
    <div style="font-size:12px;color:var(--mt);margin-bottom:14px" id="offT"></div>
    <div style="font-size:11px;color:var(--mt);letter-spacing:1px;margin-bottom:4px">КАЧАЛКА ЗАРАБОТАЛА:</div>
    <div style="font-size:40px;font-weight:900;color:var(--gd);line-height:1" id="offE">+0</div>
    <div style="font-size:10px;color:var(--mt);margin-top:6px">Макс: <span id="offMaxH">2</span>ч</div>
    <button class="off-btn" onclick="claimOff()">ЗАБРАТЬ 💰</button>
  </div>
</div>

<div id="nickpop">
  <div class="nmod">
    <div style="font-size:56px;margin-bottom:10px">💪</div>
    <div style="font-size:21px;font-weight:900;color:var(--gd);margin-bottom:5px">Добро пожаловать!</div>
    <div style="font-size:13px;color:var(--mt);margin-bottom:18px">Введи никнейм для таблицы лидеров</div>
    <input class="nin" id="nickIn" type="text" maxlength="20" placeholder="Твой никнейм..." autocomplete="off">
    <div class="nhint" id="nickHint"></div>
    <button class="nbtn" onclick="saveNick()">В КАЧАЛКУ! 💪</button>
  </div>
</div>

<div id="ov" onclick="closeDr()"></div>

<div id="dr">
  <div class="dr-top">
    <div class="dr-head">
      <div class="dr-ava" id="drAva">💪</div>
      <div class="dr-info">
        <div class="dr-name" id="drName">Игрок</div>
        <div class="dr-sub">Ур.<span id="drLvl">1</span> · <span id="drLvlN">Новичок</span></div>
      </div>
      <button class="dr-close" onclick="closeDr()">✕</button>
    </div>
    <div class="nick-row">
      <input class="nick-in" id="nickEdit" type="text" maxlength="20" placeholder="Изменить ник...">
      <button class="nick-btn" onclick="changeNick()">✓</button>
    </div>
  </div>
  <div class="dr-tabs">
    <button class="dr-tab on" data-p="stats">📊 Статистика</button>
    <button class="dr-tab" data-p="achs">🏆 Достижения</button>
    <button class="dr-tab" data-p="skins">🎨 Скины</button>
  </div>
  <div class="dr-body">
    <div class="drpan on" id="drpan-stats">
      <div class="sgrid" style="margin-top:2px">
        <div class="sc"><div class="sc-v" id="pp-tc">0</div><div class="sc-l">Всего монет</div></div>
        <div class="sc"><div class="sc-v" id="pp-cl">0</div><div class="sc-l">Кликов</div></div>
        <div class="sc"><div class="sc-v" id="pp-pr">0</div><div class="sc-l">Престижей</div></div>
        <div class="sc"><div class="sc-v" id="pp-pt">0м</div><div class="sc-l">Время игры</div></div>
        <div class="sc"><div class="sc-v" id="pp-ms">0</div><div class="sc-l">Макс /сек</div></div>
        <div class="sc"><div class="sc-v" id="pp-mc">+1</div><div class="sc-l">Макс за клик</div></div>
        <div class="sc"><div class="sc-v" id="pp-cr">0</div><div class="sc-l">Критов</div></div>
        <div class="sc"><div class="sc-v" id="pp-sk">0</div><div class="sc-l">Скинов</div></div>
      </div>
    </div>
    <div class="drpan" id="drpan-achs"><div id="achList"></div></div>
    <div class="drpan" id="drpan-skins"><div class="sgd" id="skinList"></div></div>
  </div>
</div>

<script>
// ═══ DATA ═══
const LVS=[
  {n:'Новичок',x:0},{n:'Любитель',x:100},{n:'Спортсмен',x:300},{n:'Атлет',x:700},
  {n:'Культурист',x:1500},{n:'Чемпион',x:3500},{n:'Мастер',x:8000},
  {n:'Легенда',x:20000},{n:'Бог Железа',x:50000},{n:'АБСОЛЮТ',x:120000}
];

// Upgrades — energy regen +0.3 per level
const UG = {
  click:[
    {id:'c1',n:'Протеиновый шейк',i:'🥤',d:'Больше сил в руках',bp:25,pg:2.1,mx:30,ef:'cpc',v:1},
    {id:'c2',n:'Спортперчатки',i:'🥊',d:'Точный удар по монете',bp:120,pg:2.2,mx:25,ef:'cpc',v:3},
    {id:'c3',n:'Предтрен',i:'⚡',d:'Взрывная сила удара',bp:600,pg:2.3,mx:20,ef:'cpc',v:10},
    {id:'c4',n:'Анаболики',i:'💉',d:'Сила зашкаливает',bp:4000,pg:2.4,mx:15,ef:'cpc',v:40},
    {id:'c5',n:'Режим зверя',i:'🦁',d:'Ты непобедим',bp:30000,pg:2.5,mx:12,ef:'cpc',v:200},
    {id:'c6',n:'Бог качалки',i:'🏛️',d:'Запредельная мощь',bp:300000,pg:2.6,mx:10,ef:'cpc',v:1200},
    {id:'c7',n:'Квантовый удар',i:'⚛️',d:'Разрушает пространство',bp:3000000,pg:2.7,mx:8,ef:'cpc',v:8000},
  ],
  energy:[
    {id:'e1',n:'Расширенный запас',i:'🔋',d:'Больше максимальной энергии',bp:150,pg:2.2,mx:20,ef:'mxE',v:50},
    {id:'e2',n:'Быстрое восст.',i:'🔄',d:'+0.3 восст./сек за уровень',bp:400,pg:2.3,mx:30,ef:'rgE',v:0.3},
    {id:'e3',n:'Энергетик',i:'🟡',d:'+0.3 восст./сек за уровень',bp:3000,pg:2.5,mx:20,ef:'rgE',v:0.3},
    {id:'e4',n:'Ядерный реактор',i:'☢️',d:'+0.3 восст./сек за уровень',bp:80000,pg:2.6,mx:10,ef:'rgE',v:0.3},
  ],
  crit:[
    {id:'cr1',n:'Меткость',i:'🎯',d:'Шанс нанести критический удар',bp:800,pg:2.3,mx:20,ef:'critC',v:5},
    {id:'cr2',n:'Разрушитель',i:'💣',d:'Множитель критического удара',bp:5000,pg:2.4,mx:15,ef:'critM',v:0.5},
    {id:'cr3',n:'Снайпер',i:'🔭',d:'Ещё больше шанс крита',bp:25000,pg:2.5,mx:10,ef:'critC',v:10},
  ],
  passive:[
    {id:'p1',n:'Новичок в зале',i:'🚶',d:'Парень качается за тебя',bp:50,pg:1.8,mx:50,ef:'cps',v:0.5},
    {id:'p2',n:'Личный тренер',i:'👨‍🏫',d:'Профи с программой тренировок',bp:300,pg:1.9,mx:40,ef:'cps',v:2},
    {id:'p3',n:'Мини-качалка',i:'🏋️',d:'Своя маленькая качалка',bp:1500,pg:2.0,mx:35,ef:'cps',v:8},
    {id:'p4',n:'Спортзал',i:'🏟️',d:'Целый зал работает на тебя',bp:8000,pg:2.1,mx:30,ef:'cps',v:30},
    {id:'p5',n:'Сеть клубов',i:'🌐',d:'Клубы по всему городу',bp:50000,pg:2.2,mx:20,ef:'cps',v:150},
    {id:'p6',n:'Фитнес-империя',i:'👑',d:'Ты контролируешь рынок',bp:500000,pg:2.3,mx:15,ef:'cps',v:800},
    {id:'p7',n:'Мировая сеть',i:'🌍',d:'Планета качается на тебя',bp:5000000,pg:2.4,mx:10,ef:'cps',v:5000},
  ],
  multi:[
    {id:'m1',n:'Мотивация',i:'🔑',d:'Все монеты x1.1',bp:2000,pg:2.5,mx:20,ef:'gm',v:0.1},
    {id:'m2',n:'Медитация',i:'🧘',d:'Все монеты x1.25',bp:20000,pg:2.6,mx:15,ef:'gm',v:0.25},
    {id:'m3',n:'Режим бога',i:'✨',d:'Все монеты x2.0',bp:500000,pg:2.8,mx:10,ef:'gm',v:1.0},
  ],
  auto:[
    {id:'au1',n:'Авто-рука',i:'🤖',d:'Автоматически кликает за тебя',bp:10000,pg:2.3,mx:20,ef:'aCps',v:1},
    {id:'au2',n:'Дрон-тренер',i:'🚁',d:'Летающий кликер-дрон',bp:75000,pg:2.4,mx:15,ef:'aCps',v:5},
    {id:'au3',n:'ИИ-атлет',i:'🧠',d:'Искусственный интеллект кликает',bp:800000,pg:2.5,mx:10,ef:'aCps',v:20},
  ],
  offline:[
    {id:'of1',n:'Копилка',i:'🐷',d:'Дольше копится оффлайн доход',bp:5000,pg:2.2,mx:10,ef:'offH',v:0.5},
    {id:'of2',n:'Сейф',i:'🔐',d:'Ещё больше оффлайна',bp:50000,pg:2.4,mx:6,ef:'offH',v:1},
    {id:'of3',n:'Банк',i:'🏦',d:'Максимальный оффлайн доход',bp:500000,pg:2.6,mx:4,ef:'offH',v:2},
  ],
  special:[
    {id:'sp1',n:'Двойные монеты',i:'x2',d:'x2 монеты на 30 секунд',bp:15000,pg:3.0,mx:1,ef:'tb',v:2},
    {id:'sp2',n:'Комбо-удар',i:'🎰',d:'Каждый 10-й клик даёт x10',bp:8000,pg:2.5,mx:25,ef:'combo',v:1},
    {id:'sp3',n:'Фортуна',i:'🍀',d:'Шанс удвоить монеты',bp:35000,pg:2.7,mx:10,ef:'luck',v:15},
    {id:'sp4',n:'Цепная реакция',i:'⛓️',d:'Каждый клик подряд +1 монета',bp:100000,pg:2.8,mx:8,ef:'chain',v:1},
  ],
};
const ALL_UG = Object.values(UG).flat();

const ACHS=[
  {id:'a1',i:'👆',n:'Первый клик',d:'Нажми на монету',c:s=>s.clicks>=1,r:{t:'c',v:10}},
  {id:'a2',i:'💪',n:'100 кликов',d:'Сделай 100 кликов',c:s=>s.clicks>=100,r:{t:'c',v:200}},
  {id:'a3',i:'🔥',n:'1000 кликов',d:'Сделай 1000 кликов',c:s=>s.clicks>=1000,r:{t:'c',v:2000}},
  {id:'a4',i:'💥',n:'10K кликов',d:'Машина для кликов!',c:s=>s.clicks>=10000,r:{t:'c',v:20000}},
  {id:'a5',i:'🦾',n:'100K кликов',d:'Ты кликер-легенда',c:s=>s.clicks>=100000,r:{t:'s',v:'toxic'}},
  {id:'a6',i:'💰',n:'100 монет',d:'Накопи 100 монет',c:s=>s.allC>=100,r:{t:'c',v:50}},
  {id:'a7',i:'💎',n:'10K монет',d:'Накопи 10k монет',c:s=>s.allC>=10000,r:{t:'c',v:5000}},
  {id:'a8',i:'🏦',n:'1M монет',d:'Миллионер!',c:s=>s.allC>=1000000,r:{t:'s',v:'diamond'}},
  {id:'a9',i:'⬆️',n:'Первый апгрейд',d:'Купи улучшение',c:s=>s.allU>=1,r:{t:'c',v:100}},
  {id:'a10',i:'🛒',n:'25 апгрейдов',d:'Инвестор!',c:s=>s.allU>=25,r:{t:'c',v:25000}},
  {id:'a11',i:'😴',n:'Пассивный доход',d:'1 монета/сек',c:s=>s.cps>=1,r:{t:'c',v:500}},
  {id:'a12',i:'⭐',n:'Стахановец',d:'100 монет/сек',c:s=>s.cps>=100,r:{t:'s',v:'galaxy'}},
  {id:'a13',i:'🔥',n:'Первый престиж',d:'Сделай престиж',c:s=>s.pres>=1,r:{t:'s',v:'fire'}},
  {id:'a14',i:'🎖️',n:'Ветеран',d:'5 престижей',c:s=>s.pres>=5,r:{t:'s',v:'lava'}},
  {id:'a15',i:'🏅',n:'Уровень 5',d:'Достигни 5-го уровня',c:s=>s.lvl>=5,r:{t:'c',v:10000}},
  {id:'a16',i:'👑',n:'АБСОЛЮТ',d:'Достигни макс. уровня',c:s=>s.lvl>=10,r:{t:'s',v:'rainbow'}},
  {id:'a17',i:'🎯',n:'Критикан',d:'100 критических ударов',c:s=>s.crits>=100,r:{t:'c',v:15000}},
  {id:'a18',i:'🤖',n:'Роботизация',d:'Купи Авто-руку',c:s=>(s.ul['au1']||0)>=1,r:{t:'c',v:20000}},
  {id:'a19',i:'🌌',n:'Галактический',d:'Купи Галактика Силы',c:s=>s.sk.includes('galaxy'),r:{t:'c',v:50000}},
  {id:'a20',i:'⚡',n:'Комбо-мастер',d:'Активируй комбо 10 раз',c:s=>s.combos>=10,r:{t:'c',v:30000}},
];

const SKINS=[
  {id:'default',n:'Золотая Классика',e:'💪',p:0,ach:null,
   bg:'radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),radial-gradient(circle at 70% 72%,rgba(170,90,0,.3) 0%,transparent 50%),linear-gradient(135deg,#f5c518,#e8a800,#ffd700,#cc8800,#e8a800)',
   sh:'0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4),0 8px 30px rgba(0,0,0,.6)',an:'',gl:'rgba(255,200,0,.18)'},
  {id:'fire',n:'Огненный Атлет',e:'🔥',p:5000,ach:null,
   bg:'radial-gradient(circle at 35% 25%,rgba(255,200,100,.5) 0%,transparent 50%),linear-gradient(135deg,#ff4500,#ff6b00,#ff0000,#cc2200)',
   sh:'0 0 0 4px rgba(255,80,0,.4),0 0 35px rgba(255,60,0,.6),0 8px 30px rgba(0,0,0,.6)',an:'ak',gl:'rgba(255,80,0,.2)'},
  {id:'ice',n:'Ледяной Колосс',e:'❄️',p:5000,ach:null,
   bg:'radial-gradient(circle at 35% 25%,rgba(200,240,255,.6) 0%,transparent 50%),linear-gradient(135deg,#00c8ff,#0080cc,#004488,#0060aa)',
   sh:'0 0 0 4px rgba(0,180,255,.4),0 0 35px rgba(0,180,255,.5),0 8px 30px rgba(0,0,0,.6)',an:'ap',gl:'rgba(0,180,255,.18)'},
  {id:'toxic',n:'Токсичный Доза',e:'☢️',p:0,ach:'a5',
   bg:'radial-gradient(circle at 40% 30%,rgba(180,255,100,.5) 0%,transparent 50%),linear-gradient(135deg,#39ff14,#22cc00,#009900,#007700)',
   sh:'0 0 0 4px rgba(57,255,20,.4),0 0 40px rgba(57,255,20,.6),0 8px 30px rgba(0,0,0,.6)',an:'ab',gl:'rgba(57,255,20,.2)'},
  {id:'galaxy',n:'Галактика Силы',e:'🌌',p:25000,ach:null,
   bg:'radial-gradient(circle at 30% 25%,rgba(200,150,255,.5) 0%,transparent 50%),linear-gradient(135deg,#6600cc,#9933ff,#3300aa,#cc00ff)',
   sh:'0 0 0 4px rgba(180,0,255,.4),0 0 40px rgba(150,0,255,.6),0 8px 30px rgba(0,0,0,.6)',an:'as',gl:'rgba(150,0,255,.2)'},
  {id:'diamond',n:'Бриллиантовый Бог',e:'💎',p:0,ach:'a8',
   bg:'radial-gradient(circle at 30% 20%,rgba(255,255,255,.9) 0%,transparent 40%),linear-gradient(135deg,#a8d8ff,#e0f4ff,#b8e8ff,#5cb8ff)',
   sh:'0 0 0 4px rgba(150,210,255,.5),0 0 50px rgba(100,200,255,.7),0 8px 30px rgba(0,0,0,.6)',an:'ap',gl:'rgba(150,220,255,.25)'},
  {id:'lava',n:'Магма Абсолют',e:'🌋',p:0,ach:'a14',
   bg:'radial-gradient(circle at 35% 25%,rgba(255,220,100,.6) 0%,transparent 45%),linear-gradient(135deg,#ff8c00,#cc2200,#ff4400,#881100)',
   sh:'0 0 0 4px rgba(255,100,0,.5),0 0 50px rgba(255,80,0,.7),0 8px 30px rgba(0,0,0,.7)',an:'ak',gl:'rgba(255,80,0,.25)'},
  {id:'rainbow',n:'Радужный Королевич',e:'🦄',p:0,ach:'a16',
   bg:'linear-gradient(135deg,#ff0080,#ff8c00,#ffed00,#00c800,#0080ff,#8000ff,#ff0080)',
   sh:'0 0 0 4px rgba(255,0,128,.4),0 0 50px rgba(128,0,255,.5),0 8px 30px rgba(0,0,0,.6)',an:'as',gl:'rgba(200,0,200,.2)'},
  {id:'shadow',n:'Тёмный Воин',e:'🖤',p:150000,ach:null,
   bg:'radial-gradient(circle at 35% 25%,rgba(100,0,200,.5) 0%,transparent 50%),linear-gradient(135deg,#1a0030,#2d0050,#0d001a,#3d0070)',
   sh:'0 0 0 4px rgba(100,0,200,.4),0 0 40px rgba(80,0,150,.6),0 8px 30px rgba(0,0,0,.8)',an:'ap',gl:'rgba(100,0,200,.2)'},
  {id:'cyber',n:'Кибер Мутант',e:'🤖',p:400000,ach:null,
   bg:'radial-gradient(circle at 35% 25%,rgba(0,255,200,.4) 0%,transparent 50%),linear-gradient(135deg,#001a1a,#003333,#00ff88,#002222)',
   sh:'0 0 0 4px rgba(0,255,180,.4),0 0 50px rgba(0,255,150,.5),0 8px 30px rgba(0,0,0,.7)',an:'as',gl:'rgba(0,255,150,.2)'},
];

// ═══ STATE ═══
let G={
  coins:0,allC:0,clicks:0,allU:0,crits:0,combos:0,
  pres:0,mult:1,lvl:1,xp:0,
  nrg:100,mxE:100,rgE:2,cpc:1,cps:0,pt:0,mxCps:0,mxCpc:1,
  critC:0,critM:2,aCps:0,offH:2,luck:0,combo:0,chain:0,gm:1,
  ul:{},achs:[],claimed:[],sk:['default'],skin:'default',
  lastSeen:null,comboN:0,chainV:0,
};
const SAVE_KEY='gym9';
function load(){try{const r=localStorage.getItem(SAVE_KEY);if(r)Object.assign(G,JSON.parse(r));}catch(e){}}
function save(){G.lastSeen=Date.now();try{localStorage.setItem(SAVE_KEY,JSON.stringify(G));}catch(e){}}

function fmt(n){
  n=Math.floor(n);
  if(n>=1e12)return(n/1e12).toFixed(1)+'T';
  if(n>=1e9)return(n/1e9).toFixed(1)+'B';
  if(n>=1e6)return(n/1e6).toFixed(1)+'M';
  if(n>=1000)return(n/1000).toFixed(1)+'K';
  return ''+n;
}
const uL=id=>G.ul[id]||0;
const uP=u=>Math.floor(u.bp*Math.pow(u.pg,uL(u.id)));

function recalc(){
  let cpc=1,cps=0,mxE=100,rgE=2,critC=0,critM=2,aCps=0,offH=2,luck=0,combo=0,chain=0,gm=1;
  for(const u of ALL_UG){
    const l=uL(u.id);if(!l)continue;
    if(u.ef==='cpc')cpc+=u.v*l;
    else if(u.ef==='cps')cps+=u.v*l;
    else if(u.ef==='mxE')mxE+=u.v*l;
    else if(u.ef==='rgE')rgE+=u.v*l;  // +0.3 per level
    else if(u.ef==='critC')critC+=u.v*l;
    else if(u.ef==='critM')critM+=u.v*l;
    else if(u.ef==='gm')gm+=u.v*l;
    else if(u.ef==='aCps')aCps+=u.v*l;
    else if(u.ef==='offH')offH+=u.v*l;
    else if(u.ef==='luck')luck+=u.v*l;
    else if(u.ef==='combo')combo+=u.v*l;
    else if(u.ef==='chain')chain+=u.v*l;
  }
  const tm=G.mult*gm;
  G.cpc=Math.max(1,Math.floor(cpc*tm));
  G.cps=parseFloat((cps*tm).toFixed(2));
  G.mxE=mxE;G.rgE=parseFloat(rgE.toFixed(2));
  G.critC=Math.min(critC,80);G.critM=critM;
  G.aCps=aCps;G.offH=offH;G.luck=luck;G.combo=combo;G.chain=chain;G.gm=gm;
  if(G.nrg>G.mxE)G.nrg=G.mxE;
  if(G.cps>G.mxCps)G.mxCps=G.cps;
  if(G.cpc>G.mxCpc)G.mxCpc=G.cpc;
}

function chkLvl(){
  while(G.lvl<LVS.length){
    const nx=LVS[G.lvl];if(!nx||G.xp<nx.x)break;
    G.lvl++;ntf('🎉 Уровень '+G.lvl+' — '+LVS[G.lvl-1].n);
  }
}
function chkAchs(){
  const s={clicks:G.clicks,allC:G.allC,allU:G.allU,cps:G.cps,pres:G.pres,lvl:G.lvl,crits:G.crits,combos:G.combos,ul:G.ul,sk:G.sk};
  for(const a of ACHS){
    if(G.achs.includes(a.id)||!a.c(s))continue;
    G.achs.push(a.id);
    if(a.r.t==='s'&&!G.sk.includes(a.r.v)){G.sk.push(a.r.v);G.claimed.push(a.id);}
    showAP(a);
  }
}
function claimR(id){
  const a=ACHS.find(x=>x.id===id);if(!a||G.claimed.includes(id))return;
  G.claimed.push(id);
  if(a.r.t==='c'){G.coins+=a.r.v;G.allC+=a.r.v;updateHUD();ntf('💰 +'+fmt(a.r.v)+' монет!');}
  else if(a.r.t==='s'&&!G.sk.includes(a.r.v)){G.sk.push(a.r.v);ntf('🎨 Скин разблокирован!');renderSkins();}
  save();renderAchs();
}
function presReq(){return 100000*Math.pow(5,G.pres);}
function prestige(){
  if(G.allC<presReq())return;
  G.pres++;G.mult=1+G.pres*0.5;
  G.coins=0;G.xp=0;G.lvl=1;G.nrg=G.mxE;G.ul={};G.chainV=0;G.comboN=0;
  recalc();chkAchs();updateHUD();renderAll();ntf('🔥 ПРЕСТИЖ! Множитель x'+G.mult.toFixed(1));
}

// ═══ CLICK ═══
let tbOn=false,tbM=1;
function doClick(x,y){
  if(G.nrg<1){ntf('⚡ Нет энергии!');return;}
  G.nrg=Math.max(0,G.nrg-1);G.chainV+=G.chain;
  let earn=G.cpc+G.chainV,crit=false;
  if(G.combo>0){G.comboN++;if(G.comboN>=10){earn*=10;G.comboN=0;G.combos++;spawnF('КОМБО x10!',x,y-30);}}
  if(G.critC>0&&Math.random()*100<G.critC){earn=Math.floor(earn*G.critM);crit=true;G.crits++;}
  if(G.luck>0&&Math.random()*100<G.luck){earn*=2;spawnF('УДАЧА x2!',x,y-30);}
  if(tbOn)earn=Math.floor(earn*tbM);
  earn=Math.floor(earn);
  G.coins+=earn;G.allC+=earn;G.clicks++;G.xp+=1;
  chkLvl();chkAchs();
  spawnF((crit?'💥 ':'+')+fmt(earn),x,y,crit?'#ff5500':null);
  spawnR(x,y);updateHUD();
}
function buyUpg(id){
  const u=ALL_UG.find(x=>x.id===id);if(!u)return;
  const l=uL(id);if(l>=u.mx)return;
  const p=uP(u);if(G.coins<p){ntf('💸 Недостаточно монет!');return;}
  G.coins-=p;G.ul[id]=l+1;G.allU++;G.xp+=10;
  if(u.ef==='tb'){tbOn=true;tbM=u.v;setTimeout(()=>tbOn=false,30000);ntf('🚀 x'+u.v+' монеты 30 сек!');}
  recalc();chkLvl();chkAchs();updateHUD();renderAll();
  if(u.ef!=='tb')ntf('✅ '+u.n+' — Ур.'+(l+1));
}
function tapSkin(id){
  const s=SKINS.find(x=>x.id===id);if(!s)return;
  if(s.ach&&!G.sk.includes(id)){ntf('🔒 Нужно достижение!');return;}
  if(G.sk.includes(id)){G.skin=id;applySkin(id);save();renderSkins();ntf('✅ Скин надет!');}
  else{
    if(G.coins<s.p){ntf('💸 Недостаточно монет!');return;}
    G.coins-=s.p;G.sk.push(id);G.skin=id;applySkin(id);save();updateHUD();renderSkins();ntf('🎉 Скин куплен!');
  }
}
function applySkin(id){
  const s=SKINS.find(x=>x.id===id)||SKINS[0];
  const b=document.getElementById('btn'),g=document.getElementById('glw');
  b.style.background=s.bg;b.style.boxShadow=s.sh;b.textContent=s.e;
  b.className=b.className.replace(/\\b(ab|as|ap|ak)\\b/g,'').trim();
  if(s.an)b.classList.add(s.an);
  if(g)g.style.background='radial-gradient(circle,'+s.gl+' 0%,transparent 70%)';
  document.getElementById('btnProf').textContent=s.e;
  document.getElementById('drAva').textContent=s.e;
}

// ═══ MULTITOUCH ═══
function initBtn(){
  const b=document.getElementById('btn');
  b.addEventListener('touchstart',function(e){
    e.preventDefault();
    this.classList.add('tap');setTimeout(()=>this.classList.remove('tap'),300);
    for(const t of e.changedTouches)doClick(t.clientX,t.clientY);
  },{passive:false});
  b.addEventListener('mousedown',function(e){
    this.classList.add('tap');setTimeout(()=>this.classList.remove('tap'),300);doClick(e.clientX,e.clientY);
  });
}

// ═══ HUD ═══
function updateHUD(){
  document.getElementById('hCoins').textContent=fmt(G.coins);
  document.getElementById('hCph').textContent=fmt(G.cps*3600)+'/ч';
  document.getElementById('cCpc').textContent='+'+fmt(G.cpc);
  document.getElementById('cCps').textContent=fmt(G.cps+G.aCps);
  document.getElementById('cMlt').textContent='x'+G.mult.toFixed(1);
  document.getElementById('cCrt').textContent=G.critC+'%';
  document.getElementById('nrgTxt').textContent=Math.floor(G.nrg)+'/'+G.mxE;
  document.getElementById('nrgFill').style.width=(G.nrg/G.mxE*100)+'%';
  const ci=G.lvl-1,cx=LVS[ci]?.x||0,nx=LVS[G.lvl]?.x??(LVS[LVS.length-1].x+999999);
  document.getElementById('xpFill').style.width=Math.min(100,(G.xp-cx)/(nx-cx)*100)+'%';
  document.getElementById('xpTxt').textContent=fmt(G.xp-cx)+'/'+fmt(nx-cx);
  document.getElementById('hLvlI').textContent=G.lvl;
  document.getElementById('hLvlN').textContent=LVS[G.lvl-1]?.n||'АБСОЛЮТ';
  document.getElementById('presReq').textContent=fmt(presReq());
  document.getElementById('presBtn').disabled=G.allC<presReq();
  document.getElementById('lbMe').textContent=fmt(G.cps*3600)+'/ч';
  document.getElementById('offMaxH').textContent=Math.floor(G.offH||2);
  document.getElementById('btn').classList.toggle('dead',G.nrg<1);
  // profile
  const nick=getNick()||'Игрок';
  document.getElementById('drName').textContent=nick;
  document.getElementById('drLvl').textContent=G.lvl;
  document.getElementById('drLvlN').textContent=LVS[G.lvl-1]?.n||'АБСОЛЮТ';
  document.getElementById('pp-tc').textContent=fmt(G.allC);
  document.getElementById('pp-cl').textContent=fmt(G.clicks);
  document.getElementById('pp-pr').textContent=G.pres;
  const m=Math.floor(G.pt/60),h=Math.floor(m/60);
  document.getElementById('pp-pt').textContent=h>0?h+'ч':m+'м';
  document.getElementById('pp-ms').textContent=fmt(G.mxCps);
  document.getElementById('pp-mc').textContent='+'+fmt(G.mxCpc);
  document.getElementById('pp-cr').textContent=fmt(G.crits);
  document.getElementById('pp-sk').textContent=G.sk.length;
}

// ═══ RENDER ═══
function effText(u){
  if(u.ef==='cpc')return'+'+u.v+' за клик';
  if(u.ef==='cps')return'+'+u.v+'/сек · +'+fmt(u.v*3600)+'/ч';
  if(u.ef==='mxE')return'+'+u.v+' энергии';
  if(u.ef==='rgE')return'+'+u.v.toFixed(1)+' восст./сек';
  if(u.ef==='critC')return'+'+u.v+'% крит шанс';
  if(u.ef==='critM')return'+'+u.v+'x крит урон';
  if(u.ef==='gm')return'+'+(u.v*100)+'% к монетам';
  if(u.ef==='aCps')return'+'+u.v+' авто/сек';
  if(u.ef==='offH')return'+'+u.v+'ч оффлайна';
  if(u.ef==='luck')return'+'+u.v+'% удвоить';
  if(u.ef==='combo')return'каждый 10-й клик x10';
  if(u.ef==='chain')return'каждый клик подряд +1';
  if(u.ef==='tb')return'x'+u.v+' монеты на 30 сек';
  return '';
}
function effText(u){
  if(u.ef==="cpc")return"+"+u.v+" за клик";
  if(u.ef==="cps")return"+"+u.v+"/сек · +"+fmt(u.v*3600)+"/ч";
  if(u.ef==="mxE")return"+"+u.v+" энергии";
  if(u.ef==="rgE")return"+"+u.v.toFixed(1)+" восст./сек";
  if(u.ef==="critC")return"+"+u.v+"% крит шанс";
  if(u.ef==="critM")return"+"+u.v+"x крит урон";
  if(u.ef==="gm")return"+"+(u.v*100)+"% к монетам";
  if(u.ef==="aCps")return"+"+u.v+" авто/сек";
  if(u.ef==="offH")return"+"+u.v+"ч оффлайна";
  if(u.ef==="luck")return"+"+u.v+"% удвоить";
  if(u.ef==="combo")return"каждый 10-й клик x10";
  if(u.ef==="chain")return"каждый клик подряд +1";
  if(u.ef==="tb")return"x"+u.v+" монеты на 30 сек";
  return "";
}
function renderList(cid,list){
  const el=document.getElementById(cid);if(!el)return;
  const coins=G.coins;
  el.innerHTML=list.map(u=>{
    const l=uL(u.id),mx=l>=u.mx,p=uP(u),ok=!mx&&coins>=p;
    const cls="upg"+(ok?" ok":"")+(mx?" mx":"");
    const priceHtml=mx
      ?'<div class="upg-pv" style="color:var(--gn)">МАКС</div>'
      :'<div class="upg-pv'+(ok?"":"\ no")+'">'+ fmt(p)+'</div><div class="upg-pl">монет</div>';
    return '<div class="'+cls+'" data-uid="'+u.id+'">'+
      '<div class="upg-i">'+u.i+'</div>'+
      '<div class="upg-b">'+
        '<div class="upg-n">'+u.n+'</div>'+
        '<div class="upg-d">'+u.d+'</div>'+
        '<div class="upg-e">'+effText(u)+'</div>'+
        '<div class="upg-l">Ур. '+l+' / '+u.mx+'</div>'+
      '</div>'+
      '<div class="upg-p">'+priceHtml+'</div>'+
      '</div>';
  }).join("");
}
function renderSkins(){
  const el=document.getElementById("skinList");if(!el)return;
  el.innerHTML=SKINS.map(s=>{
    const own=G.sk.includes(s.id),eq=G.skin===s.id,alck=s.ach&&!own,ok=!own&&!alck&&G.coins>=s.p;
    let badge="";
    if(eq)badge='<span class="sk-bdg b-eq">✓ НАДЕТ</span>';
    else if(own)badge='<span class="sk-bdg b-own">КУПЛЕН</span>';
    else if(alck)badge='<span class="sk-bdg b-ac">🏆 АЧИВ</span>';
    else if(s.p>0)badge='<span class="sk-bdg b-lk">🔒</span>';
    let price="";
    if(s.p===0&&!alck)price='<div class="sk-p" style="color:var(--gn)">БЕСПЛАТНО</div>';
    else if(alck){const a=ACHS.find(x=>x.id===s.ach);price='<div class="sk-p ac">'+(a?a.n:"Достижение")+'</div>';}
    else if(own)price=eq?'<div class="sk-p" style="color:var(--gn)">НАДЕТ</div>':'<div class="sk-p" style="color:var(--or)">НАДЕТЬ</div>';
    else price='<div class="sk-p'+(ok?"":" no")+'">'+fmt(s.p)+' 💰</div>';
    const cls="sk"+(eq?" eq":own?" own":alck?" ak":ok?" ok":" lk");
    return '<div class="'+cls+'" data-sid="'+s.id+'">'+
      badge+
      '<div class="sk-prev" style="background:'+s.bg+';box-shadow:'+s.sh+'">'+s.e+'</div>'+
      '<div class="sk-n">'+s.n+'</div>'+
      price+
      '</div>';
  }).join("");
}
function renderAchs(){
  const el=document.getElementById("achList");if(!el)return;
  el.innerHTML=ACHS.map(a=>{
    const done=G.achs.includes(a.id),cl=G.claimed.includes(a.id);
    let rv=a.r.t==="c"?"💰 "+fmt(a.r.v)+" монет":"";
    if(a.r.t==="s"){const sk=SKINS.find(x=>x.id===a.r.v);rv="🎨 "+(sk?sk.n:"скин");}
    let right="";
    if(done&&!cl)right='<button class="ach-btn" data-aid="'+a.id+'">ЗАБРАТЬ</button>';
    else if(done&&cl)right='<div class="ach-got">✓</div>';
    return '<div class="ach'+(done?" on":"")+'">'+
      '<div class="ach-i">'+a.i+'</div>'+
      '<div class="ach-b">'+
        '<div class="ach-n">'+a.n+'</div>'+
        '<div class="ach-d">'+( done?a.d:"???")+'</div>'+
        '<div class="ach-r">'+rv+'</div>'+
      '</div>'+
      (done?"<div>"+right+"</div>":"")+
      '</div>';
  }).join("");
}

function spawnF(t,x,y,col){
  const el=document.createElement('div');el.className='ftxt';el.textContent=t;
  if(col)el.style.color=col;
  el.style.left=(x+Math.random()*40-20)+'px';el.style.top=(y-10)+'px';
  document.body.appendChild(el);setTimeout(()=>el.remove(),900);
}
function spawnR(x,y){
  const el=document.createElement('div');el.className='rip';
  el.style.cssText='left:'+(x-25)+'px;top:'+(y-25)+'px;width:50px;height:50px';
  document.body.appendChild(el);setTimeout(()=>el.remove(),450);
}

// ═══ NOTIF ═══
let ntfT;
function ntf(msg){
  const el=document.getElementById('notif');el.textContent=msg;el.classList.add('on');
  clearTimeout(ntfT);ntfT=setTimeout(()=>el.classList.remove('on'),2200);
}
let apQ=[],apB=false;
function showAP(a){apQ.push(a);if(!apB)nextAP();}
function nextAP(){
  if(!apQ.length){apB=false;return;}apB=true;const a=apQ.shift();
  document.getElementById('apop-i').textContent=a.i;
  document.getElementById('apN').textContent=a.n;
  let rw=a.r.t==='c'?'Награда: 💰'+fmt(a.r.v):'';
  if(a.r.t==='s'){const s=SKINS.find(x=>x.id===a.r.v);rw='Награда: 🎨 '+(s?s.n:'скин');}
  document.getElementById('apR').textContent=rw;
  document.getElementById('apop').classList.add('on');
  setTimeout(()=>{document.getElementById('apop').classList.remove('on');setTimeout(nextAP,400);},3000);
}

// ═══ TABS ═══
// Event delegation for all dynamic content
document.getElementById("tabs").addEventListener("click",e=>{
  const b=e.target.closest(".tab");if(!b)return;
  const t=b.dataset.t;
  document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("on",x.dataset.t===t));
  document.querySelectorAll(".panel").forEach(x=>x.classList.toggle("on",x.id==="panel-"+t));
  if(t==="top")loadLB();
});
// Upgrade click delegation
document.body.addEventListener("click",e=>{
  const upg=e.target.closest("[data-uid]");
  if(upg){buyUpg(upg.dataset.uid);return;}
  const sk=e.target.closest("[data-sid]");
  if(sk){tapSkin(sk.dataset.sid);return;}
  const ab=e.target.closest("[data-aid]");
  if(ab){claimR(ab.dataset.aid);return;}
});

// ═══ PROFILE DRAWER ═══
function openDr(){
  document.getElementById('ov').classList.add('on');
  document.getElementById('dr').classList.add('on');
  updateHUD();renderAchs();renderSkins();
  const n=getNick();if(n)document.getElementById('nickEdit').value=n;
}
function closeDr(){
  document.getElementById('ov').classList.remove('on');
  document.getElementById('dr').classList.remove('on');
}
document.querySelectorAll('.dr-tab').forEach(b=>{
  b.addEventListener('click',function(){
    const p=this.dataset.p;
    document.querySelectorAll('.dr-tab').forEach(x=>x.classList.toggle('on',x.dataset.p===p));
    document.querySelectorAll('.drpan').forEach(x=>x.classList.toggle('on',x.id==='drpan-'+p));
    if(p==='achs')renderAchs();if(p==='skins')renderSkins();
  });
});
function changeNick(){
  const v=document.getElementById('nickEdit').value.trim();
  if(v.length<2||v.length>20){ntf('Ник: 2-20 символов');return;}
  localStorage.setItem('gymNick',v);updateHUD();save();ntf('✅ Ник: '+v);pushScore();
}

// ═══ OFFLINE ═══
let _offE=0;
function chkOffline(){
  if(!G.lastSeen||G.cps<=0)return;
  const mx=(G.offH||2)*3600,sec=Math.min((Date.now()-G.lastSeen)/1000,mx);
  if(sec<30)return;
  _offE=Math.floor(G.cps*sec);if(!_offE)return;
  const h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),s=Math.floor(sec%60);
  let t=h?h+'ч ':''+(m?m+'мин ':''+(h===0&&s?s+'сек':''));
  document.getElementById('offT').textContent='Отсутствовал: '+t.trim();
  document.getElementById('offE').textContent='+'+fmt(_offE);
  document.getElementById('offpop').classList.add('on');
}
function claimOff(){
  G.coins+=_offE;G.allC+=_offE;G.xp+=Math.floor(_offE*.05);
  chkLvl();chkAchs();updateHUD();
  document.getElementById('offpop').classList.remove('on');
  ntf('💰 Получено '+fmt(_offE)+' монет!');
}

// ═══ NICK ═══
function getNick(){
  const s=localStorage.getItem('gymNick');if(s)return s;
  if(window.Telegram?.WebApp?.initDataUnsafe?.user){
    const u=Telegram.WebApp.initDataUnsafe.user;return u.username||u.first_name||('user'+u.id);
  }
  return null;
}
function getId(){
  if(window.Telegram?.WebApp?.initDataUnsafe?.user)return''+Telegram.WebApp.initDataUnsafe.user.id;
  let id=localStorage.getItem('gymId');if(!id){id='anon_'+Date.now();localStorage.setItem('gymId',id);}return id;
}
function chkNick(){
  if(!getNick()){
    document.getElementById('nickpop').classList.add('on');
    setTimeout(()=>document.getElementById('nickIn').focus(),350);
  }
}
function saveNick(){
  const v=document.getElementById('nickIn').value.trim();
  const h=document.getElementById('nickHint');
  if(v.length<2){h.textContent='Минимум 2 символа!';return;}
  if(v.length>20){h.textContent='Максимум 20 символов!';return;}
  localStorage.setItem('gymNick',v);
  document.getElementById('nickpop').classList.remove('on');
  ntf('👋 Привет, '+v+'!');pushScore();
}
document.getElementById('nickIn').addEventListener('keydown',e=>{if(e.key==='Enter')saveNick();});

// ═══ LEADERBOARD ═══
const API=window.location.origin;
async function pushScore(){
  const nick=getNick();if(!nick||G.cps<=0)return;
  try{
    await fetch(API+'/api/score',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user_id:getId(),username:nick,cph:Math.floor(G.cps*3600),prestiges:G.pres})});
  }catch(e){}
}
function buildPod(rows){
  const el=document.getElementById('lbPod');if(!rows?.length){el.innerHTML='';return;}
  const myN=getNick(),t3=rows.slice(0,3);
  const ord=t3.length>=2?[t3[1],t3[0],t3[2]].filter(Boolean):[t3[0]];
  const cls=t3.length>=2?['p2','p1','p3']:['p1'];
  const nums=t3.length>=2?[2,1,3]:[1];
  el.innerHTML='<div class="pod"><div class="pod-t">🏆 Зал Славы</div><div class="pod-s">'
    +ord.map((r,i)=>{
      const me=r.username===myN;
      return '<div class="pod-sl '+cls[i]+'">'
        +'<div class="pod-cr">'+(nums[i]===1?'👑':'')+'</div>'
        +'<div class="pod-ci">💪</div>'
        +'<div class="pod-nm"'+(me?' style="color:var(--gn)"':'')+'>'+r.username+(me?' 👈':'')+'</div>'
        +'<div class="pod-cp">'+fmt(r.cph)+'/ч</div>'
        +'<div class="pod-bk">'+nums[i]+'</div>'
        +'</div>';
    }).join('')
    +'</div></div>';
}
async function loadLB(){
  const el=document.getElementById('lbList');
  el.innerHTML='<div class="lb-em">Загрузка...</div>';
  document.getElementById('lbPod').innerHTML='';
  try{
    const rows=await fetch(API+'/api/leaderboard').then(r=>r.json());
    buildPod(rows);
    const rest=rows.slice(3);
    if(!rest.length){el.innerHTML='';return;}
    const myN=getNick();
    el.innerHTML='<div class="pod-div"></div>'+rest.map((r,i)=>{
      const me=r.username===myN;
      return '<div class="lb-row'+(me?' me':'')+'">'
        +'<div class="lb-rk">'+(i+4)+'</div>'
        +'<div class="lb-nm">'+r.username+(me?' 👈':'')+'</div>'
        +'<div style="text-align:right;flex-shrink:0">'
          +'<div class="lb-cp">'+fmt(r.cph)+'/ч</div>'
          +(r.prestiges>0?'<div style="font-size:10px;color:var(--mt)">🔥'+r.prestiges+'</div>':'')
        +'</div></div>';
    }).join('');
  }catch(e){
    document.getElementById('lbPod').innerHTML='';
    el.innerHTML='<div class="lb-em">Ошибка загрузки</div>';
  }
}
setInterval(pushScore,30000);

// ═══ GAME LOOP ═══
let lastT=Date.now();
function tick(){
  const now=Date.now(),dt=Math.min((now-lastT)/1000,.5);lastT=now;
  const totCps=G.cps+G.aCps*G.cpc;
  if(totCps>0){const e=totCps*dt;G.coins+=e;G.allC+=e;G.xp+=e*.1;chkLvl();}
  G.nrg=Math.min(G.mxE,G.nrg+G.rgE*dt);
  G.pt+=dt;updateHUD();
}
setInterval(tick,100);
setInterval(save,5000);
setInterval(renderAll,1000);
setInterval(chkAchs,2000);
document.addEventListener('visibilitychange',()=>{if(document.hidden)save();});
window.addEventListener('pagehide',save);

// ═══ INIT ═══
load();
recalc();
initBtn();
applySkin(G.skin||'default');
updateHUD();
renderAll();
chkOffline();
chkNick();
if(window.Telegram?.WebApp){Telegram.WebApp.ready();Telegram.WebApp.expand();}
</script>
</body>
</html>


"""

# ─── Веб-сервер ───────────────────────────────────────────────────────────────
class GameHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Frame-Options", "ALLOWALL")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/leaderboard":
            data = json.dumps(get_top(20)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/score":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                user_id   = data.get("user_id", "unknown")
                username  = data.get("username", "Игрок")[:32]
                cph       = float(data.get("cph", 0))
                prestiges = int(data.get("prestiges", 0))
                upsert_score(user_id, username, cph, prestiges)
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                logger.warning("[API] score error: %s", e)
                self.send_response(400)
                self._cors()
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

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
    init_db()
    # Веб-сервер в фоновом потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    # Бот в основном потоке
    run_bot()

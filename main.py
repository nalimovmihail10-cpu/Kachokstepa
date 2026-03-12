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
:root{--bg:#0d0d16;--c1:#161624;--c2:#1c1c2e;--gd:#ffd700;--or:#ff6200;--gn:#39ff14;--rd:#ff2244;--bl:#00c8ff;--tx:#f0e6d3;--mt:#6b6480}
body{background:var(--bg);color:var(--tx);font-family:'Nunito',sans-serif;overflow-x:hidden;min-height:100vh}
#hdr{position:sticky;top:0;z-index:80;background:rgba(13,13,22,.97);border-bottom:1px solid rgba(255,215,0,.08);padding:10px 14px 8px;display:flex;align-items:center;gap:10px}
#profBtn{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--or),var(--gd));border:2px solid rgba(255,215,0,.3);font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.hm{flex:1;text-align:center}.hc{font-size:24px;font-weight:900;color:var(--gd);line-height:1}.hl{font-size:10px;color:var(--mt)}
.hr{display:flex;flex-direction:column;align-items:flex-end}.hcph{font-size:14px;font-weight:800;color:var(--gn)}.hcphl{font-size:10px;color:var(--mt)}
#xpbar{padding:5px 14px 8px;background:rgba(13,13,22,.7)}
.xrow{display:flex;justify-content:space-between;font-size:10px;color:var(--mt);margin-bottom:4px}
.xt{height:5px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden}
.xf{height:100%;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:3px;transition:width .4s}
#chips{display:flex;gap:6px;padding:8px 14px}
.chip{flex:1;background:var(--c1);border:1px solid rgba(255,215,0,.1);border-radius:10px;padding:7px 4px;text-align:center}
.chipv{font-size:14px;font-weight:900;color:var(--gd);line-height:1}.chipl{font-size:9px;color:var(--mt);margin-top:2px}
#clicker{display:flex;flex-direction:column;align-items:center;padding:10px 14px 6px}
.nrg{width:100%;max-width:320px;margin-bottom:12px}
.nrgt{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
.nrgl{color:var(--or);font-weight:800;letter-spacing:1px}
.nrgb{height:7px;background:rgba(255,255,255,.07);border-radius:4px;overflow:hidden;border:1px solid rgba(255,100,0,.15)}
.nrgf{height:100%;background:linear-gradient(90deg,#ff3c00,var(--or),#ffa500);border-radius:4px;transition:width .12s linear}
.coinwrap{position:relative;display:flex;align-items:center;justify-content:center;margin:2px 0}
.glow{position:absolute;width:210px;height:210px;border-radius:50%;pointer-events:none;background:radial-gradient(circle,rgba(255,200,0,.18) 0%,transparent 70%);animation:gp 2s ease-in-out infinite}
@keyframes gp{0%,100%{transform:scale(1);opacity:.8}50%{transform:scale(1.12);opacity:1}}
#coin{width:175px;height:175px;border-radius:50%;border:none;cursor:pointer;position:relative;z-index:10;font-size:82px;line-height:1;display:flex;align-items:center;justify-content:center;touch-action:none;-webkit-user-select:none;user-select:none;background:radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),radial-gradient(circle at 70% 72%,rgba(170,90,0,.3) 0%,transparent 50%),linear-gradient(135deg,#f5c518,#e8a800,#ffd700,#cc8800,#e8a800);box-shadow:0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4),0 8px 30px rgba(0,0,0,.6);transition:transform .08s,filter .2s}
#coin.tap{transform:scale(.88)}
#coin.dead{filter:grayscale(.7) brightness(.5)}
.ft{position:fixed;pointer-events:none;z-index:9999;font-size:20px;font-weight:900;color:var(--gd);text-shadow:0 0 10px rgba(255,200,0,.9);animation:fup .9s ease-out forwards;white-space:nowrap}
@keyframes fup{0%{opacity:1;transform:translateY(0)}50%{opacity:1;transform:translateY(-38px) scale(1.15)}100%{opacity:0;transform:translateY(-80px) scale(.8)}}
.rp{position:fixed;pointer-events:none;z-index:9998;border-radius:50%;background:rgba(255,200,0,.25);animation:ro .45s ease-out forwards}
@keyframes ro{0%{transform:scale(0);opacity:.8}100%{transform:scale(3.5);opacity:0}}
#tabs{display:flex;gap:4px;padding:8px 14px 0;overflow-x:auto;scrollbar-width:none}
#tabs::-webkit-scrollbar{display:none}
.tab{flex-shrink:0;padding:10px 14px;background:var(--c1);border:1px solid rgba(255,255,255,.07);border-radius:10px;color:var(--mt);font-family:'Nunito',sans-serif;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}
.tab.on{background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,215,0,.1));border-color:rgba(255,215,0,.4);color:var(--gd)}
.panel{display:none;padding:10px 14px 120px}.panel.on{display:block}
.sec{font-size:10px;font-weight:800;letter-spacing:2.5px;color:var(--mt);text-transform:uppercase;margin:14px 0 10px;padding-bottom:5px;border-bottom:1px solid rgba(255,255,255,.05)}.sec:first-child{margin-top:4px}
.upg{background:var(--c1);border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:16px;display:flex;align-items:center;gap:14px;margin-bottom:10px;cursor:pointer;position:relative;overflow:hidden}
.upg.ok{border-color:rgba(255,215,0,.3)}.upg.ok::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,100,0,.05),rgba(255,215,0,.05));pointer-events:none}
.upg.mx{opacity:.4;cursor:default}
.uico{width:58px;height:58px;border-radius:14px;flex-shrink:0;font-size:28px;display:flex;align-items:center;justify-content:center;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.14)}
.ubod{flex:1;min-width:0}.unam{font-size:14px;font-weight:800;color:var(--tx);margin-bottom:3px}.udsc{font-size:11px;color:var(--mt);line-height:1.35}.ueff{font-size:11px;color:var(--bl);font-weight:700;margin-top:3px}.ulvl{font-size:10px;color:var(--or);font-weight:700;margin-top:3px}
.uprc{flex-shrink:0;text-align:right;min-width:58px}.uprv{font-size:14px;font-weight:900;color:var(--gd)}.uprv.no{color:var(--rd)}.uprl{font-size:10px;color:var(--mt);margin-top:1px}
.lbme{background:rgba(57,255,20,.06);border:1px solid rgba(57,255,20,.2);border-radius:12px;padding:12px 14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}
.lbmel{font-size:11px;color:var(--gn);font-weight:800}.lbmev{font-size:16px;font-weight:900;color:var(--gd)}
.lbref{width:100%;padding:11px;border-radius:10px;border:1px solid rgba(255,100,0,.3);background:rgba(255,100,0,.1);color:var(--or);font-family:'Nunito',sans-serif;font-size:13px;font-weight:700;cursor:pointer;margin-bottom:10px}
.pod{text-align:center;padding:4px 0 18px}.podt{font-size:10px;font-weight:800;letter-spacing:3px;color:var(--mt);text-transform:uppercase;margin-bottom:14px}
.pods{display:flex;align-items:flex-end;justify-content:center;gap:8px}
.podsl{display:flex;flex-direction:column;align-items:center;flex:1;max-width:110px}
.podc{font-size:18px;margin-bottom:2px;min-height:22px}
.podci{border-radius:50%;display:flex;align-items:center;justify-content:center;margin-bottom:5px;flex-shrink:0}
.p1 .podci{width:80px;height:80px;font-size:44px;background:linear-gradient(135deg,#f5c518,#ffd700,#d4a010);box-shadow:0 0 22px rgba(255,200,0,.6)}
.p2 .podci{width:64px;height:64px;font-size:34px;background:linear-gradient(135deg,#bdbdbd,#e0e0e0,#9e9e9e)}
.p3 .podci{width:56px;height:56px;font-size:30px;background:linear-gradient(135deg,#bf7b3b,#d4924a,#9e5e1e)}
.podnm{font-size:11px;font-weight:800;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;width:100%;margin-bottom:2px}
.podcp{font-size:10px;color:var(--gd);font-weight:700}
.podbk{border-radius:9px 9px 0 0;width:100%;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:rgba(0,0,0,.35)}
.p1 .podbk{height:68px;background:linear-gradient(180deg,#c49a00,#a07800)}
.p2 .podbk{height:50px;background:linear-gradient(180deg,#8f8f8f,#6e6e6e)}
.p3 .podbk{height:38px;background:linear-gradient(180deg,#8f5a18,#6a3e0c)}
.poddiv{height:1px;background:rgba(255,255,255,.05);margin:8px 0 14px}
.lbrow{background:var(--c1);border:1px solid rgba(255,255,255,.05);border-radius:12px;padding:12px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px}
.lbrow.me{border-color:rgba(57,255,20,.4);background:linear-gradient(135deg,rgba(57,255,20,.07),transparent)}
.lbrk{width:28px;text-align:center;font-size:14px;font-weight:900;color:var(--mt);flex-shrink:0}
.lbnm{flex:1;font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lbrow.me .lbnm{color:var(--gn)}.lbcp{font-size:14px;font-weight:900;color:var(--gd);flex-shrink:0}
.lbem{text-align:center;padding:30px 20px;color:var(--mt);font-size:13px}
.task{background:var(--c1);border:1px solid rgba(255,215,0,.15);border-radius:16px;padding:16px;display:flex;align-items:center;gap:14px;margin-bottom:10px}
.task.done{opacity:.5;pointer-events:none}
.taskico{font-size:36px;flex-shrink:0}.taskbod{flex:1;min-width:0}
.tasknam{font-size:14px;font-weight:800;color:var(--tx);margin-bottom:3px}
.taskdsc{font-size:11px;color:var(--mt);line-height:1.35}
.taskrew{font-size:11px;color:var(--gd);font-weight:700;margin-top:4px}
.taskbtn{flex-shrink:0;padding:10px 14px;border-radius:10px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:'Nunito',sans-serif;font-size:12px;font-weight:900;color:#000;cursor:pointer}
#ov{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,0);pointer-events:none;transition:background .3s}
#ov.on{background:rgba(0,0,0,.65);pointer-events:all}
#dr{position:fixed;top:0;left:-110%;width:88%;max-width:380px;height:100vh;z-index:201;background:var(--c2);border-right:1px solid rgba(255,215,0,.12);display:flex;flex-direction:column;transition:left .35s cubic-bezier(.25,.46,.45,.94);overflow:hidden}
#dr.on{left:0}
.drh{flex-shrink:0;padding:20px 18px 0;background:linear-gradient(180deg,rgba(255,100,0,.1),transparent);border-bottom:1px solid rgba(255,215,0,.1)}
.drhead{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.drava{width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,var(--or),var(--gd));display:flex;align-items:center;justify-content:center;font-size:32px;flex-shrink:0;border:3px solid rgba(255,215,0,.4)}
.drinfo{flex:1;min-width:0}.drname{font-size:19px;font-weight:900;color:var(--gd);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.drsub{font-size:12px;color:var(--mt);margin-top:3px}
.drcl{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.07);border:none;color:var(--mt);font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.nrow{display:flex;gap:8px;margin-bottom:16px}
.nei{flex:1;padding:10px 13px;border-radius:10px;border:1.5px solid rgba(255,215,0,.2);background:rgba(255,255,255,.06);color:var(--tx);font-family:'Nunito',sans-serif;font-size:14px;font-weight:700;outline:none;-webkit-appearance:none}
.nei:focus{border-color:rgba(255,215,0,.5)}
.neb{padding:10px 16px;border-radius:10px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;color:#000;cursor:pointer}
.drtabs{display:flex;background:rgba(0,0,0,.3);border-bottom:1px solid rgba(255,215,0,.08);flex-shrink:0}
.drtab{flex:1;padding:13px 6px;background:transparent;border:none;color:var(--mt);font-family:'Nunito',sans-serif;font-size:11px;font-weight:700;cursor:pointer;text-align:center;border-bottom:2px solid transparent}
.drtab.on{color:var(--gd);border-bottom-color:var(--gd)}
.drbody{flex:1;overflow-y:auto;padding:14px 18px 40px;scrollbar-width:none}
.drbody::-webkit-scrollbar{display:none}
.drp{display:none}.drp.on{display:block}
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:4px}
.sc{background:var(--c1);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:15px}
.scv{font-size:20px;font-weight:900;color:var(--gd)}.scl{font-size:10px;color:var(--mt);margin-top:3px}
.ach{background:var(--c1);border:1px solid rgba(255,255,255,.05);border-radius:16px;padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:13px;opacity:.35}
.ach.on{opacity:1;border-color:rgba(255,215,0,.18);background:linear-gradient(135deg,rgba(255,100,0,.06),rgba(255,215,0,.04))}
.achi{font-size:30px;flex-shrink:0;width:44px;text-align:center}
.achb{flex:1;min-width:0}.achn{font-size:14px;font-weight:800}
.achd{font-size:11px;color:var(--mt);margin-top:2px;line-height:1.3}
.achr{font-size:10px;color:var(--bl);font-weight:700;margin-top:5px}
.achbtn{background:linear-gradient(135deg,var(--or),var(--gd));border:none;border-radius:9px;padding:8px 13px;font-family:'Nunito',sans-serif;font-size:11px;font-weight:900;color:#000;cursor:pointer;flex-shrink:0}
.achgot{font-size:11px;color:var(--gn);font-weight:700;flex-shrink:0}
.skgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sk{background:var(--c1);border:2px solid rgba(255,255,255,.07);border-radius:16px;padding:16px 12px;display:flex;flex-direction:column;align-items:center;gap:9px;cursor:pointer;position:relative;overflow:hidden}
.sk.ok{border-color:rgba(255,215,0,.3)}.sk.own{border-color:rgba(57,255,20,.3)}
.sk.eq{border-color:rgba(57,255,20,.75);background:linear-gradient(135deg,rgba(57,255,20,.08),transparent)}
.sk.lk{opacity:.5}.sk.ak{opacity:.55;cursor:default}
.skprev{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:36px;flex-shrink:0}
.skn{font-size:12px;font-weight:800;text-align:center;color:var(--tx);line-height:1.3}
.skp{font-size:12px;font-weight:700;color:var(--gd);text-align:center}.skp.no{color:var(--rd)}.skp.ac{color:var(--bl);font-size:10px}
.skbdg{position:absolute;top:6px;right:6px;font-size:9px;font-weight:800;padding:2px 6px;border-radius:20px}
.beq{background:rgba(57,255,20,.2);color:var(--gn)}.bown{background:rgba(57,255,20,.12);color:var(--gn)}.blk{background:rgba(255,255,255,.07);color:var(--mt)}.bac{background:rgba(0,200,255,.15);color:var(--bl)}
.coin-soon-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;min-height:60vh;text-align:center}
.coin-spin-wrap{width:160px;height:160px;margin-bottom:28px;position:relative;display:flex;align-items:center;justify-content:center}
.coin-spin{font-size:110px;line-height:1;animation:coinspin 3s linear infinite;display:block;filter:drop-shadow(0 0 24px rgba(255,200,0,.7))}
@keyframes coinspin{0%{transform:rotateY(0deg) scale(1)}25%{transform:rotateY(90deg) scale(.9)}50%{transform:rotateY(180deg) scale(1)}75%{transform:rotateY(270deg) scale(.9)}100%{transform:rotateY(360deg) scale(1)}}
.coin-soon-title{font-size:36px;font-weight:900;color:var(--gd);letter-spacing:4px;margin-bottom:8px;text-shadow:0 0 20px rgba(255,200,0,.5)}
.coin-soon-sub{font-size:18px;font-weight:800;color:var(--or);letter-spacing:6px;text-transform:uppercase;margin-bottom:20px}
.coin-soon-desc{font-size:13px;color:var(--mt);line-height:1.7;margin-bottom:28px;max-width:280px}
.coin-soon-btn{display:inline-block;padding:14px 28px;border-radius:14px;background:linear-gradient(135deg,var(--or),var(--gd));color:#000;font-family:'Nunito',sans-serif;font-size:14px;font-weight:900;text-decoration:none;box-shadow:0 4px 18px rgba(255,100,0,.4)}
.upg-timer{font-size:10px;color:var(--or);font-weight:800;margin-top:4px;letter-spacing:.5px}
.upg-timer.ready{color:var(--gn)}
.upg.upgrading{border-color:rgba(255,100,0,.5);background:linear-gradient(135deg,rgba(255,100,0,.08),var(--c1))}
.upg.upgrading::after{content:'';position:absolute;bottom:0;left:0;height:3px;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:0 0 16px 16px;animation:none;transition:width .5s linear}
.upg-prog{position:absolute;bottom:0;left:0;height:3px;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:0 0 16px 16px;transition:width .5s linear}
#notif{position:fixed;top:66px;left:50%;transform:translateX(-50%) translateY(-14px);background:linear-gradient(135deg,var(--or),var(--gd));color:#000;font-weight:900;font-size:13px;padding:9px 20px;border-radius:30px;z-index:9999;opacity:0;pointer-events:none;transition:all .25s;white-space:nowrap}
#notif.on{opacity:1;transform:translateX(-50%) translateY(0)}
#apop{position:fixed;bottom:-100px;left:50%;transform:translateX(-50%);background:var(--c2);border:1px solid rgba(255,215,0,.35);border-radius:16px;padding:14px 20px;display:flex;align-items:center;gap:12px;z-index:9999;transition:bottom .35s cubic-bezier(.175,.885,.32,1.275);min-width:270px}
#apop.on{bottom:18px}
#apopi{font-size:34px}.apl{font-size:10px;color:var(--gd);letter-spacing:2px;font-weight:800}.apn{font-size:14px;font-weight:900}.apr{font-size:11px;color:var(--bl);margin-top:2px}
#offpop{position:fixed;inset:0;z-index:99998;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.85);backdrop-filter:blur(7px)}
#offpop.on{display:flex}
.offmod{background:var(--c2);border:1px solid rgba(255,215,0,.3);border-radius:22px;padding:30px 26px;text-align:center;width:88%;max-width:320px;animation:pi .35s cubic-bezier(.175,.885,.32,1.275)}
@keyframes pi{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
.offic{font-size:52px;margin-bottom:10px;animation:sn 2s ease-in-out infinite}
@keyframes sn{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
.offbtn{width:100%;padding:15px;border:none;border-radius:13px;background:linear-gradient(135deg,var(--or),var(--gd));font-family:'Nunito',sans-serif;font-size:16px;font-weight:900;color:#000;cursor:pointer;margin-top:18px}
#nickpop{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.9);backdrop-filter:blur(8px)}
#nickpop.on{display:flex}
.nmod{background:var(--c2);border:1px solid rgba(255,215,0,.28);border-radius:22px;padding:32px 26px 26px;text-align:center;width:88%;max-width:330px;animation:pi .35s cubic-bezier(.175,.885,.32,1.275)}
.nin{width:100%;padding:13px 15px;border-radius:11px;outline:none;background:rgba(255,255,255,.06);border:2px solid rgba(255,215,0,.18);color:var(--tx);font-family:'Nunito',sans-serif;font-size:16px;font-weight:700;text-align:center;margin-bottom:7px;-webkit-appearance:none}
.nin:focus{border-color:rgba(255,215,0,.5)}.nin::placeholder{color:var(--mt);font-weight:400}
.nhint{font-size:11px;color:var(--rd);min-height:16px;margin-bottom:14px}
.nbtn{width:100%;padding:15px;border:none;border-radius:13px;background:linear-gradient(135deg,var(--or),var(--gd));font-family:'Nunito',sans-serif;font-size:16px;font-weight:900;color:#000;cursor:pointer}
</style>
</head>
<body>
<div id="hdr">
  <button id="profBtn">&#x1F4AA;</button>
  <div class="hm"><div class="hc" id="hCoins">0</div><div class="hl">&#x1F4B0; МОНЕТ</div></div>
  <div class="hr"><div class="hcph" id="hCph">0/&#x447;</div><div class="hcphl">&#x1F4C8; В ЧАС</div></div>
</div>
<div id="xpbar">
  <div class="xrow">
    <span style="color:var(--or);font-weight:800">&#x2B50; <span id="lvlName">Новичок</span> &#x2014; Ур.<span id="lvlNum">1</span></span>
    <span id="xpTxt">0/100</span>
  </div>
  <div class="xt"><div class="xf" id="xpFill" style="width:0%"></div></div>
</div>
<div id="chips">
  <div class="chip"><div class="chipv" id="cCpc">+1</div><div class="chipl">за клик</div></div>
  <div class="chip"><div class="chipv" id="cCps">0</div><div class="chipl">/ сек</div></div>
  <div class="chip"><div class="chipv" id="cAuto">0</div><div class="chipl">авто/сек</div></div>
  <div class="chip"><div class="chipv" id="cCrit">0%</div><div class="chipl">крит</div></div>
</div>
<div id="clicker">
  <div class="nrg">
    <div class="nrgt"><span class="nrgl">&#x26A1; ЭНЕРГИЯ</span><span id="nTxt">100/100</span></div>
    <div class="nrgb"><div class="nrgf" id="nFill" style="width:100%"></div></div>
  </div>
  <div class="coinwrap">
    <div class="glow" id="cglow"></div>
    <button id="coin">&#x1F4AA;</button>
  </div>
</div>
<div id="tabs">
  <button class="tab on" data-t="click">&#x1F5B1; КЛИК</button>
  <button class="tab" data-t="passive">&#x23F1; ПАССИВ</button>
  <button class="tab" data-t="boost">&#x1F680; БУСТ</button>
  <button class="tab" data-t="top">&#x1F451; ТОП</button>
  <button class="tab" data-t="extra">&#x2795; ДОП</button>
  <button class="tab" data-t="coin">&#x1FA99; COIN</button>
</div>
<div class="panel on" id="panel-click">
  <div class="sec">Сила удара</div><div id="lClick"></div>
  <div class="sec">Энергия</div><div id="lEnergy"></div>
  <div class="sec">Критический удар</div><div id="lCrit"></div>
</div>
<div class="panel" id="panel-passive">
  <div class="sec">Пассивный доход</div><div id="lPassive"></div>
</div>
<div class="panel" id="panel-boost">
  <div class="sec">Авто-кликер</div><div id="lAuto"></div>
  <div class="sec">Специальные</div><div id="lSpecial"></div>
</div>
<div class="panel" id="panel-top">
  <div class="lbme" style="margin-top:6px">
    <span class="lbmel">&#x1F4C8; МОЙ ДОХОД / ЧАС</span>
    <span class="lbmev" id="lbMe">0</span>
  </div>
  <button class="lbref" id="lbRefBtn">&#x1F504; Обновить</button>
  <div id="lbPod"></div><div id="lbList"></div>
</div>
<div class="panel" id="panel-extra">
  <div class="sec">Задания</div>
  <div class="task" id="taskTg">
    <div class="taskico">&#x1F4E2;</div>
    <div class="taskbod">
      <div class="tasknam">Подписаться на канал</div>
      <div class="taskdsc">Подпишись на официальный Telegram-канал GymClicker</div>
      <div class="taskrew">&#x1F4B0; Награда: 10,000 монет</div>
    </div>
    <button class="taskbtn" id="taskTgBtn">ПЕРЕЙТИ</button>
  </div>
</div>
<div class="panel" id="panel-coin">
  <div class="coin-soon-wrap">
    <div class="coin-spin-wrap">
      <div class="coin-spin" id="coinSpin">&#x1F4AA;</div>
    </div>
    <div class="coin-soon-title">COIN</div>
    <div class="coin-soon-sub">Coming Soon</div>
    <div class="coin-soon-desc">Собственная монета GymClicker.<br>Следи за обновлениями в нашем канале!</div>
    <a class="coin-soon-btn" href="https://t.me/gymclicker" target="_blank">&#x1F4E2; Подписаться на канал</a>
  </div>
</div>

<div id="notif"></div>
<div id="apop"><div id="apopi">&#x1F3C6;</div><div><div class="apl">ДОСТИЖЕНИЕ!</div><div class="apn" id="apN">-</div><div class="apr" id="apR"></div></div></div>
<div id="offpop">
  <div class="offmod">
    <div class="offic">&#x1F4A4;</div>
    <div style="font-size:15px;font-weight:900;margin-bottom:4px">Пока тебя не было...</div>
    <div style="font-size:12px;color:var(--mt);margin-bottom:14px" id="offT"></div>
    <div style="font-size:11px;color:var(--mt);letter-spacing:1px;margin-bottom:4px">КАЧАЛКА ЗАРАБОТАЛА:</div>
    <div style="font-size:40px;font-weight:900;color:var(--gd);line-height:1" id="offE">+0</div>
    <button class="offbtn" id="offBtn">ЗАБРАТЬ &#x1F4B0;</button>
  </div>
</div>
<div id="nickpop">
  <div class="nmod">
    <div style="font-size:56px;margin-bottom:10px">&#x1F4AA;</div>
    <div style="font-size:21px;font-weight:900;color:var(--gd);margin-bottom:5px">Добро пожаловать!</div>
    <div style="font-size:13px;color:var(--mt);margin-bottom:18px">Введи никнейм для таблицы лидеров</div>
    <input class="nin" id="nickIn" type="text" maxlength="20" placeholder="Твой никнейм..." autocomplete="off">
    <div class="nhint" id="nickHint"></div>
    <button class="nbtn" id="nickSaveBtn">В КАЧАЛКУ! &#x1F4AA;</button>
  </div>
</div>
<div id="ov"></div>
<div id="dr">
  <div class="drh">
    <div class="drhead">
      <div class="drava" id="drAva">&#x1F4AA;</div>
      <div class="drinfo"><div class="drname" id="drName">Игрок</div><div class="drsub">Ур.<span id="drLvl">1</span> &middot; <span id="drLvlN">Новичок</span></div></div>
      <button class="drcl" id="drCloseBtn">&#x2715;</button>
    </div>
    <div class="nrow">
      <input class="nei" id="nickEdit" type="text" maxlength="20" placeholder="Изменить ник...">
      <button class="neb" id="nickEditBtn">&#x2713;</button>
    </div>
  </div>
  <div class="drtabs">
    <button class="drtab on" data-p="stats">&#x1F4CA; Стат</button>
    <button class="drtab" data-p="achs">&#x1F3C6; Ачив</button>
    <button class="drtab" data-p="skins">&#x1F3A8; Скины</button>
  </div>
  <div class="drbody">
    <div class="drp on" id="drp-stats">
      <div class="sgrid" style="margin-top:2px">
        <div class="sc"><div class="scv" id="stTC">0</div><div class="scl">Всего монет</div></div>
        <div class="sc"><div class="scv" id="stCL">0</div><div class="scl">Кликов</div></div>
        <div class="sc"><div class="scv" id="stPT">0м</div><div class="scl">Время игры</div></div>
        <div class="sc"><div class="scv" id="stMS">0</div><div class="scl">Макс /сек</div></div>
        <div class="sc"><div class="scv" id="stMC">+1</div><div class="scl">Макс за клик</div></div>
        <div class="sc"><div class="scv" id="stCR">0</div><div class="scl">Критов</div></div>
        <div class="sc"><div class="scv" id="stSK">0</div><div class="scl">Скинов</div></div>
        <div class="sc"><div class="scv" id="stAC">0</div><div class="scl">Достижений</div></div>
      </div>
    </div>
    <div class="drp" id="drp-achs"><div id="achList"></div></div>
    <div class="drp" id="drp-skins"><div class="skgrid" id="skinList"></div></div>
  </div>
</div>
<script>
'use strict';
var LVS=[{n:'Новичок',x:0},{n:'Любитель',x:100},{n:'Спортсмен',x:300},{n:'Атлет',x:700},{n:'Культурист',x:1500},{n:'Чемпион',x:3500},{n:'Мастер',x:8000},{n:'Легенда',x:20000},{n:'Бог Железа',x:50000},{n:'АБСОЛЮТ',x:120000},{n:'Железный Кулак',x:200000},{n:'Стальная Воля',x:350000},{n:'Гранитный',x:550000},{n:'Титановый',x:850000},{n:'Алмазный',x:1300000},{n:'Платиновый',x:2000000},{n:'Космический',x:3000000},{n:'Галактический',x:4500000},{n:'Вселенский',x:7000000},{n:'Квантовый',x:10000000},{n:'Ультра',x:15000000},{n:'Мега',x:22000000},{n:'Гига',x:32000000},{n:'Тера',x:47000000},{n:'Пета',x:70000000},{n:'Экза',x:100000000},{n:'ЛЕГЕНДА ВСЕХ ВРЕМЁН',x:150000000},{n:'БОГ КАЧАЛКИ',x:220000000},{n:'СОЗДАТЕЛЬ',x:330000000},{n:'БЕСКОНЕЧНЫЙ',x:500000000}];
var UPG={
click:[
{id:'c1',n:'Протеиновый шейк',i:'🥤',d:'Больше сил в руках',bp:25,pg:2.1,mx:30,ef:'cpc',v:1},
{id:'c2',n:'Спортперчатки',i:'🥊',d:'Точный удар',bp:120,pg:2.2,mx:25,ef:'cpc',v:3},
{id:'c3',n:'Предтрен',i:'⚡',d:'Взрывная сила',bp:600,pg:2.3,mx:20,ef:'cpc',v:10},
{id:'c4',n:'Анаболики',i:'💉',d:'Сила зашкаливает',bp:4000,pg:2.4,mx:15,ef:'cpc',v:40},
{id:'c5',n:'Режим зверя',i:'🦁',d:'Ты непобедим',bp:30000,pg:2.5,mx:12,ef:'cpc',v:200},
{id:'c6',n:'Бог качалки',i:'🏛️',d:'Запредельная мощь',bp:300000,pg:2.6,mx:10,ef:'cpc',v:1200},
{id:'c7',n:'Квантовый удар',i:'⚛️',d:'Разрушает пространство',bp:3000000,pg:2.7,mx:8,ef:'cpc',v:8000},
{id:'c8',n:'Перчатки Титана',i:'🧤',d:'Сила запредельная',bp:25000000,pg:2.8,mx:6,ef:'cpc',v:60000},
{id:'c9',n:'Молот Тора',i:'🔨',d:'Мощь бога грома',bp:200000000,pg:2.9,mx:5,ef:'cpc',v:500000},
{id:'c10',n:'Перчатки Бесконечности',i:'♾️',d:'Неограниченная сила',bp:2000000000,pg:3.0,mx:4,ef:'cpc',v:5000000}
],
energy:[
{id:'e1',n:'Расширенный запас',i:'🔋',d:'Больше максимальной энергии',bp:150,pg:2.2,mx:20,ef:'mxE',v:50},
{id:'e2',n:'Быстрое восст.',i:'🔄',d:'+0.3 восст./сек за уровень',bp:400,pg:2.3,mx:30,ef:'rgE',v:0.3}
],
crit:[
{id:'cr1',n:'Меткость',i:'🎯',d:'+5% шанс критического удара',bp:800,pg:2.3,mx:5,ef:'critC',v:5},
{id:'cr2',n:'Снайпер',i:'🔭',d:'+10% шанс критического удара',bp:25000,pg:2.5,mx:5,ef:'critC',v:10},
{id:'cr3',n:'Мощь удара',i:'💢',d:'+0.5x множитель крита',bp:5000,pg:2.4,mx:10,ef:'critM',v:0.5}
],
passive:[
{id:'p1',n:'Новичок в зале',i:'🚶',d:'Парень качается за тебя',bp:50,pg:1.8,mx:50,ef:'cps',v:0.5},
{id:'p2',n:'Личный тренер',i:'👨‍🏫',d:'Профи с программой',bp:300,pg:1.9,mx:40,ef:'cps',v:2},
{id:'p3',n:'Мини-качалка',i:'🏋️',d:'Своя маленькая качалка',bp:1500,pg:2.0,mx:35,ef:'cps',v:8},
{id:'p4',n:'Спортзал',i:'🏟️',d:'Целый зал работает',bp:8000,pg:2.1,mx:30,ef:'cps',v:30},
{id:'p5',n:'Сеть клубов',i:'🌐',d:'Клубы по всему городу',bp:50000,pg:2.2,mx:20,ef:'cps',v:150},
{id:'p6',n:'Фитнес-империя',i:'👑',d:'Ты контролируешь рынок',bp:500000,pg:2.3,mx:15,ef:'cps',v:800},
{id:'p7',n:'Мировая сеть',i:'🌍',d:'Планета качается на тебя',bp:5000000,pg:2.4,mx:10,ef:'cps',v:5000},
{id:'p8',n:'Межгалактическая сеть',i:'🌌',d:'Галактики качаются',bp:50000000,pg:2.5,mx:8,ef:'cps',v:40000},
{id:'p9',n:'Вселенская сеть',i:'✨',d:'Вселенная работает',bp:500000000,pg:2.6,mx:6,ef:'cps',v:400000},
{id:'p10',n:'Машина времени',i:'⏰',d:'Монеты из прошлого',bp:5000000000,pg:2.7,mx:5,ef:'cps',v:4000000}
],
auto:[
{id:'au1',n:'Авто-рука',i:'🤖',d:'Автоматически кликает за тебя',bp:10000,pg:999,mx:1,ef:'aCps',v:1},
{id:'au2',n:'Дрон-тренер',i:'🚁',d:'Летающий кликер-дрон',bp:75000,pg:999,mx:1,ef:'aCps',v:5}
],
special:[
{id:'sp1',n:'Комбо-удар',i:'🎰',d:'Каждый 10-й клик даёт x10',bp:50000,pg:999,mx:1,ef:'combo',v:1},
{id:'sp2',n:'Фортуна',i:'🍀',d:'15% шанс удвоить монеты',bp:35000,pg:999,mx:1,ef:'luck',v:15}
]};
var ALL_UPG=[];
Object.keys(UPG).forEach(function(k){ALL_UPG=ALL_UPG.concat(UPG[k]);});
var ACHS=[
{id:'a1',i:'👆',n:'Первый клик',d:'Нажми на монету',c:function(s){return s.clicks>=1;},r:{t:'c',v:10}},
{id:'a2',i:'💪',n:'100 кликов',d:'Сделай 100 кликов',c:function(s){return s.clicks>=100;},r:{t:'c',v:200}},
{id:'a3',i:'🔥',n:'1000 кликов',d:'Сделай 1000 кликов',c:function(s){return s.clicks>=1000;},r:{t:'c',v:2000}},
{id:'a4',i:'💥',n:'10K кликов',d:'Машина для кликов!',c:function(s){return s.clicks>=10000;},r:{t:'c',v:20000}},
{id:'a5',i:'🦾',n:'100K кликов',d:'Ты кликер-легенда',c:function(s){return s.clicks>=100000;},r:{t:'s',v:'toxic'}},
{id:'a6',i:'💰',n:'100 монет',d:'Накопи 100 монет',c:function(s){return s.allC>=100;},r:{t:'c',v:50}},
{id:'a7',i:'💎',n:'10K монет',d:'Накопи 10k монет',c:function(s){return s.allC>=10000;},r:{t:'c',v:5000}},
{id:'a8',i:'🏦',n:'1M монет',d:'Миллионер!',c:function(s){return s.allC>=1000000;},r:{t:'s',v:'diamond'}},
{id:'a9',i:'⬆️',n:'Первый апгрейд',d:'Купи улучшение',c:function(s){return s.allU>=1;},r:{t:'c',v:100}},
{id:'a10',i:'🛒',n:'25 апгрейдов',d:'Инвестор!',c:function(s){return s.allU>=25;},r:{t:'c',v:25000}},
{id:'a11',i:'😴',n:'Пассивный доход',d:'1 монета в секунду',c:function(s){return s.cps>=1;},r:{t:'c',v:500}},
{id:'a12',i:'⭐',n:'Стахановец',d:'100 монет в секунду',c:function(s){return s.cps>=100;},r:{t:'s',v:'galaxy'}},
{id:'a13',i:'🏅',n:'Уровень 5',d:'Достигни 5-го уровня',c:function(s){return s.lvl>=5;},r:{t:'c',v:10000}},
{id:'a14',i:'🥇',n:'Уровень 10',d:'Достигни 10-го уровня',c:function(s){return s.lvl>=10;},r:{t:'s',v:'fire'}},
{id:'a15',i:'👑',n:'Уровень 20',d:'Достигни 20-го уровня',c:function(s){return s.lvl>=20;},r:{t:'s',v:'rainbow'}},
{id:'a16',i:'🎯',n:'Критикан',d:'100 критических ударов',c:function(s){return s.crits>=100;},r:{t:'c',v:15000}},
{id:'a17',i:'🤖',n:'Роботизация',d:'Купи Авто-руку',c:function(s){return (s.ul['au1']||0)>=1;},r:{t:'c',v:20000}},
{id:'a18',i:'🎰',n:'Комбо-мастер',d:'Активируй комбо 10 раз',c:function(s){return s.combos>=10;},r:{t:'c',v:30000}},
{id:'a19',i:'🌌',n:'Галактический',d:'Купи Галактика Силы',c:function(s){return s.sk.includes('galaxy');},r:{t:'c',v:50000}},
{id:'a20',i:'♾️',n:'Бесконечный',d:'Достигни уровня БЕСКОНЕЧНЫЙ',c:function(s){return s.lvl>=30;},r:{t:'s',v:'cyber'}}
];
var SKINS=[
{id:'default',n:'Золотая Классика',e:'💪',p:0,ach:null,bg:'radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),linear-gradient(135deg,#f5c518,#e8a800,#ffd700,#cc8800)',sh:'0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4)',gl:'rgba(255,200,0,.18)'},
{id:'fire',n:'Огненный Атлет',e:'🔥',p:0,ach:'a14',bg:'radial-gradient(circle at 35% 25%,rgba(255,200,100,.5) 0%,transparent 50%),linear-gradient(135deg,#ff4500,#ff6b00,#ff0000,#cc2200)',sh:'0 0 0 4px rgba(255,80,0,.4),0 0 35px rgba(255,60,0,.6)',gl:'rgba(255,80,0,.2)'},
{id:'ice',n:'Ледяной Колосс',e:'❄️',p:5000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(200,240,255,.6) 0%,transparent 50%),linear-gradient(135deg,#00c8ff,#0080cc,#004488)',sh:'0 0 0 4px rgba(0,180,255,.4),0 0 35px rgba(0,180,255,.5)',gl:'rgba(0,180,255,.18)'},
{id:'toxic',n:'Токсичный Доза',e:'☢️',p:0,ach:'a5',bg:'radial-gradient(circle at 40% 30%,rgba(180,255,100,.5) 0%,transparent 50%),linear-gradient(135deg,#39ff14,#22cc00,#009900)',sh:'0 0 0 4px rgba(57,255,20,.4),0 0 40px rgba(57,255,20,.6)',gl:'rgba(57,255,20,.2)'},
{id:'galaxy',n:'Галактика Силы',e:'🌌',p:25000,ach:null,bg:'radial-gradient(circle at 30% 25%,rgba(200,150,255,.5) 0%,transparent 50%),linear-gradient(135deg,#6600cc,#9933ff,#3300aa)',sh:'0 0 0 4px rgba(180,0,255,.4),0 0 40px rgba(150,0,255,.6)',gl:'rgba(150,0,255,.2)'},
{id:'diamond',n:'Бриллиантовый Бог',e:'💎',p:0,ach:'a8',bg:'radial-gradient(circle at 30% 20%,rgba(255,255,255,.9) 0%,transparent 40%),linear-gradient(135deg,#a8d8ff,#e0f4ff,#b8e8ff)',sh:'0 0 0 4px rgba(150,210,255,.5),0 0 50px rgba(100,200,255,.7)',gl:'rgba(150,220,255,.25)'},
{id:'lava',n:'Магма Абсолют',e:'🌋',p:150000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,220,100,.6) 0%,transparent 45%),linear-gradient(135deg,#ff8c00,#cc2200,#ff4400)',sh:'0 0 0 4px rgba(255,100,0,.5),0 0 50px rgba(255,80,0,.7)',gl:'rgba(255,80,0,.25)'},
{id:'rainbow',n:'Радужный Королевич',e:'🦄',p:0,ach:'a15',bg:'linear-gradient(135deg,#ff0080,#ff8c00,#ffed00,#00c800,#0080ff,#8000ff)',sh:'0 0 0 4px rgba(255,0,128,.4),0 0 50px rgba(128,0,255,.5)',gl:'rgba(200,0,200,.2)'},
{id:'shadow',n:'Тёмный Воин',e:'🖤',p:400000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(100,0,200,.5) 0%,transparent 50%),linear-gradient(135deg,#1a0030,#2d0050,#0d001a)',sh:'0 0 0 4px rgba(100,0,200,.4),0 0 40px rgba(80,0,150,.6)',gl:'rgba(100,0,200,.2)'},
{id:'cyber',n:'Кибер Мутант',e:'🤖',p:0,ach:'a20',bg:'radial-gradient(circle at 35% 25%,rgba(0,255,200,.4) 0%,transparent 50%),linear-gradient(135deg,#001a1a,#003333,#00ff88)',sh:'0 0 0 4px rgba(0,255,180,.4),0 0 50px rgba(0,255,150,.5)',gl:'rgba(0,255,150,.2)'}
];
var SAVE_KEY='gymv11';
var G={};
var DEF={coins:0,allC:0,clicks:0,allU:0,crits:0,combos:0,lvl:1,xp:0,nrg:100,mxE:100,rgE:2,cpc:1,cps:0,aCps:0,critC:0,critM:2,luck:0,combo:0,pt:0,mxCps:0,mxCpc:1,ul:{},achs:[],claimed:[],sk:['default'],skin:'default',lastSeen:null,comboN:0};
function loadGame(){
  try{var s=localStorage.getItem(SAVE_KEY);G=Object.assign({},DEF,s?JSON.parse(s):{});}catch(e){G=Object.assign({},DEF);}
  try{var t=localStorage.getItem(SAVE_KEY+'_tmr');if(t){var loaded=JSON.parse(t);Object.keys(loaded).forEach(function(k){if(!loaded[k].applied)TIMERS[k]=loaded[k];});}}catch(e){}
}
function saveGame(){
  G.lastSeen=Date.now();
  try{localStorage.setItem(SAVE_KEY,JSON.stringify(G));}catch(e){}
  try{localStorage.setItem(SAVE_KEY+'_tmr',JSON.stringify(TIMERS));}catch(e){}
}
function fmt(n){n=Math.floor(n);if(n>=1e12)return(n/1e12).toFixed(1)+'T';if(n>=1e9)return(n/1e9).toFixed(1)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1000)return(n/1000).toFixed(1)+'K';return String(n);}
function uLvl(id){return G.ul[id]||0;}
function uPrice(u){return Math.floor(u.bp*Math.pow(u.pg,uLvl(u.id)));}
function recalc(){
  var cpc=1,cps=0,mxE=100,rgE=2,critC=0,critM=2,aCps=0,luck=0,combo=0;
  for(var i=0;i<ALL_UPG.length;i++){var u=ALL_UPG[i];var l=uLvl(u.id);if(!l)continue;
    if(u.ef==='cpc')cpc+=u.v*l;else if(u.ef==='cps')cps+=u.v*l;else if(u.ef==='mxE')mxE+=u.v*l;
    else if(u.ef==='rgE')rgE+=u.v*l;else if(u.ef==='critC')critC+=u.v*l;else if(u.ef==='critM')critM+=u.v*l;
    else if(u.ef==='aCps')aCps+=u.v*l;else if(u.ef==='luck')luck+=u.v*l;else if(u.ef==='combo')combo+=u.v*l;}
  G.cpc=Math.max(1,Math.floor(cpc));G.cps=parseFloat(cps.toFixed(2));
  G.mxE=mxE;G.rgE=parseFloat(rgE.toFixed(2));G.critC=Math.min(critC,80);G.critM=critM;
  G.aCps=aCps;G.luck=luck;G.combo=combo;
  if(G.nrg>G.mxE)G.nrg=G.mxE;if(G.cps>G.mxCps)G.mxCps=G.cps;if(G.cpc>G.mxCpc)G.mxCpc=G.cpc;}
function checkLevel(){
  while(G.lvl<LVS.length){var nx=LVS[G.lvl];if(!nx||G.xp<nx.x)break;G.lvl++;showNotif('Уровень '+G.lvl+' — '+LVS[G.lvl-1].n);}}
function checkAchs(){
  var snap={clicks:G.clicks,allC:G.allC,allU:G.allU,cps:G.cps,lvl:G.lvl,crits:G.crits,combos:G.combos,ul:G.ul,sk:G.sk};
  for(var i=0;i<ACHS.length;i++){var a=ACHS[i];if(G.achs.indexOf(a.id)>=0)continue;if(!a.c(snap))continue;
    G.achs.push(a.id);if(a.r.t==='s'&&G.sk.indexOf(a.r.v)<0){G.sk.push(a.r.v);G.claimed.push(a.id);}showAchPopup(a);}}
function claimReward(id){
  if(G.claimed.indexOf(id)>=0)return;var a=null;for(var i=0;i<ACHS.length;i++){if(ACHS[i].id===id){a=ACHS[i];break;}}
  if(!a||G.achs.indexOf(id)<0)return;G.claimed.push(id);
  if(a.r.t==='c'){G.coins+=a.r.v;G.allC+=a.r.v;updateHUD();showNotif('+'+fmt(a.r.v)+' монет!');}
  else if(a.r.t==='s'&&G.sk.indexOf(a.r.v)<0){G.sk.push(a.r.v);showNotif('Скин разблокирован!');renderSkins();}
  saveGame();renderAchs();}
var tbActive=false;
function doClick(x,y){
  if(G.nrg<1){showNotif('Нет энергии!');return;}
  G.nrg=Math.max(0,G.nrg-1);
  var earn=G.cpc;var isCrit=false;
  if(G.combo>0){G.comboN=(G.comboN||0)+1;if(G.comboN>=10){earn*=10;G.comboN=0;G.combos=(G.combos||0)+1;spawnFloat('КОМБО x10!',x,y-30,null);}}
  if(G.critC>0&&Math.random()*100<G.critC){earn=Math.floor(earn*G.critM);isCrit=true;G.crits++;}
  if(G.luck>0&&Math.random()*100<G.luck){earn*=2;spawnFloat('УДАЧА x2!',x,y-30,null);}
  if(tbActive)earn=Math.floor(earn*2);
  earn=Math.floor(earn);G.coins+=earn;G.allC+=earn;G.clicks++;G.xp+=1;
  checkLevel();checkAchs();
  spawnFloat((isCrit?'x':'+')+fmt(earn),x,y,isCrit?'#ff5500':null);spawnRipple(x,y);updateHUD();}
// Timer durations: level 1-5 = 30s-5min, 6-15 = 5-15min, 16+ = 15-30min
function getUpgradeTime(u, newLvl) {
  if(newLvl<=5)return 30+Math.floor(Math.random()*270); // 30s-5min
  if(newLvl<=15)return 300+Math.floor(Math.random()*600); // 5-15min
  return 900+Math.floor(Math.random()*900); // 15-30min
}
function fmtTime(sec){
  if(sec<60)return sec+'с';
  var m=Math.floor(sec/60),s=sec%60;
  return m+'м'+(s>0?' '+s+'с':'');
}
var TIMERS={}; // {id: {end, total, applied}}
function buyUpgrade(id){
  var u=null;for(var i=0;i<ALL_UPG.length;i++){if(ALL_UPG[i].id===id){u=ALL_UPG[i];break;}}
  if(!u)return;
  // If timer running — collect if ready
  if(TIMERS[id]){
    if(Date.now()>=TIMERS[id].end&&!TIMERS[id].applied){
      TIMERS[id].applied=true;
      G.ul[id]=(G.ul[id]||0)+1;G.allU++;G.xp+=10;
      recalc();checkLevel();checkAchs();updateHUD();
      delete TIMERS[id];
      renderAll();
      showNotif(u.n+' — готово! Ур.'+uLvl(id));
      return;
    } else if(!TIMERS[id].applied){
      var rem=Math.ceil((TIMERS[id].end-Date.now())/1000);
      showNotif('Ещё идёт прокачка: '+fmtTime(rem));
      return;
    }
  }
  var l=uLvl(id);if(l>=u.mx)return;
  var p=uPrice(u);
  if(G.coins<p){showNotif('Недостаточно монет!');return;}
  G.coins-=p;G.allU++;
  var dur=getUpgradeTime(u,l+1);
  TIMERS[id]={end:Date.now()+dur*1000,total:dur,applied:false};
  updateHUD();renderAll();
  showNotif(u.n+' — прокачка '+fmtTime(dur)+'...');
}
function tapSkin(id){
  var s=null;for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id){s=SKINS[i];break;}}if(!s)return;
  if(s.ach&&G.sk.indexOf(id)<0){showNotif('Нужно достижение!');return;}
  if(G.sk.indexOf(id)>=0){G.skin=id;applySkin(id);saveGame();renderSkins();showNotif('Скин надет!');}
  else{if(G.coins<s.p){showNotif('Недостаточно монет!');return;}
    G.coins-=s.p;G.sk.push(id);G.skin=id;applySkin(id);saveGame();updateHUD();renderSkins();showNotif('Скин куплен!');}}
function applySkin(id){
  var s=SKINS[0];for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id){s=SKINS[i];break;}}
  var btn=document.getElementById('coin');var gl=document.getElementById('cglow');
  btn.style.background=s.bg;btn.style.boxShadow=s.sh;btn.textContent=s.e;
  if(gl)gl.style.background='radial-gradient(circle,'+s.gl+' 0%,transparent 70%)';
  document.getElementById('profBtn').textContent=s.e;document.getElementById('drAva').textContent=s.e;}
function updateHUD(){
  document.getElementById('hCoins').textContent=fmt(G.coins);
  document.getElementById('hCph').textContent=fmt(G.cps*3600)+'/ч';
  document.getElementById('cCpc').textContent='+'+fmt(G.cpc);
  document.getElementById('cCps').textContent=fmt(G.cps);
  document.getElementById('cAuto').textContent=fmt(G.aCps);
  document.getElementById('cCrit').textContent=G.critC+'%';
  document.getElementById('nTxt').textContent=Math.floor(G.nrg)+'/'+G.mxE;
  document.getElementById('nFill').style.width=(G.nrg/G.mxE*100)+'%';
  var ci=G.lvl-1;var cx=LVS[ci]?LVS[ci].x:0;var nx=LVS[G.lvl]?LVS[G.lvl].x:LVS[LVS.length-1].x+999999;
  var pct=nx>cx?Math.min(100,(G.xp-cx)/(nx-cx)*100):100;
  document.getElementById('xpFill').style.width=pct+'%';
  document.getElementById('xpTxt').textContent=fmt(G.xp-cx)+'/'+fmt(nx-cx);
  document.getElementById('lvlNum').textContent=G.lvl;
  document.getElementById('lvlName').textContent=LVS[ci]?LVS[ci].n:'MAX';
  document.getElementById('lbMe').textContent=fmt(G.cps*3600)+'/ч';
  document.getElementById('coin').classList.toggle('dead',G.nrg<1);
  var nick=getNick()||'Игрок';
  document.getElementById('drName').textContent=nick;
  document.getElementById('drLvl').textContent=G.lvl;
  document.getElementById('drLvlN').textContent=LVS[ci]?LVS[ci].n:'MAX';
  document.getElementById('stTC').textContent=fmt(G.allC);
  document.getElementById('stCL').textContent=fmt(G.clicks);
  var m=Math.floor(G.pt/60),h=Math.floor(m/60);
  document.getElementById('stPT').textContent=h>0?h+'ч':m+'м';
  document.getElementById('stMS').textContent=fmt(G.mxCps);
  document.getElementById('stMC').textContent='+'+fmt(G.mxCpc);
  document.getElementById('stCR').textContent=fmt(G.crits||0);
  document.getElementById('stSK').textContent=G.sk.length;
  document.getElementById('stAC').textContent=G.achs.length+'/'+ACHS.length;}
function effText(u){
  if(u.ef==='cpc')return'+'+u.v+' за клик';
  if(u.ef==='cps')return'+'+u.v+'/сек · +'+fmt(u.v*3600)+'/ч';
  if(u.ef==='mxE')return'+'+u.v+' энергии';
  if(u.ef==='rgE')return'+'+u.v.toFixed(1)+' восст./сек';
  if(u.ef==='critC')return'+'+u.v+'% шанс крита';
  if(u.ef==='critM')return'+'+u.v+'x крит урон';
  if(u.ef==='aCps')return'+'+u.v+' авто/сек';
  if(u.ef==='luck')return'+'+u.v+'% удвоить монеты';
  if(u.ef==='combo')return'каждый 10-й клик x10';return '';}
function renderList(cid,list){
  var el=document.getElementById(cid);if(!el)return;var rows=[];
  for(var i=0;i<list.length;i++){
    var u=list[i];var l=uLvl(u.id);var mx=l>=u.mx;var p=uPrice(u);var ok=!mx&&G.coins>=p;
    var timer=TIMERS[u.id];
    var timerHtml='';var cls='upg';var priceHtml='';
    if(timer&&!timer.applied){
      var now=Date.now();var rem=Math.max(0,Math.ceil((timer.end-now)/1000));
      var prog=Math.min(100,Math.round((1-(timer.end-now)/(timer.total*1000))*100));
      if(rem<=0){
        timerHtml='<div class="upg-timer ready">&#x2705; Готово! Нажми чтобы получить</div>';
        cls='upg ok';priceHtml='<div class="uprv" style="color:var(--gn)">ГОТОВО</div>';
      } else {
        timerHtml='<div class="upg-timer">&#x23F3; '+fmtTime(rem)+'</div><div class="upg-prog" style="width:'+prog+'%"></div>';
        cls='upg upgrading';priceHtml='<div class="uprv" style="color:var(--or)">'+fmtTime(rem)+'</div>';
      }
    } else {
      cls='upg'+(ok?' ok':'')+(mx?' mx':'');
      priceHtml=mx?'<div class="uprv" style="color:var(--gn)">МАКС</div>':'<div class="uprv'+(ok?'':' no')+'">'+fmt(p)+'</div><div class="uprl">монет</div>';
    }
    rows.push('<div class="'+cls+'" data-uid="'+u.id+'" style="position:relative"><div class="uico">'+u.i+'</div><div class="ubod"><div class="unam">'+u.n+'</div><div class="udsc">'+u.d+'</div><div class="ueff">'+effText(u)+'</div><div class="ulvl">Ур. '+l+' / '+u.mx+'</div>'+timerHtml+'</div><div class="uprc">'+priceHtml+'</div></div>');}
  el.innerHTML=rows.join('');}
function renderAll(){
  renderList('lClick',UPG.click);renderList('lEnergy',UPG.energy);renderList('lCrit',UPG.crit);
  renderList('lPassive',UPG.passive);renderList('lAuto',UPG.auto);renderList('lSpecial',UPG.special);}
function renderAchs(){
  var el=document.getElementById('achList');if(!el)return;var rows=[];
  for(var i=0;i<ACHS.length;i++){var a=ACHS[i];var done=G.achs.indexOf(a.id)>=0;var cl=G.claimed.indexOf(a.id)>=0;
    var rv=a.r.t==='c'?fmt(a.r.v)+' монет':'';
    if(a.r.t==='s'){for(var j=0;j<SKINS.length;j++){if(SKINS[j].id===a.r.v){rv='Скин: '+SKINS[j].n;break;}}}
    var btn='';if(done&&!cl)btn='<button class="achbtn" data-aid="'+a.id+'">ЗАБРАТЬ</button>';
    else if(done&&cl)btn='<div class="achgot">&#x2713;</div>';
    rows.push('<div class="ach'+(done?' on':'')+'"><div class="achi">'+a.i+'</div><div class="achb"><div class="achn">'+a.n+'</div><div class="achd">'+(done?a.d:'???')+'</div><div class="achr">'+rv+'</div></div>'+(done?'<div>'+btn+'</div>':'')+'</div>');}
  el.innerHTML=rows.join('');}
function renderSkins(){
  var el=document.getElementById('skinList');if(!el)return;var rows=[];
  for(var i=0;i<SKINS.length;i++){var s=SKINS[i];var own=G.sk.indexOf(s.id)>=0;var eq=G.skin===s.id;var alck=s.ach&&!own;var ok=!own&&!alck&&G.coins>=s.p;
    var badge='';if(eq)badge='<span class="skbdg beq">&#x2713; НАДЕТ</span>';else if(own)badge='<span class="skbdg bown">КУПЛЕН</span>';else if(alck)badge='<span class="skbdg bac">АЧИВ</span>';else if(s.p>0)badge='<span class="skbdg blk">&#x1F512;</span>';
    var price='';if(s.p===0&&!alck)price='<div class="skp" style="color:var(--gn)">БЕСПЛАТНО</div>';
    else if(alck){var an='Достижение';for(var j=0;j<ACHS.length;j++){if(ACHS[j].id===s.ach){an=ACHS[j].n;break;}}price='<div class="skp ac">'+an+'</div>';}
    else if(own)price=eq?'<div class="skp" style="color:var(--gn)">НАДЕТ</div>':'<div class="skp" style="color:var(--or)">НАДЕТЬ</div>';
    else price='<div class="skp'+(ok?'':' no')+'">'+fmt(s.p)+' монет</div>';
    var cls='sk'+(eq?' eq':own?' own':alck?' ak':ok?' ok':' lk');
    rows.push('<div class="'+cls+'" data-sid="'+s.id+'">'+badge+'<div class="skprev" style="background:'+s.bg+';box-shadow:'+s.sh+'">'+s.e+'</div><div class="skn">'+s.n+'</div>'+price+'</div>');}
  el.innerHTML=rows.join('');}
function spawnFloat(txt,x,y,color){var el=document.createElement('div');el.className='ft';el.textContent=txt;if(color)el.style.color=color;el.style.left=(x+(Math.random()*40-20))+'px';el.style.top=(y-10)+'px';document.body.appendChild(el);setTimeout(function(){el.remove();},900);}
function spawnRipple(x,y){var el=document.createElement('div');el.className='rp';el.style.cssText='left:'+(x-25)+'px;top:'+(y-25)+'px;width:50px;height:50px';document.body.appendChild(el);setTimeout(function(){el.remove();},450);}
var _ntfT=null;
function showNotif(msg){var el=document.getElementById('notif');el.textContent=msg;el.classList.add('on');clearTimeout(_ntfT);_ntfT=setTimeout(function(){el.classList.remove('on');},2200);}
var _achQ=[],_achBusy=false;
function showAchPopup(a){_achQ.push(a);if(!_achBusy)nextAch();}
function nextAch(){if(!_achQ.length){_achBusy=false;return;}_achBusy=true;var a=_achQ.shift();
  document.getElementById('apopi').textContent=a.i;document.getElementById('apN').textContent=a.n;
  var rw=a.r.t==='c'?'Награда: '+fmt(a.r.v)+' монет':'';
  if(a.r.t==='s'){for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===a.r.v){rw='Скин: '+SKINS[i].n;break;}}}
  document.getElementById('apR').textContent=rw;document.getElementById('apop').classList.add('on');
  setTimeout(function(){document.getElementById('apop').classList.remove('on');setTimeout(nextAch,400);},3000);}
function openDrawer(){document.getElementById('ov').classList.add('on');document.getElementById('dr').classList.add('on');updateHUD();renderAchs();renderSkins();var n=getNick();if(n)document.getElementById('nickEdit').value=n;}
function closeDrawer(){document.getElementById('ov').classList.remove('on');document.getElementById('dr').classList.remove('on');}
function changeNick(){var v=document.getElementById('nickEdit').value.trim();if(v.length<2||v.length>20){showNotif('Ник: 2-20 символов');return;}localStorage.setItem('gymNick',v);updateHUD();saveGame();showNotif('Ник изменён: '+v);pushScore();}
var _offE=0;
function checkOffline(){if(!G.lastSeen||G.cps<=0)return;var sec=Math.min((Date.now()-G.lastSeen)/1000,7200);if(sec<30)return;_offE=Math.floor(G.cps*sec);if(!_offE)return;var h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60);document.getElementById('offT').textContent='Отсутствовал: '+(h?h+'ч ':'')+m+'мин';document.getElementById('offE').textContent='+'+fmt(_offE);document.getElementById('offpop').classList.add('on');}
function claimOffline(){G.coins+=_offE;G.allC+=_offE;checkAchs();updateHUD();document.getElementById('offpop').classList.remove('on');showNotif('+'+fmt(_offE)+' монет!');}
function getNick(){var s=localStorage.getItem('gymNick');if(s)return s;if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user){var u=Telegram.WebApp.initDataUnsafe.user;return u.username||u.first_name||('user'+u.id);}return null;}
function getId(){if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user)return''+Telegram.WebApp.initDataUnsafe.user.id;var id=localStorage.getItem('gymId');if(!id){id='anon_'+Date.now();localStorage.setItem('gymId',id);}return id;}
function checkNick(){if(!getNick()){document.getElementById('nickpop').classList.add('on');setTimeout(function(){document.getElementById('nickIn').focus();},350);}}
function saveNick(){var v=document.getElementById('nickIn').value.trim();var hint=document.getElementById('nickHint');if(v.length<2){hint.textContent='Минимум 2 символа!';return;}if(v.length>20){hint.textContent='Максимум 20 символов!';return;}localStorage.setItem('gymNick',v);document.getElementById('nickpop').classList.remove('on');showNotif('Привет, '+v+'!');pushScore();}
var API=window.location.origin;
function pushScore(){var nick=getNick();if(!nick||G.cps<=0)return;try{fetch(API+'/api/score',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:getId(),username:nick,cph:Math.floor(G.cps*3600)})});}catch(e){}}
function buildPodium(rows){var el=document.getElementById('lbPod');if(!rows||!rows.length){el.innerHTML='';return;}var myN=getNick();var t3=rows.slice(0,3);var ord=t3.length>=2?[t3[1],t3[0],t3[2]].filter(Boolean):[t3[0]];var cls=t3.length>=2?['p2','p1','p3']:['p1'];var num=t3.length>=2?[2,1,3]:[1];var html='<div class="pod"><div class="podt">Зал Славы</div><div class="pods">';for(var i=0;i<ord.length;i++){var r=ord[i];var me=r.username===myN;html+='<div class="podsl '+cls[i]+'"><div class="podc">'+(num[i]===1?'&#x1F451;':'')+'</div><div class="podci">&#x1F4AA;</div><div class="podnm"'+(me?' style="color:var(--gn)"':'')+'>'+r.username+(me?' &#x1F448;':'')+'</div><div class="podcp">'+fmt(r.cph)+'/ч</div><div class="podbk">'+num[i]+'</div></div>';}html+='</div></div>';el.innerHTML=html;}
function loadLB(){var el=document.getElementById('lbList');el.innerHTML='<div class="lbem">Загрузка...</div>';document.getElementById('lbPod').innerHTML='';fetch(API+'/api/leaderboard').then(function(r){return r.json();}).then(function(rows){buildPodium(rows);var rest=rows.slice(3);if(!rest.length){el.innerHTML='';return;}var myN=getNick();var html='<div class="poddiv"></div>';for(var i=0;i<rest.length;i++){var r=rest[i];var me=r.username===myN;html+='<div class="lbrow'+(me?' me':'')+'"><div class="lbrk">'+(i+4)+'</div><div class="lbnm">'+r.username+(me?' &#x1F448;':'')+'</div><div class="lbcp">'+fmt(r.cph)+'/ч</div></div>';}el.innerHTML=html;}).catch(function(){el.innerHTML='<div class="lbem">Ошибка загрузки</div>';});}
var _lastTick=Date.now();
function tick(){var now=Date.now();var dt=Math.min((now-_lastTick)/1000,0.5);_lastTick=now;
  if(G.cps>0){G.coins+=G.cps*dt;G.allC+=G.cps*dt;}
  if(G.aCps>0){G.coins+=G.aCps*G.cpc*dt;G.allC+=G.aCps*G.cpc*dt;}
  G.nrg=Math.min(G.mxE,G.nrg+G.rgE*dt);G.pt+=dt;updateHUD();}
window.addEventListener('DOMContentLoaded',function(){
  loadGame();recalc();applySkin(G.skin||'default');updateHUD();renderAll();checkOffline();checkNick();
  setInterval(tick,100);setInterval(saveGame,5000);setInterval(renderAll,1000);setInterval(checkAchs,3000);setInterval(pushScore,30000);
  var coin=document.getElementById('coin');
  coin.addEventListener('touchstart',function(e){e.preventDefault();this.classList.add('tap');var self=this;setTimeout(function(){self.classList.remove('tap');},300);for(var i=0;i<e.changedTouches.length;i++){doClick(e.changedTouches[i].clientX,e.changedTouches[i].clientY);}},{passive:false});
  coin.addEventListener('mousedown',function(e){this.classList.add('tap');var self=this;setTimeout(function(){self.classList.remove('tap');},300);doClick(e.clientX,e.clientY);});
  document.getElementById('profBtn').addEventListener('click',openDrawer);
  document.getElementById('drCloseBtn').addEventListener('click',closeDrawer);
  document.getElementById('ov').addEventListener('click',closeDrawer);
  document.getElementById('nickSaveBtn').addEventListener('click',saveNick);
  document.getElementById('nickIn').addEventListener('keydown',function(e){if(e.key==='Enter')saveNick();});
  document.getElementById('nickEditBtn').addEventListener('click',changeNick);
  document.getElementById('offBtn').addEventListener('click',claimOffline);
  document.getElementById('lbRefBtn').addEventListener('click',loadLB);
  document.getElementById('tabs').addEventListener('click',function(e){var b=e.target.closest('.tab');if(!b)return;var t=b.dataset.t;var tabs=document.querySelectorAll('.tab');var panels=document.querySelectorAll('.panel');for(var i=0;i<tabs.length;i++)tabs[i].classList.toggle('on',tabs[i].dataset.t===t);for(var i=0;i<panels.length;i++)panels[i].classList.toggle('on',panels[i].id==='panel-'+t);if(t==='top')loadLB();});
  var drtabs=document.querySelectorAll('.drtab');
  for(var i=0;i<drtabs.length;i++){drtabs[i].addEventListener('click',function(){var p=this.dataset.p;var tabs=document.querySelectorAll('.drtab');var pans=document.querySelectorAll('.drp');for(var j=0;j<tabs.length;j++)tabs[j].classList.toggle('on',tabs[j].dataset.p===p);for(var j=0;j<pans.length;j++)pans[j].classList.toggle('on',pans[j].id==='drp-'+p);if(p==='achs')renderAchs();if(p==='skins')renderSkins();});}
  document.addEventListener('click',function(e){var u=e.target.closest('[data-uid]');if(u){buyUpgrade(u.dataset.uid);return;}var s=e.target.closest('[data-sid]');if(s){tapSkin(s.dataset.sid);return;}var a=e.target.closest('[data-aid]');if(a){claimReward(a.dataset.aid);return;}});
  var taskBtn=document.getElementById('taskTgBtn');
  if(taskBtn){if(localStorage.getItem('task_tg')){taskBtn.textContent='Выполнено';taskBtn.disabled=true;document.getElementById('taskTg').classList.add('done');}
    taskBtn.addEventListener('click',function(){window.open('https://t.me/gymclicker','_blank');var btn=this;setTimeout(function(){if(!localStorage.getItem('task_tg')){localStorage.setItem('task_tg','1');G.coins+=10000;G.allC+=10000;updateHUD();saveGame();showNotif('+10,000 монет за подписку!');btn.textContent='Выполнено';btn.disabled=true;document.getElementById('taskTg').classList.add('done');}},3000);});}
  if(window.Telegram&&Telegram.WebApp){Telegram.WebApp.ready();Telegram.WebApp.expand();}
});
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

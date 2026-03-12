"""
main.py — Качалка Кликер
"""

import os, json, logging, sqlite3, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN")
GAME_URL  = os.environ.get("GAME_URL",  "https://YOUR_DOMAIN")
PORT      = int(os.environ.get("PORT", 8080))
DB_PATH   = os.environ.get("DB_PATH", "leaderboard.db")

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    con = sqlite3.connect(DB_PATH)
    # Reset all players on deploy
    con.execute("DROP TABLE IF EXISTS leaderboard")
    con.execute("""
        CREATE TABLE leaderboard (
            user_id  TEXT PRIMARY KEY,
            username TEXT,
            cph      REAL,
            skin     TEXT DEFAULT 'default',
            updated  INTEGER
        )
    """)
    con.commit()
    con.close()
    logger.info("[DB] Reset: %s", DB_PATH)

def upsert_score(user_id, username, cph, skin="default"):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO leaderboard (user_id, username, cph, skin, updated)
        VALUES (?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            cph      = excluded.cph,
            skin     = excluded.skin,
            updated  = excluded.updated
    """, (str(user_id), str(username)[:32], float(cph), str(skin)))
    con.commit()
    con.close()

def get_top(n=20):
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT username, cph, skin FROM leaderboard ORDER BY cph DESC LIMIT ?", (n,)
    ).fetchall()
    con.close()
    return [{"username": r[0], "cph": r[1], "skin": r[2] or "default"} for r in rows]

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
.chipv{font-size:13px;font-weight:900;color:var(--gd);line-height:1}.chipl{font-size:9px;color:var(--mt);margin-top:2px}
#clicker{display:flex;flex-direction:column;align-items:center;padding:10px 14px 6px}
.nrg{width:100%;max-width:320px;margin-bottom:12px}
.nrgt{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
.nrgl{color:var(--or);font-weight:800;letter-spacing:1px}
.nrgb{height:7px;background:rgba(255,255,255,.07);border-radius:4px;overflow:hidden;border:1px solid rgba(255,100,0,.15)}
.nrgf{height:100%;background:linear-gradient(90deg,#ff3c00,var(--or),#ffa500);border-radius:4px;transition:width .12s linear}
.coinwrap{position:relative;display:flex;align-items:center;justify-content:center;margin:0;flex-direction:column;align-items:center}
.glow{position:absolute;width:210px;height:210px;border-radius:50%;pointer-events:none;background:radial-gradient(circle,rgba(255,200,0,.18) 0%,transparent 70%);animation:gp 2s ease-in-out infinite}
@keyframes gp{0%,100%{transform:scale(1);opacity:.8}50%{transform:scale(1.12);opacity:1}}
/* 3D PHYSICS COIN */
.coin-scene{width:190px;height:190px;perspective:600px;cursor:pointer;-webkit-user-select:none;user-select:none;touch-action:none;position:relative;z-index:10}
.coin-3d{width:190px;height:190px;border-radius:50%;position:relative;transform-style:preserve-3d;transition:transform .05s ease-out;will-change:transform}
.coin-face,.coin-back{position:absolute;inset:0;border-radius:50%;display:flex;align-items:center;justify-content:center;backface-visibility:hidden}
.coin-face{
  background:
    radial-gradient(circle at 32% 28%,rgba(255,255,200,.9) 0%,rgba(255,220,50,.4) 20%,transparent 55%),
    radial-gradient(circle at 65% 70%,rgba(120,60,0,.4) 0%,transparent 45%),
    conic-gradient(from 0deg,#c8860a,#ffd700,#f0b800,#e8a000,#ffc800,#d4900a,#ffd700,#c8860a);
  box-shadow:
    0 0 0 5px rgba(255,180,0,.35),
    0 0 40px rgba(255,160,0,.5),
    0 12px 40px rgba(0,0,0,.7),
    inset 0 2px 6px rgba(255,255,200,.6),
    inset 0 -2px 6px rgba(100,50,0,.4);
  font-size:88px;line-height:1;
}
.coin-face::before{content:'';position:absolute;inset:10px;border-radius:50%;border:2px solid rgba(255,215,0,.25)}
.coin-back{
  background:conic-gradient(from 0deg,#a07000,#d4a010,#b88800,#c89800,#a07000);
  transform:rotateY(180deg);
  box-shadow:inset 0 0 20px rgba(0,0,0,.5);
  font-size:50px;line-height:1;
}
.coin-shadow{position:absolute;bottom:-16px;left:50%;transform:translateX(-50%);width:160px;height:20px;border-radius:50%;background:rgba(0,0,0,.4);filter:blur(8px);transition:all .1s}
#coin{display:none}
.coin-3d.dead{filter:grayscale(.7) brightness(.5)}

@keyframes coinBounce{
  0%  {transform:rotateX(0) rotateY(0) scale(1)}
  15% {transform:rotateX(25deg) rotateY(-15deg) scale(.78) translateY(8px)}
  35% {transform:rotateX(-12deg) rotateY(12deg) scale(.85)}
  55% {transform:rotateX(6deg) rotateY(-6deg) scale(1.06)}
  75% {transform:rotateX(-3deg) rotateY(3deg) scale(1.02)}
  100%{transform:rotateX(0) rotateY(0) scale(1)}
}
.coin-3d.tap{animation:coinBounce .4s cubic-bezier(.25,.46,.45,.94)}
.ft{position:fixed;pointer-events:none;z-index:9999;font-size:28px;font-weight:900;color:#fff;text-shadow:0 0 8px rgba(255,200,0,1),0 0 20px rgba(255,150,0,.9),0 2px 0 rgba(0,0,0,.8);animation:fup 1.1s ease-out forwards;white-space:nowrap;letter-spacing:.5px}
.ft.crit{color:#fff;text-shadow:0 0 8px rgba(255,80,0,1),0 0 24px rgba(255,40,0,.9),0 2px 0 rgba(0,0,0,.8);font-size:34px}
@keyframes fup{0%{opacity:1;transform:translateY(0) scale(.8)}15%{opacity:1;transform:translateY(-10px) scale(1.3)}60%{opacity:1;transform:translateY(-60px) scale(1.1)}100%{opacity:0;transform:translateY(-110px) scale(.9)}}
.rp{position:fixed;pointer-events:none;z-index:9998;border-radius:50%;background:rgba(255,200,0,.25);animation:ro .45s ease-out forwards}
@keyframes ro{0%{transform:scale(0);opacity:.8}100%{transform:scale(3.5);opacity:0}}
#tabs-wrap{position:relative}
#tabs{display:flex;gap:4px;padding:8px 14px 0;overflow-x:auto;scrollbar-width:none}
#tabs::-webkit-scrollbar{display:none}
.tab{flex-shrink:0;padding:10px 14px;background:var(--c1);border:1px solid rgba(255,255,255,.07);border-radius:10px;color:var(--mt);font-family:'Nunito',sans-serif;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}
.tab.on{background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,215,0,.1));border-color:rgba(255,215,0,.4);color:var(--gd)}
.tarr{position:absolute;top:50%;margin-top:4px;transform:translateY(-50%);width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,var(--or),var(--gd));border:none;color:#000;font-size:11px;font-weight:900;cursor:pointer;z-index:10;opacity:0;pointer-events:none;transition:opacity .2s}
.tarr.show{opacity:1;pointer-events:all}
.tarr.tl{left:2px}.tarr.tr{right:2px}
.panel{display:none;padding:0 0 110px}.panel.on{display:block}
.sec{font-size:9px;font-weight:900;letter-spacing:3px;color:rgba(255,200,0,.6);text-transform:uppercase;margin:14px 0 8px;padding:5px 10px;border-radius:6px;background:rgba(255,200,0,.05);border:1px solid rgba(255,200,0,.1)}.sec:first-child{margin-top:4px}
.upg{background:linear-gradient(160deg,rgba(30,28,52,1) 0%,rgba(18,18,32,1) 100%);border:1px solid rgba(255,255,255,.08);border-radius:18px;padding:16px;display:flex;align-items:center;gap:14px;margin-bottom:10px;cursor:pointer;position:relative;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.07),inset 0 -1px 0 rgba(0,0,0,.4)}
.upg.ok{border-color:rgba(255,200,0,.35);box-shadow:0 4px 20px rgba(255,150,0,.18),inset 0 1px 0 rgba(255,255,255,.08),inset 0 -1px 0 rgba(0,0,0,.4)}.upg.ok::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,120,0,.08),rgba(255,215,0,.07),transparent);pointer-events:none}
.upg.mx{opacity:.4;cursor:default}
.upg.upgrading{border-color:rgba(255,100,0,.5);background:linear-gradient(135deg,rgba(255,100,0,.06),var(--c1))}
.uico{width:58px;height:58px;border-radius:14px;flex-shrink:0;font-size:28px;display:flex;align-items:center;justify-content:center;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.14)}
.ubod{flex:1;min-width:0}.unam{font-size:14px;font-weight:800;color:var(--tx);margin-bottom:3px}.udsc{font-size:11px;color:var(--mt);line-height:1.35}.ueff{font-size:11px;color:var(--bl);font-weight:700;margin-top:3px}.ulvl{font-size:10px;color:var(--or);font-weight:700;margin-top:3px}
.utmr{font-size:10px;color:var(--or);font-weight:800;margin-top:4px;letter-spacing:.5px}
.utmr.ready{color:var(--gn)}
.uprg{position:absolute;bottom:0;left:0;height:3px;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:0 0 0 16px;transition:width .3s linear}
.uprc{flex-shrink:0;text-align:right;min-width:60px}
.uprv{font-size:14px;font-weight:900;color:var(--gd)}.uprv.no{color:var(--rd)}.uprl{font-size:10px;color:var(--mt);margin-top:1px}
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
.lbsk{font-size:22px;flex-shrink:0}
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
.coin-soon-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;min-height:60vh;text-align:center}
.coin-spin{font-size:110px;line-height:1;filter:drop-shadow(0 0 24px rgba(255,200,0,.7));display:inline-block;margin-bottom:24px;animation:cspin 2s linear infinite;transform-origin:center}
@keyframes cspin{0%{transform:rotateY(0deg)}25%{transform:rotateY(90deg) scaleX(.1)}50%{transform:rotateY(180deg)}75%{transform:rotateY(270deg) scaleX(.1)}100%{transform:rotateY(360deg)}}
.coin-soon-title{font-size:36px;font-weight:900;color:var(--gd);letter-spacing:4px;margin-bottom:8px;text-shadow:0 0 20px rgba(255,200,0,.5)}
.coin-soon-sub{font-size:18px;font-weight:800;color:var(--or);letter-spacing:6px;text-transform:uppercase;margin-bottom:20px}
.coin-soon-desc{font-size:13px;color:var(--mt);line-height:1.7;margin-bottom:28px;max-width:280px}
.coin-soon-btn{display:inline-block;padding:14px 28px;border-radius:14px;background:linear-gradient(135deg,var(--or),var(--gd));color:#000;font-family:'Nunito',sans-serif;font-size:14px;font-weight:900;text-decoration:none}
.crash-wrap{padding:10px 14px 100px}
.crash-hdr{text-align:center;margin-bottom:16px}
.crash-title{font-size:28px;font-weight:900;color:var(--rd);text-shadow:0 0 20px rgba(255,34,68,.5)}
.crash-sub{font-size:12px;color:var(--mt);margin-top:4px}
.crash-screen{background:var(--c1);border:1px solid rgba(255,34,68,.2);border-radius:16px;padding:20px;text-align:center;margin-bottom:16px;min-height:140px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;position:relative;overflow:hidden}
.crash-mult{font-size:52px;font-weight:900;color:var(--gd);text-shadow:0 0 30px rgba(255,200,0,.6);line-height:1;transition:color .2s}

50%{transform:translateX(3px)}}
.crash-coinrun{font-size:40px;animation:coinrun .5s ease-in-out infinite;display:inline-block}
@keyframes coinrun{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-10px) rotate(12deg)}}
.crash-stat{font-size:13px;color:var(--mt);font-weight:700}
.crash-betw{background:var(--c1);border:1px solid rgba(255,215,0,.12);border-radius:16px;padding:16px;margin-bottom:14px}
.crash-betl{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);text-transform:uppercase;margin-bottom:10px}
.crash-betr{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.cbb{flex:1;min-width:44px;padding:8px 4px;background:var(--c2);border:1px solid rgba(255,215,0,.15);border-radius:9px;color:var(--gd);font-family:'Nunito',sans-serif;font-size:12px;font-weight:800;cursor:pointer}
.cbb.sel{background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,215,0,.1));border-color:rgba(255,215,0,.4)}
.cbb:active{transform:scale(.95)}
.crash-custr{display:flex;gap:8px;margin-bottom:10px}
.crash-inp{flex:1;padding:9px 12px;border-radius:9px;border:1.5px solid rgba(255,215,0,.2);background:rgba(255,255,255,.06);color:var(--tx);font-family:'Nunito',sans-serif;font-size:14px;font-weight:700;outline:none;-webkit-appearance:none}
.crash-inp:focus{border-color:rgba(255,215,0,.5)}
.crash-setb{padding:9px 14px;border-radius:9px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;color:#000;cursor:pointer}
.crash-betdisp{font-size:13px;font-weight:800;color:var(--gd);text-align:center}
.crash-btnr{display:flex;gap:10px;margin-bottom:16px}
.crash-startb,.crash-cashb{flex:1;padding:14px;border:none;border-radius:13px;font-family:'Nunito',sans-serif;font-size:15px;font-weight:900;cursor:pointer;transition:transform .1s}
.crash-startb{background:linear-gradient(135deg,var(--or),var(--gd));color:#000}
.crash-startb:disabled{opacity:.35;cursor:not-allowed}
.crash-cashb{background:linear-gradient(135deg,#00aa00,var(--gn));color:#000}
.crash-cashb:disabled{opacity:.35;cursor:not-allowed}
.crash-startb:active:not(:disabled),.crash-cashb:active:not(:disabled){transform:scale(.97)}
.crash-hist{background:var(--c1);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
.crash-histt{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);text-transform:uppercase;margin-bottom:10px}
.crash-histl{display:flex;flex-wrap:wrap;gap:6px}
.ch{padding:5px 10px;border-radius:20px;font-size:12px;font-weight:800}
.ch.w{background:rgba(57,255,20,.15);color:var(--gn);border:1px solid rgba(57,255,20,.3)}
.ch.l{background:rgba(255,34,68,.12);color:var(--rd);border:1px solid rgba(255,34,68,.25)}
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
.sk{background:var(--c1);border:2px solid rgba(255,255,255,.07);border-radius:16px;padding:18px 12px;display:flex;flex-direction:column;align-items:center;gap:10px;cursor:pointer;position:relative;overflow:hidden}
.sk.ok{border-color:rgba(255,215,0,.3)}.sk.own{border-color:rgba(57,255,20,.3)}
.sk.eq{border-color:rgba(57,255,20,.75);background:linear-gradient(135deg,rgba(57,255,20,.08),transparent)}
.sk.lk{opacity:.5}.sk.ak{opacity:.55;cursor:default}
.skprev{width:90px;height:90px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:52px;flex-shrink:0;box-shadow:0 4px 16px rgba(0,0,0,.5),inset 0 2px 4px rgba(255,255,255,.2)}
.skn{font-size:12px;font-weight:800;text-align:center;color:var(--tx);line-height:1.3}
.skp{font-size:12px;font-weight:700;color:var(--gd);text-align:center}.skp.no{color:var(--rd)}.skp.ac{color:var(--bl);font-size:10px}
.skbdg{position:absolute;top:6px;right:6px;font-size:9px;font-weight:800;padding:2px 6px;border-radius:20px}
.beq{background:rgba(57,255,20,.2);color:var(--gn)}.bown{background:rgba(57,255,20,.12);color:var(--gn)}.blk{background:rgba(255,255,255,.07);color:var(--mt)}.bac{background:rgba(0,200,255,.15);color:var(--bl)}
.reset-btn{width:100%;padding:12px;margin-top:14px;border:1px solid rgba(255,34,68,.4);border-radius:12px;background:rgba(255,34,68,.08);color:var(--rd);font-family:'Nunito',sans-serif;font-size:13px;font-weight:800;cursor:pointer}
#bnav{position:fixed;bottom:12px;left:10px;right:10px;z-index:90;background:rgba(18,18,30,.96);border:1px solid rgba(255,215,0,.15);border-radius:20px;display:flex;padding:6px 4px;box-shadow:0 4px 24px rgba(0,0,0,.5),0 0 0 1px rgba(255,215,0,.05)}
.bnb{flex:1;background:transparent;border:none;color:var(--mt);font-family:'Nunito',sans-serif;cursor:pointer;padding:8px 4px 6px;display:flex;flex-direction:column;align-items:center;gap:3px;transition:all .2s;border-radius:14px}
.bnb.on{color:var(--gd);background:rgba(255,215,0,.08)}
.bnb-i{font-size:22px;line-height:1}
.bnb-l{font-size:9px;font-weight:800;letter-spacing:.5px}
.ubtabs{display:flex;gap:8px;padding:12px 14px 4px;margin-bottom:2px}
.ubtab{flex:1;padding:14px;border-radius:14px;border:1.5px solid rgba(255,255,255,.08);background:linear-gradient(135deg,rgba(22,20,40,.99),rgba(20,20,34,.98));color:var(--mt);font-family:'Nunito',sans-serif;font-size:14px;font-weight:800;cursor:pointer;transition:all .2s;box-shadow:0 2px 8px rgba(0,0,0,.3)}
.ubtab.on{background:linear-gradient(135deg,rgba(255,100,0,.25),rgba(255,200,0,.15));border-color:rgba(255,215,0,.4);color:var(--gd);box-shadow:0 2px 16px rgba(255,150,0,.2)}
.ubpan{display:none}.ubpan.on{display:block}
.mine-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:12px 14px 4px}
.mine-stat{background:linear-gradient(135deg,rgba(22,20,40,.99),rgba(20,20,34,.98));border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:14px 12px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.06)}
.mine-sv{font-size:19px;font-weight:900;color:var(--gd);text-shadow:0 0 12px rgba(255,200,0,.5)}
.mine-sl{font-size:9px;color:var(--mt);margin-top:3px;font-weight:800;letter-spacing:.5px;text-transform:uppercase}
.claim-all-btn{padding:8px 14px;border-radius:9px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:'Nunito',sans-serif;font-size:11px;font-weight:900;color:#000;cursor:pointer}
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
  <div class="hm"><div class="hc" id="hCoins">0</div><div class="hl">&#x1F4AA; БИЦУШКИ</div></div>
  <div class="hr"><div class="hcph" id="hCph">0/&#x447;</div><div class="hcphl">&#x1F4C8; В ЧАС</div></div>
</div>
<div id="xpbar">
  <div class="xrow">
    <span style="color:var(--or);font-weight:800">&#x2B50; <span id="lvlName">Новичок</span> &#x2014; Ур.<span id="lvlNum">1</span></span>
    <span id="xpTxt">0/100</span>
  </div>
  
  
  <div class="panel on" id="panel-mine">
    <div class="mine-stats">
      <div class="mine-stat"><div class="mine-sv" id="msCpc">+1</div><div class="mine-sl">за клик</div></div>
      <div class="mine-stat"><div class="mine-sv" id="msCrit">0%</div><div class="mine-sl">крит шанс</div></div>
      <div class="mine-stat"><div class="mine-sv" id="msCps">0/сек</div><div class="mine-sl">пассив</div></div>
      <div class="mine-stat"><div class="mine-sv" id="msLuck">0%</div><div class="mine-sl">удача</div></div>
    </div>
  <div id="clicker">
      <div class="nrg">
        <div class="nrgt"><span class="nrgl">&#x26A1; ЭНЕРГИЯ</span><span id="nTxt">100/100</span></div>
        <div class="nrgb"><div class="nrgf" id="nFill" style="width:100%"></div></div>
      </div>
      <div class="coinwrap">
        <div class="glow" id="cglow"></div>
        <button id="coin" style="display:none">&#x1F4AA;</button>
        <div class="coin-scene" id="coinScene">
          <div class="coin-3d" id="coin3d">
            <div class="coin-face" id="coinFace">&#x1F4AA;</div>
            <div class="coin-back">&#x1FA99;</div>
          </div>
          <div class="coin-shadow" id="coinShadow"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="panel" id="panel-upgrade">
    <div class="ubtabs">
      <button class="ubtab on" data-u="hit">&#x1F44A; Удар</button>
      <button class="ubtab" data-u="income">&#x1F4B0; Бицушки/час</button>
    </div>
    <div class="ubpan on" id="ubpan-hit">
      <div class="sec">Сила удара</div><div id="lClick2"></div>
      <div class="sec">Энергия</div><div id="lEnergy2"></div>
      <div class="sec">Критический удар</div><div id="lCrit2"></div>
      <div class="sec">Специальные</div><div id="lSpecial2"></div>
    </div>
    <div class="ubpan" id="ubpan-income">
      <div class="sec">Инвестиции в страны</div><div id="lPassive2"></div>
    </div>
  </div>
  <div class="xt"><div class="xf" id="xpFill" style="width:0%"></div></div>
</div>
<div id="chips">
  <div class="chip"><div class="chipv" id="cCpc">+1</div><div class="chipl">за клик</div></div>
  <div class="chip"><div class="chipv" id="cCps">0</div><div class="chipl">пассив/с</div></div>
  <div class="chip"><div class="chipv" id="cCrit">0%</div><div class="chipl">крит</div></div>
  <div class="chip"><div class="chipv" id="cLuck">0%</div><div class="chipl">удача</div></div>
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
      <div class="taskrew">&#x1F4AA; Награда: 10,000 бицушек</div>
    </div>
    <button class="taskbtn" id="taskTgBtn">ПЕРЕЙТИ</button>
  </div>
  <div class="sec" style="margin-top:20px">COIN</div>
  <div class="coin-soon-wrap" style="min-height:auto;padding:20px 0">
    <div class="coin-spin" style="font-size:80px;margin-bottom:16px">&#x1FA99;</div>
    <div class="coin-soon-title" style="font-size:26px">COIN</div>
    <div class="coin-soon-sub" style="font-size:14px;margin-bottom:12px">Coming Soon</div>
    <div class="coin-soon-desc">Собственная монета GymClicker.<br>Следи за обновлениями!</div>
    <a class="coin-soon-btn" href="https://t.me/gymclicker" target="_blank">&#x1F4E2; Канал</a>
  </div>
</div>
<div class="panel" id="panel-crash">
  <div class="crash-wrap">
    <div class="crash-hdr">
      <div class="crash-title">&#x1F4A5; CRASH</div>
      <div class="crash-sub">Забери до краша или потеряй всё</div>
    </div>
    <div class="crash-screen">
      <div class="crash-mult" id="crashMult">x1.00</div>
      <div class="crash-coinrun" id="crashCoin">&#x1F4AA;</div>
      <div class="crash-stat" id="crashStat">Сделай ставку и начни</div>
    </div>
    <div class="crash-betw">
      <div class="crash-betl">Ставка (&#x1F4AA; бицушки)</div>
      <div class="crash-betr">
        <button class="cbb" data-bet="100">100</button>
        <button class="cbb" data-bet="500">500</button>
        <button class="cbb" data-bet="1000">1K</button>
        <button class="cbb" data-bet="5000">5K</button>
        <button class="cbb" data-bet="10000">10K</button>
        <button class="cbb" data-bet="all">ВСЕ</button>
      </div>
      <div class="crash-custr">
        <input class="crash-inp" id="crashBetIn" type="number" placeholder="Своя ставка..." min="1">
        <button class="crash-setb" id="crashSetBtn">&#x2713;</button>
      </div>
      <div class="crash-betdisp" id="crashBetDisp">Ставка: 0 &#x1F4AA;</div>
    </div>
    <div class="crash-btnr">
      <button class="crash-startb" id="crashStartBtn">&#x1F680; НАЧАТЬ</button>
      <button class="crash-cashb" id="crashCashBtn" disabled>&#x1F4B0; ЗАБРАТЬ</button>
    </div>
    <div class="crash-hist">
      <div class="crash-histt">История</div>
      <div class="crash-histl" id="crashHistList"></div>
    </div>
  </div>
</div>

<nav id="bnav">
  <button class="bnb on" data-t="mine">
    <span class="bnb-i">💪</span>
    <span class="bnb-l">Добыча</span>
  </button>
  <button class="bnb" data-t="upgrade">
    <span class="bnb-i">⬆️</span>
    <span class="bnb-l">Прокачка</span>
  </button>
  <button class="bnb" data-t="crash">
    <span class="bnb-i">💥</span>
    <span class="bnb-l">Краш</span>
  </button>
  <button class="bnb" data-t="top">
    <span class="bnb-i">👑</span>
    <span class="bnb-l">Топ</span>
  </button>
  <button class="bnb" data-t="extra">
    <span class="bnb-i">➕</span>
    <span class="bnb-l">Доп</span>
  </button>
</nav>

<div id="notif"></div>
<div id="apop"><div id="apopi">&#x1F3C6;</div><div><div class="apl">ДОСТИЖЕНИЕ!</div><div class="apn" id="apN">-</div><div class="apr" id="apR"></div></div></div>
<div id="offpop">
  <div class="offmod">
    <div class="offic">&#x1F4A4;</div>
    <div style="font-size:15px;font-weight:900;margin-bottom:4px">Пока тебя не было...</div>
    <div style="font-size:12px;color:var(--mt);margin-bottom:14px" id="offT"></div>
    <div style="font-size:11px;color:var(--mt);letter-spacing:1px;margin-bottom:4px">КАЧАЛКА ЗАРАБОТАЛА:</div>
    <div style="font-size:40px;font-weight:900;color:var(--gd);line-height:1" id="offE">+0</div>
    <button class="offbtn" id="offBtn">ЗАБРАТЬ &#x1F4AA;</button>
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
    <button class="drtab on" data-p="stats">📊 Стат</button>
    <button class="drtab" data-p="achs">🏆 Ачив</button>
    <button class="drtab" data-p="skins">🎨 Скины</button>
    <button class="drtab" data-p="bgs">🖼 Фон</button>
  </div>
  <div class="drbody">
    <div class="drp on" id="drp-stats">
      <div class="sgrid" style="margin-top:2px">
        <div class="sc"><div class="scv" id="stTC">0</div><div class="scl">Всего бицушек</div></div>
        <div class="sc"><div class="scv" id="stCL">0</div><div class="scl">Кликов</div></div>
        <div class="sc"><div class="scv" id="stPT">0м</div><div class="scl">Время игры</div></div>
        <div class="sc"><div class="scv" id="stMS">0</div><div class="scl">Макс /сек</div></div>
        <div class="sc"><div class="scv" id="stMC">+1</div><div class="scl">Макс за клик</div></div>
        <div class="sc"><div class="scv" id="stCR">0</div><div class="scl">Критов</div></div>
        <div class="sc"><div class="scv" id="stSK">0</div><div class="scl">Скинов</div></div>
        <div class="sc"><div class="scv" id="stAC">0</div><div class="scl">Достижений</div></div>
      </div>
      <button class="reset-btn" id="resetBtn">&#x1F5D1; Сбросить прогресс</button>
    </div>
    <div class="drp" id="drp-achs"><div id="achList"></div></div>
    <div class="drp" id="drp-skins"><div class="skgrid" id="skinList"></div></div>
    <div class="drp" id="drp-bgs"><div class="skgrid" id="bgList"></div></div>
  </div>
</div>
<script><script>


'use strict';
var LVS=[{n:'Новичок',x:0},{n:'Любитель',x:100},{n:'Спортсмен',x:300},{n:'Атлет',x:700},{n:'Культурист',x:1500},{n:'Чемпион',x:3500},{n:'Мастер',x:8000},{n:'Легенда',x:20000},{n:'Бог Железа',x:50000},{n:'АБСОЛЮТ',x:120000},{n:'Железный Кулак',x:200000},{n:'Стальная Воля',x:350000},{n:'Гранитный',x:550000},{n:'Титановый',x:850000},{n:'Алмазный',x:1300000},{n:'Платиновый',x:2000000},{n:'Космический',x:3000000},{n:'Галактический',x:4500000},{n:'Вселенский',x:7000000},{n:'Квантовый',x:10000000},{n:'Ультра',x:15000000},{n:'Мега',x:22000000},{n:'Гига',x:32000000},{n:'Тера',x:47000000},{n:'Пета',x:70000000},{n:'Экза',x:100000000},{n:'ЛЕГЕНДА ВСЕХ ВРЕМЁН',x:150000000},{n:'БОГ КАЧАЛКИ',x:220000000},{n:'СОЗДАТЕЛЬ',x:330000000},{n:'БЕСКОНЕЧНЫЙ',x:500000000}];
var UPG={
click:[
{id:'c1',n:'Протеиновый шейк',i:'🥤',d:'Больше сил в руках',bp:25,pg:2.1,mx:20,ef:'cpc',v:1},
{id:'c2',n:'Спортперчатки',i:'🥊',d:'Точный удар',bp:120,pg:2.2,mx:20,ef:'cpc',v:3},
{id:'c3',n:'Предтрен',i:'⚡',d:'Взрывная сила',bp:600,pg:2.3,mx:20,ef:'cpc',v:10},
{id:'c4',n:'Анаболики',i:'💉',d:'Сила зашкаливает',bp:4000,pg:2.4,mx:15,ef:'cpc',v:40},
{id:'c5',n:'Режим зверя',i:'🦁',d:'Ты непобедим',bp:30000,pg:2.5,mx:12,ef:'cpc',v:200},
{id:'c6',n:'Бог качалки',i:'🏛',d:'Запредельная мощь',bp:300000,pg:2.6,mx:10,ef:'cpc',v:1200},
{id:'c7',n:'Квантовый удар',i:'⚛',d:'Разрушает пространство',bp:3000000,pg:2.7,mx:8,ef:'cpc',v:8000},
{id:'c8',n:'Перчатки Титана',i:'🧤',d:'Сила запредельная',bp:25000000,pg:2.8,mx:6,ef:'cpc',v:60000},
{id:'c9',n:'Молот Тора',i:'🔨',d:'Мощь бога грома',bp:200000000,pg:2.9,mx:5,ef:'cpc',v:500000},
{id:'c10',n:'Перчатки Бесконечности',i:'♾',d:'Неограниченная сила',bp:2000000000,pg:3.0,mx:4,ef:'cpc',v:5000000},
{id:'c11',n:'Удар Галактики',i:'🌌',d:'Пробивает галактики',bp:20000000000,pg:3.1,mx:3,ef:'cpc',v:50000000},
{id:'c12',n:'Взрыв Вселенной',i:'💥',d:'Мощь Большого взрыва',bp:200000000000,pg:3.2,mx:3,ef:'cpc',v:500000000},
{id:'c13',n:'Рука Бога',i:'✋',d:'Бог нажимает за тебя',bp:2000000000000,pg:3.3,mx:2,ef:'cpc',v:5000000000},
{id:'c14',n:'Омега Удар',i:'🔱',d:'Превосходит всё',bp:20000000000000,pg:3.4,mx:2,ef:'cpc',v:50000000000},
{id:'c15',n:'Бицепс Времени',i:'⏳',d:'Удары сквозь время',bp:200000000000000,pg:3.5,mx:1,ef:'cpc',v:500000000000}
],
energy:[
{id:'e1',n:'Расширенный запас',i:'🔋',d:'Больше максимальной энергии',bp:150,pg:2.2,mx:20,ef:'mxE',v:50},
{id:'e2',n:'Быстрое восст.',i:'🔄',d:'+0.3 восст./сек за уровень',bp:400,pg:2.3,mx:20,ef:'rgE',v:0.3}
],
crit:[
{id:'cr1',n:'Меткость I',i:'🎯',d:'Шанс крита +5%',bp:800,pg:2.3,mx:5,ef:'critC',v:5},
{id:'cr2',n:'Снайпер I',i:'🔭',d:'Шанс крита +10%',bp:25000,pg:2.5,mx:5,ef:'critC',v:10}
],
passive:[
{id:'p1',n:'Россия',i:'🇷🇺',d:'Инвестируй в российские качалки',bp:50,pg:1.8,mx:20,ef:'cps',v:0.25},
{id:'p2',n:'Исландия',i:'🇮🇸',d:'Ледяные залы Рейкьявика',bp:300,pg:1.9,mx:20,ef:'cps',v:1},
{id:'p3',n:'США',i:'🇺🇸',d:'Сеть American Gym',bp:1500,pg:2.0,mx:20,ef:'cps',v:4},
{id:'p4',n:'ОАЭ',i:'🇦🇪',d:'Люксовые залы Дубая',bp:8000,pg:2.1,mx:20,ef:'cps',v:15},
{id:'p5',n:'Япония',i:'🇯🇵',d:'Технологии Japanese Fit',bp:50000,pg:2.2,mx:18,ef:'cps',v:75},
{id:'p6',n:'Германия',i:'🇩🇪',d:'Немецкая инженерия силы',bp:200000,pg:2.3,mx:16,ef:'cps',v:300},
{id:'p7',n:'Великобритания',i:'🇬🇧',d:'Королевские залы Лондона',bp:800000,pg:2.3,mx:15,ef:'cps',v:1250},
{id:'p8',n:'Китай',i:'🇨🇳',d:'Миллиард качающихся',bp:3000000,pg:2.4,mx:12,ef:'cps',v:5000},
{id:'p9',n:'Бразилия',i:'🇧🇷',d:'Пляжные качалки Рио',bp:12000000,pg:2.4,mx:10,ef:'cps',v:20000},
{id:'p10',n:'Европейский союз',i:'🇪🇺',d:'Сеть залов по всей Европе',bp:50000000,pg:2.5,mx:10,ef:'cps',v:90000},
{id:'p11',n:'Австралия',i:'🇦🇺',d:'Залы под звёздным небом',bp:200000000,pg:2.5,mx:8,ef:'cps',v:400000},
{id:'p12',n:'Канада',i:'🇨🇦',d:'Хоккейно-силовые залы',bp:800000000,pg:2.6,mx:7,ef:'cps',v:1750000},
{id:'p13',n:'Индия',i:'🇮🇳',d:'Йога и сила 1.4 млрд',bp:3200000000,pg:2.6,mx:6,ef:'cps',v:7500000},
{id:'p14',n:'Весь мир',i:'🌍',d:'Залы на всех континентах',bp:15000000000,pg:2.7,mx:5,ef:'cps',v:35000000},
{id:'p15',n:'МКС',i:'🚀',d:'Тренировки в невесомости',bp:70000000000,pg:2.7,mx:4,ef:'cps',v:175000000},
{id:'p16',n:'Луна',i:'🌙',d:'Первый зал на Луне',bp:350000000000,pg:2.8,mx:4,ef:'cps',v:1000000000},
{id:'p17',n:'Марс',i:'🔴',d:'Качаешься на красной планете',bp:1500000000000,pg:2.8,mx:3,ef:'cps',v:5000000000},
{id:'p18',n:'Юпитер',i:'🪐',d:'Гравитация качает сама',bp:7000000000000,pg:2.9,mx:3,ef:'cps',v:25000000000},
{id:'p19',n:'Галактика',i:'🌌',d:'Галактические качалки',bp:30000000000000,pg:2.9,mx:2,ef:'cps',v:125000000000},
{id:'p20',n:'Машина времени',i:'⏰',d:'Бицушки из прошлого и будущего',bp:150000000000000,pg:3.0,mx:2,ef:'cps',v:750000000000}
],
special:[
{id:'sp1',n:'Комбо-удар',i:'🎰',d:'Каждый 10-й клик даёт x10',bp:50000,pg:999,mx:1,ef:'combo',v:1},
{id:'sp2',n:'Фортуна',i:'🍀',d:'15% шанс удвоить бицушки',bp:35000,pg:999,mx:1,ef:'luck',v:15}
]};
var ALL_UPG=[];
['click','energy','crit','passive','special'].forEach(function(k){ALL_UPG=ALL_UPG.concat(UPG[k]);});

var ACHS=[
{id:'a1',i:'👆',n:'Первый клик',d:'Нажми на монету',c:function(s){return s.clicks>=1;},r:{t:'c',v:10}},
{id:'a2',i:'💪',n:'100 кликов',d:'Сделай 100 кликов',c:function(s){return s.clicks>=100;},r:{t:'c',v:200}},
{id:'a3',i:'🔥',n:'1000 кликов',d:'Сделай 1000 кликов',c:function(s){return s.clicks>=1000;},r:{t:'c',v:2000}},
{id:'a4',i:'💥',n:'10K кликов',d:'Машина для кликов!',c:function(s){return s.clicks>=10000;},r:{t:'c',v:20000}},
{id:'a5',i:'🦾',n:'100K кликов',d:'Ты кликер-легенда',c:function(s){return s.clicks>=100000;},r:{t:'s',v:'toxic'}},
{id:'a6',i:'💰',n:'100 бицушек',d:'Накопи 100 бицушек',c:function(s){return s.allC>=100;},r:{t:'c',v:50}},
{id:'a7',i:'💎',n:'10K бицушек',d:'Накопи 10k бицушек',c:function(s){return s.allC>=10000;},r:{t:'c',v:5000}},
{id:'a8',i:'🏦',n:'1M бицушек',d:'Миллионер!',c:function(s){return s.allC>=1000000;},r:{t:'s',v:'diamond'}},
{id:'a9',i:'⬆',n:'Первый апгрейд',d:'Купи улучшение',c:function(s){return s.allU>=1;},r:{t:'c',v:100}},
{id:'a10',i:'🛒',n:'25 апгрейдов',d:'Инвестор!',c:function(s){return s.allU>=25;},r:{t:'c',v:25000}},
{id:'a11',i:'😴',n:'Пассивный доход',d:'1 бицушка/сек',c:function(s){return s.cps>=1;},r:{t:'c',v:500}},
{id:'a12',i:'⭐',n:'Стахановец',d:'100 бицушек/сек',c:function(s){return s.cps>=100;},r:{t:'s',v:'galaxy'}},
{id:'a13',i:'🏅',n:'Уровень 5',d:'Достигни 5-го уровня',c:function(s){return s.lvl>=5;},r:{t:'c',v:10000}},
{id:'a14',i:'🥇',n:'Уровень 10',d:'Достигни 10-го уровня',c:function(s){return s.lvl>=10;},r:{t:'s',v:'fire'}},
{id:'a15',i:'👑',n:'Уровень 20',d:'Достигни 20-го уровня',c:function(s){return s.lvl>=20;},r:{t:'s',v:'rainbow'}},
{id:'a16',i:'🎯',n:'Критикан',d:'100 критических ударов',c:function(s){return s.crits>=100;},r:{t:'c',v:15000}},
{id:'a17',i:'🎰',n:'Комбо-мастер',d:'Активируй комбо 10 раз',c:function(s){return s.combos>=10;},r:{t:'c',v:30000}},
{id:'a18',i:'💸',n:'Крэш-победитель',d:'Выиграй 5 раз в Crash',c:function(s){return s.crashWins>=5;},r:{t:'s',v:'lava'}},
{id:'a19',i:'🌌',n:'Галактический',d:'Купи Галактика Силы',c:function(s){return s.sk.includes('galaxy');},r:{t:'c',v:50000}},
{id:'a20',i:'♾',n:'Бесконечный',d:'Достигни уровня БЕСКОНЕЧНЫЙ',c:function(s){return s.lvl>=30;},r:{t:'s',v:'cyber'}},
{id:'a21',i:'🔥',n:'1M бицушек',d:'Накопи 1 миллион',c:function(s){return s.allC>=1000000;},r:{t:'c',v:50000}},
{id:'a22',i:'💫',n:'10M бицушек',d:'Накопи 10 миллионов',c:function(s){return s.allC>=10000000;},r:{t:'c',v:500000}},
{id:'a23',i:'🌟',n:'1B бицушек',d:'Миллиардер!',c:function(s){return s.allC>=1000000000;},r:{t:'c',v:5000000}},
{id:'a24',i:'⚡',n:'50K кликов',d:'50 тысяч кликов',c:function(s){return s.clicks>=50000;},r:{t:'c',v:10000}},
{id:'a25',i:'💎',n:'Уровень 15',d:'Достигни 15-го уровня',c:function(s){return s.lvl>=15;},r:{t:'s',v:'neon'}},
{id:'a26',i:'🏆',n:'Уровень 25',d:'Достигни 25-го уровня',c:function(s){return s.lvl>=25;},r:{t:'s',v:'platinum'}},
{id:'a27',i:'🎯',n:'Крит мастер',d:'500 критических ударов',c:function(s){return s.crits>=500;},r:{t:'c',v:100000}},
{id:'a28',i:'💥',n:'Комбо легенда',d:'Комбо 50 раз',c:function(s){return s.combos>=50;},r:{t:'c',v:200000}},
{id:'a29',i:'🌊',n:'Краш ветеран',d:'Выиграй 20 раз в Crash',c:function(s){return (s.crashWins||0)>=20;},r:{t:'s',v:'ocean'}},
{id:'a30',i:'🖼',n:'Коллекционер',d:'Купи любой фон',c:function(s){return s.bgs&&s.bgs.length>1;},r:{t:'c',v:50000}}
];

var SKINS=[
{id:'default',n:'Золотая Классика',e:'💪',p:0,ach:null,bg:'radial-gradient(circle at 35% 30%,rgba(255,255,180,.55) 0%,transparent 50%),linear-gradient(135deg,#f5c518,#e8a800,#ffd700,#cc8800)',sh:'0 0 0 4px rgba(255,200,0,.28),0 0 30px rgba(255,175,0,.4)',gl:'rgba(255,200,0,.18)'},
{id:'fire',n:'Огненный Атлет',e:'🔥',p:0,ach:'a14',bg:'radial-gradient(circle at 35% 25%,rgba(255,200,100,.5) 0%,transparent 50%),linear-gradient(135deg,#ff4500,#ff6b00,#ff0000,#cc2200)',sh:'0 0 0 4px rgba(255,80,0,.4),0 0 35px rgba(255,60,0,.6)',gl:'rgba(255,80,0,.2)'},
{id:'ice',n:'Ледяной Колосс',e:'❄',p:5000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(200,240,255,.6) 0%,transparent 50%),linear-gradient(135deg,#00c8ff,#0080cc,#004488)',sh:'0 0 0 4px rgba(0,180,255,.4),0 0 35px rgba(0,180,255,.5)',gl:'rgba(0,180,255,.18)'},
{id:'toxic',n:'Токсичный',e:'☢',p:0,ach:'a5',bg:'radial-gradient(circle at 40% 30%,rgba(180,255,100,.5) 0%,transparent 50%),linear-gradient(135deg,#39ff14,#22cc00,#009900)',sh:'0 0 0 4px rgba(57,255,20,.4),0 0 40px rgba(57,255,20,.6)',gl:'rgba(57,255,20,.2)'},
{id:'galaxy',n:'Галактика',e:'🌌',p:25000,ach:null,bg:'radial-gradient(circle at 30% 25%,rgba(200,150,255,.5) 0%,transparent 50%),linear-gradient(135deg,#6600cc,#9933ff,#3300aa)',sh:'0 0 0 4px rgba(180,0,255,.4),0 0 40px rgba(150,0,255,.6)',gl:'rgba(150,0,255,.2)'},
{id:'diamond',n:'Бриллиант',e:'💎',p:0,ach:'a8',bg:'radial-gradient(circle at 30% 20%,rgba(255,255,255,.9) 0%,transparent 40%),linear-gradient(135deg,#a8d8ff,#e0f4ff,#b8e8ff)',sh:'0 0 0 4px rgba(150,210,255,.5),0 0 50px rgba(100,200,255,.7)',gl:'rgba(150,220,255,.25)'},
{id:'lava',n:'Магма',e:'🌋',p:0,ach:'a18',bg:'radial-gradient(circle at 35% 25%,rgba(255,220,100,.6) 0%,transparent 45%),linear-gradient(135deg,#ff8c00,#cc2200,#ff4400)',sh:'0 0 0 4px rgba(255,100,0,.5),0 0 50px rgba(255,80,0,.7)',gl:'rgba(255,80,0,.25)'},
{id:'rainbow',n:'Радуга',e:'🦄',p:0,ach:'a15',bg:'linear-gradient(135deg,#ff0080,#ff8c00,#ffed00,#00c800,#0080ff,#8000ff)',sh:'0 0 0 4px rgba(255,0,128,.4),0 0 50px rgba(128,0,255,.5)',gl:'rgba(200,0,200,.2)'},
{id:'shadow',n:'Тёмный',e:'🖤',p:400000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(100,0,200,.5) 0%,transparent 50%),linear-gradient(135deg,#1a0030,#2d0050,#0d001a)',sh:'0 0 0 4px rgba(100,0,200,.4),0 0 40px rgba(80,0,150,.6)',gl:'rgba(100,0,200,.2)'},
{id:'cyber',n:'Кибер',e:'🤖',p:0,ach:'a20',bg:'radial-gradient(circle at 35% 25%,rgba(0,255,200,.4) 0%,transparent 50%),linear-gradient(135deg,#001a1a,#003333,#00ff88)',sh:'0 0 0 4px rgba(0,255,180,.4),0 0 50px rgba(0,255,150,.5)',gl:'rgba(0,255,150,.2)'},
{id:'blood',n:'Кровавый',e:'🩸',p:80000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,100,100,.5) 0%,transparent 50%),linear-gradient(135deg,#8b0000,#cc0000,#ff0000,#990000)',sh:'0 0 0 4px rgba(200,0,0,.5),0 0 40px rgba(180,0,0,.6)',gl:'rgba(180,0,0,.2)'},
{id:'ocean',n:'Океан',e:'🌊',p:60000,ach:null,bg:'radial-gradient(circle at 30% 25%,rgba(100,200,255,.5) 0%,transparent 50%),linear-gradient(135deg,#003366,#0066cc,#0099ff)',sh:'0 0 0 4px rgba(0,100,200,.4),0 0 40px rgba(0,120,255,.5)',gl:'rgba(0,150,255,.2)'},
{id:'forest',n:'Лес',e:'🌲',p:45000,ach:null,bg:'radial-gradient(circle at 35% 30%,rgba(100,255,100,.4) 0%,transparent 50%),linear-gradient(135deg,#1a4a00,#2d7a00,#3d9900)',sh:'0 0 0 4px rgba(0,150,0,.4),0 0 35px rgba(0,180,0,.5)',gl:'rgba(0,180,0,.2)'},
{id:'gold',n:'Золотой Царь',e:'👑',p:200000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,255,150,.7) 0%,transparent 50%),linear-gradient(135deg,#b8860b,#ffd700,#ffec8b,#b8860b)',sh:'0 0 0 4px rgba(255,215,0,.6),0 0 50px rgba(255,200,0,.8)',gl:'rgba(255,215,0,.3)'},
{id:'neon',n:'Неон',e:'👾',p:120000,ach:null,bg:'radial-gradient(circle at 40% 30%,rgba(0,255,255,.5) 0%,transparent 50%),linear-gradient(135deg,#000033,#003333,#00ffff)',sh:'0 0 0 4px rgba(0,255,255,.5),0 0 50px rgba(0,255,255,.6)',gl:'rgba(0,255,255,.2)'},
{id:'sunset',n:'Закат',e:'🌅',p:90000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,200,100,.5) 0%,transparent 50%),linear-gradient(135deg,#ff6600,#ff9900,#ffcc00)',sh:'0 0 0 4px rgba(255,150,0,.4),0 0 40px rgba(255,120,0,.5)',gl:'rgba(255,150,0,.2)'},
{id:'platinum',n:'Платина',e:'⚡',p:500000,ach:null,bg:'radial-gradient(circle at 30% 20%,rgba(220,220,255,.8) 0%,transparent 40%),linear-gradient(135deg,#c0c0c0,#e8e8e8,#f5f5f5,#a0a0a0)',sh:'0 0 0 4px rgba(192,192,192,.6),0 0 50px rgba(200,200,255,.7)',gl:'rgba(200,200,220,.3)'},
{id:'inferno',n:'Инферно',e:'😈',p:1000000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,50,0,.6) 0%,transparent 50%),linear-gradient(135deg,#1a0000,#660000,#ff2200)',sh:'0 0 0 4px rgba(255,0,0,.5),0 0 60px rgba(200,0,0,.7)',gl:'rgba(200,0,0,.25)'},
{id:'angel',n:'Ангел',e:'👼',p:750000,ach:null,bg:'radial-gradient(circle at 35% 25%,rgba(255,255,255,.9) 0%,transparent 50%),linear-gradient(135deg,#fffff0,#f0f8ff,#fff5ee)',sh:'0 0 0 4px rgba(255,255,200,.6),0 0 50px rgba(255,255,180,.8)',gl:'rgba(255,255,200,.4)'},
{id:'matrix',n:'Матрица',e:'🟩',p:300000,ach:null,bg:'radial-gradient(circle at 40% 30%,rgba(0,255,0,.4) 0%,transparent 50%),linear-gradient(135deg,#000800,#001a00,#003300)',sh:'0 0 0 4px rgba(0,255,0,.4),0 0 40px rgba(0,200,0,.6)',gl:'rgba(0,200,0,.2)'}
];

var BGS=[
  {id:'bg_default',n:'Тёмный космос',p:0,css:'#0d0d16'},
  {id:'bg_navy',n:'Глубокий синий',p:10000,css:'linear-gradient(180deg,#0a0a2e 0%,#0d0d40 100%)'},
  {id:'bg_fire',n:'Огненный ад',p:10000,css:'linear-gradient(180deg,#1a0000 0%,#2d0000 100%)'},
  {id:'bg_forest',n:'Тёмный лес',p:10000,css:'linear-gradient(180deg,#001a00 0%,#002800 100%)'},
  {id:'bg_purple',n:'Фиолетовый туман',p:10000,css:'linear-gradient(180deg,#0d0020 0%,#1a0035 100%)'},
  {id:'bg_gold',n:'Золотые тени',p:10000,css:'linear-gradient(180deg,#1a1200 0%,#2d2000 100%)'},
  {id:'bg_ice',n:'Ледяная пещера',p:10000,css:'linear-gradient(180deg,#001a2d 0%,#00263d 100%)'},
  {id:'bg_matrix',n:'Матрица',p:10000,css:'linear-gradient(180deg,#000d00 0%,#001800 100%)'},
  {id:'bg_sunset',n:'Закат',p:10000,css:'linear-gradient(180deg,#1a0a00 0%,#2d1500 100%)'},
  {id:'bg_space',n:'Звёздное небо',p:10000,css:'linear-gradient(180deg,#050510 0%,#0a0a20 100%)'}
];

var SAVE_KEY='gymv12';
var DEF={coins:0,allC:0,clicks:0,allU:0,crits:0,combos:0,crashWins:0,lvl:1,xp:0,nrg:100,mxE:100,rgE:2,cpc:1,cps:0,critC:0,critM:2,luck:0,combo:0,pt:0,mxCps:0,mxCpc:1,ul:{},achs:[],claimed:[],sk:['default'],skin:'default',bg:'bg_default',bgs:['bg_default'],lastSeen:null,comboN:0};
var G={};
var TIMERS={};

function loadGame(){
  try{var s=localStorage.getItem(SAVE_KEY);G=Object.assign({},DEF,s?JSON.parse(s):{});}
  catch(e){G=Object.assign({},DEF);}
  try{var t=localStorage.getItem(SAVE_KEY+'_t');if(t){var td=JSON.parse(t);Object.keys(td).forEach(function(k){if(!td[k].done)TIMERS[k]=td[k];});}}
  catch(e){}
}
function saveGame(){
  G.lastSeen=Date.now();
  try{localStorage.setItem(SAVE_KEY,JSON.stringify(G));}catch(e){}
  try{localStorage.setItem(SAVE_KEY+'_t',JSON.stringify(TIMERS));}catch(e){}
}
function fmt(n){
  n=Math.floor(n);
  if(n>=1e15)return(n/1e15).toFixed(1)+'Q';
  if(n>=1e12)return(n/1e12).toFixed(1)+'T';
  if(n>=1e9)return(n/1e9).toFixed(1)+'B';
  if(n>=1e6)return(n/1e6).toFixed(1)+'M';
  if(n>=1000)return(n/1000).toFixed(1)+'K';
  return String(n);
}
function uLvl(id){return G.ul[id]||0;}
function uPrice(u){return Math.floor(u.bp*Math.pow(u.pg,uLvl(u.id)));}
function nextVal(u){return parseFloat((u.v*Math.pow(1.10,uLvl(u.id))).toFixed(4));}

function recalc(){
  var cpc=1,cps=0,mxE=100,rgE=2,critC=0,luck=0,combo=0;
  for(var i=0;i<ALL_UPG.length;i++){
    var u=ALL_UPG[i];var l=uLvl(u.id);if(!l)continue;
    var tot=0;for(var lv=0;lv<l;lv++)tot+=u.v*Math.pow(1.10,lv);
    tot=parseFloat(tot.toFixed(4));
    if(u.ef==='cpc')cpc+=tot;
    else if(u.ef==='cps')cps+=tot;
    else if(u.ef==='mxE')mxE+=tot;
    else if(u.ef==='rgE')rgE+=tot;
    else if(u.ef==='critC')critC+=tot;
    else if(u.ef==='luck')luck+=tot;
    else if(u.ef==='combo')combo=Math.min(1,combo+tot);
  }
  G.cpc=Math.max(1,Math.floor(cpc));
  G.cps=parseFloat(cps.toFixed(2));
  G.mxE=Math.floor(mxE);
  G.rgE=parseFloat(rgE.toFixed(2));
  G.critC=Math.min(critC,80);
  G.luck=Math.min(luck,80);
  G.combo=combo;
  if(G.nrg>G.mxE)G.nrg=G.mxE;
  if(G.cps>G.mxCps)G.mxCps=G.cps;
  if(G.cpc>G.mxCpc)G.mxCpc=G.cpc;
}

function chkLvl(){
  while(G.lvl<LVS.length){
    var nx=LVS[G.lvl];
    if(!nx||G.xp<nx.x)break;
    G.lvl++;
    showNotif('🎉 Уровень '+G.lvl+' — '+LVS[G.lvl-1].n);
  }
}
function chkAchs(){
  var snap={clicks:G.clicks,allC:G.allC,allU:G.allU,cps:G.cps,lvl:G.lvl,crits:G.crits,combos:G.combos,crashWins:G.crashWins||0,ul:G.ul,sk:G.sk};
  for(var i=0;i<ACHS.length;i++){
    var a=ACHS[i];
    if(G.achs.indexOf(a.id)>=0)continue;
    if(!a.c(snap))continue;
    G.achs.push(a.id);
    if(a.r.t==='s'&&G.sk.indexOf(a.r.v)<0){G.sk.push(a.r.v);G.claimed.push(a.id);}
    showAchPopup(a);
  }
}
function claimReward(id){
  if(G.claimed.indexOf(id)>=0)return;
  var a=null;for(var i=0;i<ACHS.length;i++){if(ACHS[i].id===id){a=ACHS[i];break;}}
  if(!a||G.achs.indexOf(id)<0)return;
  G.claimed.push(id);
  if(a.r.t==='c'){G.coins+=a.r.v;G.allC+=a.r.v;updateHUD();showNotif('+'+fmt(a.r.v)+' бицушек!');}
  else if(a.r.t==='s'&&G.sk.indexOf(a.r.v)<0){G.sk.push(a.r.v);showNotif('Скин разблокирован!');renderSkins();}
  saveGame();renderAchs();
}
function resetProgress(){
  if(!confirm('Сбросить весь прогресс? Это необратимо!'))return;
  localStorage.removeItem(SAVE_KEY);localStorage.removeItem(SAVE_KEY+'_t');
  TIMERS={};G=Object.assign({},DEF);
  recalc();updateHUD();renderAll();renderAchs();renderSkins();
  showNotif('Прогресс сброшен!');
}

function getUpgTime(u,newLvl){
  if(newLvl<=5)return 30+Math.floor(Math.random()*270);
  if(newLvl<=15)return 300+Math.floor(Math.random()*600);
  return 900+Math.floor(Math.random()*900);
}
function fmtTime(sec){
  if(sec<=0)return'0с';
  if(sec<60)return sec+'с';
  var m=Math.floor(sec/60),s=sec%60;
  return m+'м'+(s>0?' '+s+'с':'');
}
function buyUpgrade(id){
  var u=null;for(var i=0;i<ALL_UPG.length;i++){if(ALL_UPG[i].id===id){u=ALL_UPG[i];break;}}
  if(!u)return;
  if(TIMERS[id]&&!TIMERS[id].done){
    var rem=Math.ceil((TIMERS[id].end-Date.now())/1000);
    if(rem>0){showNotif('Прокачка: '+fmtTime(rem));return;}
  }
  var l=uLvl(id);if(l>=u.mx)return;
  var p=uPrice(u);if(G.coins<p){showNotif('Недостаточно бицушек!');return;}
  G.coins-=p;G.allU++;
  var dur=getUpgTime(u,l+1);
  TIMERS[id]={end:Date.now()+dur*1000,total:dur,done:false};
  updateHUD();renderAll();
  showNotif(u.n+' — прокачка '+fmtTime(dur)+'...');
}

function doClick(x,y){
  if(G.nrg<1){showNotif('Нет энергии!');return;}
  G.nrg=Math.max(0,G.nrg-1);
  var earn=G.cpc,isCrit=false;
  if(G.combo>0){G.comboN=(G.comboN||0)+1;if(G.comboN>=10){earn*=10;G.comboN=0;G.combos=(G.combos||0)+1;spawnFlt('КОМБО x10!',x,y-30,null);}}
  if(G.critC>0&&Math.random()*100<G.critC){earn=Math.floor(earn*G.critM);isCrit=true;G.crits++;}
  if(G.luck>0&&Math.random()*100<G.luck){earn*=2;spawnFlt('УДАЧА x2!',x,y-30,null);}
  earn=Math.floor(earn);
  G.coins+=earn;G.allC+=earn;G.clicks++;G.xp+=1;
  chkLvl();chkAchs();
  spawnFlt((isCrit?'x':'+')+''+fmt(earn),x,y,isCrit?'#ff5500':null);
  spawnRipple(x,y);updateHUD();
}
function tapSkin(id){
  var s=null;for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id){s=SKINS[i];break;}}if(!s)return;
  if(s.ach&&G.sk.indexOf(id)<0){showNotif('Нужно достижение!');return;}
  if(G.sk.indexOf(id)>=0){G.skin=id;applySkin(id);saveGame();renderSkins();showNotif('Скин надет!');}
  else{if(G.coins<s.p){showNotif('Недостаточно бицушек!');return;}G.coins-=s.p;G.sk.push(id);G.skin=id;applySkin(id);saveGame();updateHUD();renderSkins();showNotif('Скин куплен!');}
}
function getSkinEmoji(id){for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id)return SKINS[i].e;}return '💪';}
function applySkin(id){
  var s=SKINS[0];for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id){s=SKINS[i];break;}}
  // Update hidden #coin
  var btn=document.getElementById('coin');
  if(btn){btn.style.background=s.bg;btn.style.boxShadow=s.sh;btn.innerHTML=s.e;}
  // Update 3D coin face
  var face=document.getElementById('coinFace');
  if(face){face.style.background=s.bg;face.style.boxShadow=s.sh;face.innerHTML=s.e;}
  var gl=document.getElementById('cglow');
  if(gl)gl.style.background='radial-gradient(circle,'+s.gl+' 0%,transparent 70%)';
  document.getElementById('profBtn').innerHTML=s.e;
  document.getElementById('drAva').innerHTML=s.e;
  var cc=document.getElementById('crashCoin');if(cc)cc.innerHTML=s.e;
}

function applyBg(id){
  var bg=BGS[0];for(var i=0;i<BGS.length;i++){if(BGS[i].id===id){bg=BGS[i];break;}}
  document.body.style.background=bg.css;
  G.bg=id;
}
function tapBg(id){
  var bg=null;for(var i=0;i<BGS.length;i++){if(BGS[i].id===id){bg=BGS[i];break;}}if(!bg)return;
  if(G.bgs.indexOf(id)>=0){applyBg(id);saveGame();renderBgs();showNotif('Фон применён!');}
  else{if(G.coins<bg.p){showNotif('Недостаточно бицушек!');return;}G.coins-=bg.p;G.bgs.push(id);applyBg(id);saveGame();updateHUD();renderBgs();showNotif('Фон куплен!');}
}
function renderBgs(){
  var el=document.getElementById('bgList');if(!el)return;
  var rows=[];
  for(var i=0;i<BGS.length;i++){
    var bg=BGS[i];var own=G.bgs.indexOf(bg.id)>=0;var active=G.bg===bg.id;var ok=!own&&G.coins>=bg.p;
    var badge=active?'<span class="skbdg beq">✓</span>':(own?'<span class="skbdg bown">куплен</span>':'');
    var price=bg.p===0?'<div class="skp" style="color:var(--gn)">БЕСПЛАТНО</div>':
      (own?(active?'<div class="skp" style="color:var(--gn)">АКТИВЕН</div>':'<div class="skp" style="color:var(--or)">ПРИМЕНИТЬ</div>'):
       '<div class="skp'+(ok?'':' no')+'">'+fmt(bg.p)+' 💪</div>');
    rows.push('<div class="sk'+(active?' eq':own?' own':ok?' ok':' lk')+'" data-bgid="'+bg.id+'">'+badge+'<div class="skprev" style="background:'+bg.css+';box-shadow:none;border:2px solid rgba(255,255,255,.15)"> </div><div class="skn">'+bg.n+'</div>'+price+'</div>');
  }
  el.innerHTML=rows.join('');
}
function updateHUD(){
  document.getElementById('hCoins').textContent=fmt(G.coins);
  document.getElementById('hCph').textContent=fmt(G.cps*3600)+'/ч';
  document.getElementById('cCpc').textContent='+'+fmt(G.cpc);
  document.getElementById('cCps').textContent=fmt(G.cps);
  document.getElementById('cCrit').textContent=Math.round(G.critC)+'%';
  document.getElementById('cLuck').textContent=Math.round(G.luck)+'%';
  document.getElementById('nTxt').textContent=Math.floor(G.nrg)+'/'+G.mxE;
  document.getElementById('nFill').style.width=(G.nrg/G.mxE*100)+'%';
  var ci=G.lvl-1,cx=LVS[ci]?LVS[ci].x:0,nx=LVS[G.lvl]?LVS[G.lvl].x:LVS[LVS.length-1].x+999999;
  var pct=nx>cx?Math.min(100,(G.xp-cx)/(nx-cx)*100):100;
  document.getElementById('xpFill').style.width=pct+'%';
  document.getElementById('xpTxt').textContent=fmt(G.xp-cx)+'/'+fmt(nx-cx);
  document.getElementById('lvlNum').textContent=G.lvl;
  document.getElementById('lvlName').textContent=LVS[ci]?LVS[ci].n:'MAX';
  document.getElementById('lbMe').textContent=fmt(G.cps*3600)+'/ч';
  var el;
  el=document.getElementById('msCpc');if(el)el.textContent='+'+fmt(G.cpc);
  el=document.getElementById('msCrit');if(el)el.textContent=Math.round(G.critC)+'%';
  el=document.getElementById('msCps');if(el)el.textContent=fmt(G.cps)+'/сек';
  el=document.getElementById('msLuck');if(el)el.textContent=Math.round(G.luck)+'%';
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
  document.getElementById('stAC').textContent=G.achs.length+'/'+ACHS.length;
}

function effLbl(u){
  var v=nextVal(u);
  if(u.ef==='cpc')return'+'+fmt(v)+' 💪 за клик';
  if(u.ef==='cps')return'+'+fmt(v)+'/сек (+'+fmt(Math.round(v*3600))+'/ч)';
  if(u.ef==='mxE')return'+'+fmt(v)+' энергии';
  if(u.ef==='rgE')return'+'+v.toFixed(1)+' восст./сек';
  if(u.ef==='critC')return'+'+v+'% шанс крита';
  if(u.ef==='luck')return'+'+v+'% удвоить';
  if(u.ef==='combo')return'каждый 10-й клик x10';
  return '';
}
function renderList(cid,list){
  var el=document.getElementById(cid);if(!el)return;
  var rows=[];
  for(var i=0;i<list.length;i++){
    var u=list[i];var l=uLvl(u.id);var mx=l>=u.mx;
    var tmr=TIMERS[u.id];
    var cls,priceHtml,timerHtml='',progHtml='';
    if(tmr&&!tmr.done){
      var rem=Math.max(0,Math.ceil((tmr.end-Date.now())/1000));
      var pct=Math.min(100,Math.round((1-(tmr.end-Date.now())/(tmr.total*1000))*100));
      if(pct<0)pct=0;
      if(rem<=0){cls='upg ok';priceHtml='<div class="uprv" style="color:var(--gn)">ГОТОВО!</div>';timerHtml='<div class="utmr ready">✅ Нажми чтобы получить</div>';}
      else{cls='upg upgrading';priceHtml='<div class="uprv" style="color:var(--or)">'+fmtTime(rem)+'</div>';timerHtml='<div class="utmr">⏳ '+fmtTime(rem)+'</div>';progHtml='<div class="uprg" style="width:'+pct+'%"></div>';}
    } else {
      var p=uPrice(u);var ok=!mx&&G.coins>=p;
      cls='upg'+(ok?' ok':'')+(mx?' mx':'');
      priceHtml=mx?'<div class="uprv" style="color:var(--gn)">МАКС</div>':'<div class="uprv'+(ok?'':' no')+'">'+fmt(p)+'</div><div class="uprl">💪</div>';
    }
    rows.push('<div class="'+cls+'" data-uid="'+u.id+'">'
      +'<div class="uico">'+u.i+'</div>'
      +'<div class="ubod"><div class="unam">'+u.n+'</div>'
      +'<div class="udsc">'+u.d+'</div>'
      +'<div class="ueff">'+effLbl(u)+'</div>'
      +'<div class="ulvl">Ур. '+l+' / '+u.mx+'</div>'
      +timerHtml+'</div>'
      +'<div class="uprc">'+priceHtml+'</div>'
      +progHtml+'</div>');
  }
  el.innerHTML=rows.join('');
}
function renderAll(){
  renderList('lClick',UPG.click);
  renderList('lEnergy',UPG.energy);
  renderList('lCrit',UPG.crit);
  renderList('lSpecial',UPG.special);
  renderList('lPassive',UPG.passive);
  renderList('lClick2',UPG.click);
  renderList('lEnergy2',UPG.energy);
  renderList('lCrit2',UPG.crit);
  renderList('lSpecial2',UPG.special);
  renderList('lPassive2',UPG.passive);
}
function claimAllRewards(){
  var count=0,coins=0;
  for(var i=0;i<ACHS.length;i++){
    var a=ACHS[i];
    if(G.achs.indexOf(a.id)>=0&&G.claimed.indexOf(a.id)<0){
      G.claimed.push(a.id);
      if(a.r.t==='c'){coins+=a.r.v;G.coins+=a.r.v;G.allC+=a.r.v;count++;}
      else if(a.r.t==='s'&&G.sk.indexOf(a.r.v)<0){G.sk.push(a.r.v);count++;}
    }
  }
  if(count>0){updateHUD();saveGame();renderAchs();renderSkins();showNotif('Забрано '+count+' наград! +'+fmt(coins)+' 💪');}
  else showNotif('Нет новых наград');
}
function renderAchs(){
  var el=document.getElementById('achList');if(!el)return;
  var rows=[];
  var canClaim=ACHS.filter(function(a){return G.achs.indexOf(a.id)>=0&&G.claimed.indexOf(a.id)<0;}).length;
  rows.push('<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center"><div style="flex:1;font-size:11px;color:var(--mt)">'+G.achs.length+'/'+ACHS.length+' выполнено</div>'+(canClaim>0?'<button class="claim-all-btn" id="claimAllBtn">ЗАБРАТЬ ВСЕ ('+canClaim+')</button>':'')+'</div>');
  for(var i=0;i<ACHS.length;i++){
    var a=ACHS[i];var done=G.achs.indexOf(a.id)>=0;var cl=G.claimed.indexOf(a.id)>=0;
    var rv=a.r.t==='c'?fmt(a.r.v)+' 💪':'';
    if(a.r.t==='s'){for(var j=0;j<SKINS.length;j++){if(SKINS[j].id===a.r.v){rv='🎨 '+SKINS[j].n;break;}}}
    var btn='';
    if(done&&!cl)btn='<button class="achbtn" data-aid="'+a.id+'">ЗАБРАТЬ</button>';
    else if(done&&cl)btn='<div class="achgot">✓</div>';
    rows.push('<div class="ach'+(done?' on':'')+'"><div class="achi">'+a.i+'</div><div class="achb"><div class="achn">'+a.n+'</div><div class="achd">'+(done?a.d:'???')+'</div><div class="achr">'+rv+'</div></div>'+(done?'<div>'+btn+'</div>':'')+'</div>');
  }
  el.innerHTML=rows.join('');
}
function renderSkins(){
  var el=document.getElementById('skinList');if(!el)return;
  var rows=[];
  for(var i=0;i<SKINS.length;i++){
    var s=SKINS[i];var own=G.sk.indexOf(s.id)>=0;var eq=G.skin===s.id;var alck=s.ach&&!own;var ok=!own&&!alck&&G.coins>=s.p;
    var badge='';
    if(eq)badge='<span class="skbdg beq">✓ НАДЕТ</span>';
    else if(own)badge='<span class="skbdg bown">КУПЛЕН</span>';
    else if(alck)badge='<span class="skbdg bac">АЧИВ</span>';
    else if(s.p>0)badge='<span class="skbdg blk">🔒</span>';
    var price='';
    if(s.p===0&&!alck)price='<div class="skp" style="color:var(--gn)">БЕСПЛАТНО</div>';
    else if(alck){var an='Достижение';for(var j=0;j<ACHS.length;j++){if(ACHS[j].id===s.ach){an=ACHS[j].n;break;}}price='<div class="skp ac">'+an+'</div>';}
    else if(own)price=eq?'<div class="skp" style="color:var(--gn)">НАДЕТ</div>':'<div class="skp" style="color:var(--or)">НАДЕТЬ</div>';
    else price='<div class="skp'+(ok?'':' no')+'">'+fmt(s.p)+' 💪</div>';
    var cls='sk'+(eq?' eq':own?' own':alck?' ak':ok?' ok':' lk');
    rows.push('<div class="'+cls+'" data-sid="'+s.id+'">'+badge+'<div class="skprev" style="background:'+s.bg+';box-shadow:'+s.sh+'">'+s.e+'</div><div class="skn">'+s.n+'</div>'+price+'</div>');
  }
  el.innerHTML=rows.join('');
}
function spawnFlt(txt,x,y,col){
  var el=document.createElement('div');
  el.className='ft'+(col?' crit':'');
  el.innerHTML=txt;
  if(col)el.style.color=col;
  // Random spread
  var spread=col?60:40;
  el.style.left=(x+(Math.random()*spread-spread/2))+'px';
  el.style.top=(y-20)+'px';
  document.body.appendChild(el);
  setTimeout(function(){el.remove();},1100);
}
function spawnRipple(x,y){var el=document.createElement('div');el.className='rp';el.style.cssText='left:'+(x-25)+'px;top:'+(y-25)+'px;width:50px;height:50px';document.body.appendChild(el);setTimeout(function(){el.remove();},450);}

var _ntT=null;
function showNotif(msg){var el=document.getElementById('notif');el.innerHTML=msg;el.classList.add('on');clearTimeout(_ntT);_ntT=setTimeout(function(){el.classList.remove('on');},2200);}
var _apQ=[],_apB=false;
function showAchPopup(a){_apQ.push(a);if(!_apB)nextAch();}
function nextAch(){
  if(!_apQ.length){_apB=false;return;}_apB=true;var a=_apQ.shift();
  document.getElementById('apopi').innerHTML=a.i;document.getElementById('apN').textContent=a.n;
  var rw=a.r.t==='c'?'Награда: '+fmt(a.r.v)+' 💪':'';
  if(a.r.t==='s'){for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===a.r.v){rw='Скин: '+SKINS[i].n;break;}}}
  document.getElementById('apR').innerHTML=rw;
  document.getElementById('apop').classList.add('on');
  setTimeout(function(){document.getElementById('apop').classList.remove('on');setTimeout(nextAch,400);},3000);
}

function openDrawer(){
  document.getElementById('ov').classList.add('on');document.getElementById('dr').classList.add('on');
  updateHUD();renderAchs();renderSkins();
  var n=getNick();if(n)document.getElementById('nickEdit').value=n;
}
function closeDrawer(){document.getElementById('ov').classList.remove('on');document.getElementById('dr').classList.remove('on');}
function changeNick(){var v=document.getElementById('nickEdit').value.trim();if(v.length<2||v.length>20){showNotif('Ник: 2-20 символов');return;}localStorage.setItem('gymNick',v);updateHUD();saveGame();showNotif('Ник: '+v);pushScore();}

var _offE=0;
function chkOffline(){
  if(!G.lastSeen||G.cps<=0)return;
  var sec=Math.min((Date.now()-G.lastSeen)/1000,7200);if(sec<30)return;
  _offE=Math.floor(G.cps*sec);if(!_offE)return;
  var h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60);
  document.getElementById('offT').textContent='Отсутствовал: '+(h?h+'ч ':'')+m+'мин';
  document.getElementById('offE').textContent='+'+fmt(_offE);
  document.getElementById('offpop').classList.add('on');
}
function claimOffline(){G.coins+=_offE;G.allC+=_offE;chkAchs();updateHUD();document.getElementById('offpop').classList.remove('on');showNotif('+'+fmt(_offE)+' бицушек!');}

function getNick(){var s=localStorage.getItem('gymNick');if(s)return s;if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user){var u=Telegram.WebApp.initDataUnsafe.user;return u.username||u.first_name||('user'+u.id);}return null;}
function getId(){if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user)return''+Telegram.WebApp.initDataUnsafe.user.id;var id=localStorage.getItem('gymId');if(!id){id='anon_'+Date.now();localStorage.setItem('gymId',id);}return id;}
function chkNick(){if(!getNick()){document.getElementById('nickpop').classList.add('on');setTimeout(function(){document.getElementById('nickIn').focus();},350);}}
function saveNick(){var v=document.getElementById('nickIn').value.trim();var hint=document.getElementById('nickHint');if(v.length<2){hint.textContent='Минимум 2 символа!';return;}if(v.length>20){hint.textContent='Максимум 20 символов!';return;}localStorage.setItem('gymNick',v);document.getElementById('nickpop').classList.remove('on');showNotif('Привет, '+v+'!');pushScore();}

var API=window.location.origin;
function pushScore(){var nick=getNick();if(!nick||G.cps<=0)return;try{fetch(API+'/api/score',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:getId(),username:nick,cph:Math.floor(G.cps*3600),skin:G.skin||'default'})});}catch(e){}}
function buildPodium(rows){
  var el=document.getElementById('lbPod');if(!rows||!rows.length){el.innerHTML='';return;}
  var myN=getNick();var t3=rows.slice(0,3);
  var ord=t3.length>=2?[t3[1],t3[0],t3[2]].filter(Boolean):[t3[0]];
  var cls=t3.length>=2?['p2','p1','p3']:['p1'];var num=t3.length>=2?[2,1,3]:[1];
  var h='<div class="pod"><div class="podt">🏆 Зал Славы</div><div class="pods">';
  for(var i=0;i<ord.length;i++){var r=ord[i];var me=r.username===myN;
    h+='<div class="podsl '+cls[i]+'"><div class="podc">'+(num[i]===1?'👑':'')+'</div><div class="podci">'+getSkinEmoji(r.skin||'default')+'</div><div class="podnm"'+(me?' style="color:var(--gn)"':'')+'>'+r.username+(me?' 👈':'')+'</div><div class="podcp">'+fmt(r.cph)+'/ч</div><div class="podbk">'+num[i]+'</div></div>';}
  h+='</div></div>';el.innerHTML=h;
}
function loadLB(){
  var el=document.getElementById('lbList');el.innerHTML='<div class="lbem">Загрузка...</div>';document.getElementById('lbPod').innerHTML='';
  fetch(API+'/api/leaderboard').then(function(r){return r.json();}).then(function(rows){
    buildPodium(rows);var rest=rows.slice(3);if(!rest.length){el.innerHTML='';return;}
    var myN=getNick();var h='<div class="poddiv"></div>';
    for(var i=0;i<rest.length;i++){var r=rest[i];var me=r.username===myN;
      h+='<div class="lbrow'+(me?' me':'')+'"><div class="lbrk">'+(i+4)+'</div><div class="lbsk">'+getSkinEmoji(r.skin||'default')+'</div><div class="lbnm">'+r.username+(me?' 👈':'')+'</div><div class="lbcp">'+fmt(r.cph)+'/ч</div></div>';}
    el.innerHTML=h;
  }).catch(function(){el.innerHTML='<div class="lbem">Ошибка</div>';});
}

var CRASH={bet:0,running:false,mult:1.0,timer:null,crashAt:1.0,history:[]};
try{CRASH.history=JSON.parse(localStorage.getItem('cH')||'[]');}catch(e){}
function crashGenPt(){var r=Math.random();if(r<.55)return 1+Math.random()*.4;if(r<.75)return 1.4+Math.random()*.6;if(r<.88)return 2+Math.random()*2;if(r<.95)return 4+Math.random()*6;if(r<.99)return 10+Math.random()*15;return 25+Math.random()*25;}
function setCrashBet(val){
  if(CRASH.running)return;
  var b=val==='all'?Math.floor(G.coins):parseInt(val);
  if(isNaN(b)||b<=0)return;
  b=Math.min(b,Math.floor(G.coins));CRASH.bet=b;
  document.getElementById('crashBetDisp').innerHTML='Ставка: '+fmt(b)+' 💪';
  document.querySelectorAll('.cbb').forEach(function(btn){btn.classList.toggle('sel',btn.dataset.bet==val);});
}
function crashStart(){
  if(CRASH.running)return;if(CRASH.bet<=0){showNotif('Сделай ставку!');return;}
  if(G.coins<CRASH.bet){showNotif('Недостаточно бицушек!');return;}
  G.coins-=CRASH.bet;updateHUD();
  CRASH.running=true;CRASH.mult=1.0;CRASH.crashAt=parseFloat(crashGenPt().toFixed(2));
  var cc=document.getElementById('crashCoin');cc.classList.add('crash-coinrun');
  document.getElementById('crashStartBtn').disabled=true;
  document.getElementById('crashCashBtn').disabled=false;
  document.getElementById('crashStat').textContent='Монетка бежит! Забери вовремя!';
  var spd=0.015;
    CRASH.timer=setInterval(function(){
      CRASH.mult=parseFloat((CRASH.mult+spd).toFixed(2));
      spd=Math.min(spd+0.0005,0.1);
      document.getElementById('crashMult').textContent='x'+CRASH.mult.toFixed(2);
      if(CRASH.mult>=CRASH.crashAt)crashEnd(false);
    },100);
}
function crashCash(){if(!CRASH.running)return;crashEnd(true);}
function crashEnd(won){
  clearInterval(CRASH.timer);CRASH.running=false;
  var cc=document.getElementById('crashCoin');cc.classList.remove('crash-coinrun');
  document.getElementById('crashStartBtn').disabled=false;
  document.getElementById('crashCashBtn').disabled=true;
  if(won){
    var win=Math.floor(CRASH.bet*CRASH.mult);G.coins+=win;G.allC+=win;updateHUD();
    CRASH.history.unshift({m:CRASH.mult.toFixed(2),w:true});
    G.crashWins=(G.crashWins||0)+1;chkAchs();
    document.getElementById('crashStat').textContent='Выиграл! +'+fmt(win)+' (x'+CRASH.mult.toFixed(2)+')';
    showNotif('+'+fmt(win)+' бицушек!');
    document.getElementById('crashMult').style.color='var(--gn)';
  } else {
    CRASH.history.unshift({m:CRASH.crashAt.toFixed(2),w:false});
    document.getElementById('crashStat').textContent='КРАШ на x'+CRASH.crashAt+'! Потерял '+fmt(CRASH.bet);
    showNotif('Краш на x'+CRASH.crashAt+'!');
    document.getElementById('crashCoin').innerHTML='💀';
    document.getElementById('crashMult').style.color='var(--rd)';
    setTimeout(function(){document.getElementById('crashCoin').innerHTML=getSkinEmoji(G.skin||'default');},1500);
  }
  if(CRASH.history.length>20)CRASH.history=CRASH.history.slice(0,20);
  try{localStorage.setItem('cH',JSON.stringify(CRASH.history));}catch(e){}
  renderCrashHist();
  setTimeout(function(){CRASH.mult=1.0;document.getElementById('crashMult').textContent='x1.00';document.getElementById('crashMult').style.color='';},2000);
}
function renderCrashHist(){
  var el=document.getElementById('crashHistList');if(!el)return;
  el.innerHTML=CRASH.history.map(function(h){return'<span class="ch '+(h.w?'w':'l')+'">x'+h.m+'</span>';}).join('');
}

var _lastT=Date.now();
function autoCollectTimers(){
  var changed=false;
  Object.keys(TIMERS).forEach(function(id){
    if(!TIMERS[id].done&&Date.now()>=TIMERS[id].end){
      TIMERS[id].done=true;
      G.ul[id]=(G.ul[id]||0)+1;G.allU++;G.xp+=10;
      changed=true;
      var u=null;for(var i=0;i<ALL_UPG.length;i++){if(ALL_UPG[i].id===id){u=ALL_UPG[i];break;}}
      recalc();chkLvl();chkAchs();
      if(u)showNotif('✅ '+u.n+' — Ур.'+uLvl(id)+' готово!');
      delete TIMERS[id];
    }
  });
  if(changed){updateHUD();renderAll();}
}
var _lastT=Date.now();
function tick(){
  var now=Date.now();var dt=Math.min((now-_lastT)/1000,0.5);_lastT=now;
  if(G.cps>0){G.coins+=G.cps*dt;G.allC+=G.cps*dt;}
  G.nrg=Math.min(G.mxE,G.nrg+G.rgE*dt);G.pt+=dt;
  updateHUD();
}

window.addEventListener('DOMContentLoaded',function(){
  loadGame();recalc();applySkin(G.skin||'default');applyBg(G.bg||'bg_default');updateHUD();renderAll();chkOffline();chkNick();renderCrashHist();
  setInterval(tick,100);setInterval(saveGame,5000);setInterval(renderAll,1000);setInterval(chkAchs,3000);setInterval(pushScore,30000);setInterval(autoCollectTimers,500);
  document.addEventListener('visibilitychange',function(){if(document.hidden)saveGame();});
  window.addEventListener('pagehide',saveGame);

  // 3D COIN physics
  var coinScene=document.getElementById('coinScene');
  var coin3dEl=document.getElementById('coin3d');
  var coinShadow=document.getElementById('coinShadow');
  var _tapActive=false;

  var _tapTs=[];
  function triggerCoin(x,y){
    var _n=Date.now();_tapTs=_tapTs.filter(function(t){return _n-t<1000;});if(_tapTs.length>=10)return;_tapTs.push(_n);
    if(_tapActive)return;
    _tapActive=true;
    coin3dEl.classList.add('tap');
    // Physics: tilt based on tap position relative to center
    var rect=coinScene.getBoundingClientRect();
    var cx=rect.left+rect.width/2,cy=rect.top+rect.height/2;
    var dx=(x-cx)/rect.width*2,dy=(y-cy)/rect.height*2;
    coin3dEl.style.animation='none';
    coin3dEl.offsetHeight; // reflow
    coin3dEl.style.animation='';
    coinShadow.style.transform='translateX(-50%) scale(.7)';
    coinShadow.style.opacity='.15';
    setTimeout(function(){
      coin3dEl.classList.remove('tap');
      coinShadow.style.transform='translateX(-50%) scale(1)';
      coinShadow.style.opacity='.4';
      _tapActive=false;
    },400);
    doClick(x,y);
  }
  if(coinScene){
    coinScene.addEventListener('touchstart',function(e){
      e.preventDefault();
      for(var i=0;i<e.changedTouches.length;i++){
        triggerCoin(e.changedTouches[i].clientX,e.changedTouches[i].clientY);
      }
    },{passive:false});
    coinScene.addEventListener('mousedown',function(e){triggerCoin(e.clientX,e.clientY);});
  }
  // Keep old #coin for applySkin compatibility
  var coin=document.getElementById('coin');

  // Profile
  document.getElementById('profBtn').addEventListener('click',openDrawer);
  document.getElementById('drCloseBtn').addEventListener('click',closeDrawer);
  document.getElementById('ov').addEventListener('click',closeDrawer);

  // Nick
  document.getElementById('nickSaveBtn').addEventListener('click',saveNick);
  document.getElementById('nickIn').addEventListener('keydown',function(e){if(e.key==='Enter')saveNick();});
  document.getElementById('nickEditBtn').addEventListener('click',changeNick);

  // Offline
  document.getElementById('offBtn').addEventListener('click',claimOffline);
  document.addEventListener('click',function(e){
    if(e.target.id==='claimAllBtn')claimAllRewards();
  });

  // LB
  document.getElementById('lbRefBtn').addEventListener('click',loadLB);

  // Reset
  document.getElementById('resetBtn').addEventListener('click',resetProgress);

  // Bottom nav
  document.getElementById('bnav').addEventListener('click',function(e){
    var b=e.target.closest('.bnb');if(!b)return;var t=b.dataset.t;
    document.querySelectorAll('.bnb').forEach(function(x){x.classList.toggle('on',x.dataset.t===t);});
    document.querySelectorAll('.panel').forEach(function(x){x.classList.toggle('on',x.id==='panel-'+t);});
    if(t==='top')loadLB();
  });

  // Upgrade sub-tabs
  document.querySelectorAll('.ubtab').forEach(function(b){
    b.addEventListener('click',function(){
      var u=this.dataset.u;
      document.querySelectorAll('.ubtab').forEach(function(x){x.classList.toggle('on',x.dataset.u===u);});
      document.querySelectorAll('.ubpan').forEach(function(x){x.classList.toggle('on',x.id==='ubpan-'+u);});
    });
  });

  // Profile tabs
  document.querySelectorAll('.drtab').forEach(function(b){
    b.addEventListener('click',function(){
      var p=this.dataset.p;
      document.querySelectorAll('.drtab').forEach(function(x){x.classList.toggle('on',x.dataset.p===p);});
      document.querySelectorAll('.drp').forEach(function(x){x.classList.toggle('on',x.id==='drp-'+p);});
      if(p==='achs')renderAchs();if(p==='skins')renderSkins();if(p==='bgs')renderBgs();
    });
  });

  // Upgrade / skin / ach delegation
  document.addEventListener('click',function(e){
    var u=e.target.closest('[data-uid]');if(u){buyUpgrade(u.dataset.uid);return;}
    var s=e.target.closest('[data-sid]');if(s){tapSkin(s.dataset.sid);return;}
    var bg=e.target.closest('[data-bgid]');if(bg){tapBg(bg.dataset.bgid);return;}
    var a=e.target.closest('[data-aid]');if(a){claimReward(a.dataset.aid);return;}
  });

  // TG task
  var tb=document.getElementById('taskTgBtn');
  if(tb){
    if(localStorage.getItem('tg_task')){tb.textContent='Выполнено';tb.disabled=true;document.getElementById('taskTg').classList.add('done');}
    tb.addEventListener('click',function(){
      window.open('https://t.me/gymclicker','_blank');
      var btn=this;setTimeout(function(){if(!localStorage.getItem('tg_task')){localStorage.setItem('tg_task','1');G.coins+=10000;G.allC+=10000;updateHUD();saveGame();showNotif('+10,000 бицушек!');btn.textContent='Выполнено';btn.disabled=true;document.getElementById('taskTg').classList.add('done');}},3000);
    });
  }

  // Crash
  document.getElementById('crashStartBtn').addEventListener('click',crashStart);
  document.getElementById('crashCashBtn').addEventListener('click',crashCash);
  document.getElementById('crashSetBtn').addEventListener('click',function(){var v=parseInt(document.getElementById('crashBetIn').value);if(v>0)setCrashBet(v);});
  document.getElementById('crashBetIn').addEventListener('keydown',function(e){if(e.key==='Enter'){var v=parseInt(this.value);if(v>0)setCrashBet(v);}});
  document.querySelectorAll('.cbb').forEach(function(btn){btn.addEventListener('click',function(){setCrashBet(this.dataset.bet);});});



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
                upsert_score(user_id, username, cph, data.get("skin", "default"))
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

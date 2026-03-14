"""
main.py — Качалка Кликер (полная перезапись)
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
    con.commit(); con.close()
    logger.info("[DB] Reset: %s", DB_PATH)

def upsert_score(user_id, username, cph, skin="default"):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO leaderboard (user_id, username, cph, skin, updated)
        VALUES (?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username, cph=excluded.cph,
            skin=excluded.skin, updated=excluded.updated
    """, (str(user_id), str(username)[:32], float(cph), str(skin)))
    con.commit(); con.close()

def get_top(n=20):
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT username, cph, skin FROM leaderboard ORDER BY cph DESC LIMIT ?", (n,)
    ).fetchall()
    con.close()
    return [{"username": r[0], "cph": r[1], "skin": r[2] or "default"} for r in rows]

# ─── HTML GAME ────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
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
html,body{height:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--tx);font-family:'Nunito',sans-serif;min-height:100vh}

/* ── HEADER ── */
#hdr{position:sticky;top:0;z-index:80;background:rgba(13,13,22,.97);
  border-bottom:1px solid rgba(255,215,0,.08);padding:10px 14px 8px;
  display:flex;align-items:center;gap:10px}
#profBtn{width:44px;height:44px;border-radius:50%;
  background:linear-gradient(135deg,var(--or),var(--gd));
  border:2px solid rgba(255,215,0,.3);font-size:22px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.hm{flex:1;text-align:center}
.hc{font-size:24px;font-weight:900;color:var(--gd);line-height:1}
.hl{font-size:10px;color:var(--mt)}
.hr{display:flex;flex-direction:column;align-items:flex-end}
.hcph{font-size:14px;font-weight:800;color:var(--gn)}
.hcphl{font-size:10px;color:var(--mt)}

/* ── XP BAR ── */
#xpbar{padding:5px 14px 8px;background:rgba(13,13,22,.7)}
.xrow{display:flex;justify-content:space-between;font-size:10px;color:var(--mt);margin-bottom:4px}
.xt{height:5px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden}
.xf{height:100%;background:linear-gradient(90deg,var(--or),var(--gd));border-radius:3px;transition:width .4s}

/* ── CHIPS ── */
#chips{display:flex;gap:6px;padding:8px 14px}
.chip{flex:1;background:var(--c1);border:1px solid rgba(255,215,0,.1);border-radius:10px;padding:7px 4px;text-align:center}
.chipv{font-size:13px;font-weight:900;color:var(--gd);line-height:1}
.chipl{font-size:9px;color:var(--mt);margin-top:2px}

/* ── PANELS ── */
.panel{display:none;padding:0 0 110px}
.panel.on{display:block}
.sec{font-size:9px;font-weight:900;letter-spacing:3px;color:rgba(255,200,0,.6);
  text-transform:uppercase;margin:14px 14px 8px;padding:5px 10px;
  border-radius:6px;background:rgba(255,200,0,.05);border:1px solid rgba(255,200,0,.1)}

/* ── CLICKER PANEL ── */
#panel-mine{padding-bottom:110px}
.nrg{width:100%;max-width:340px;margin:12px auto 14px;padding:0 14px}
.nrgt{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
.nrgl{color:var(--or);font-weight:800;letter-spacing:1px}
.nrgb{height:7px;background:rgba(255,255,255,.07);border-radius:4px;overflow:hidden;border:1px solid rgba(255,100,0,.15)}
.nrgf{height:100%;background:linear-gradient(90deg,#ff3c00,var(--or),#ffa500);border-radius:4px;transition:width .12s linear}
.coinwrap{position:relative;display:flex;align-items:center;justify-content:center;flex-direction:column;margin:4px 0 8px}
.glow{position:absolute;width:210px;height:210px;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,rgba(255,200,0,.18) 0%,transparent 70%);
  animation:glowPulse 2s ease-in-out infinite}
@keyframes glowPulse{0%,100%{transform:scale(1);opacity:.8}50%{transform:scale(1.12);opacity:1}}
.coin-scene{width:190px;height:190px;perspective:600px;cursor:pointer;
  user-select:none;-webkit-user-select:none;touch-action:none;position:relative;z-index:10}
.coin-3d{width:190px;height:190px;border-radius:50%;position:relative;
  transform-style:preserve-3d;transition:transform .05s ease-out;will-change:transform}
.coin-face,.coin-back{position:absolute;inset:0;border-radius:50%;
  display:flex;align-items:center;justify-content:center;backface-visibility:hidden}
.coin-face{
  background:radial-gradient(circle at 32% 28%,rgba(255,255,200,.9) 0%,rgba(255,220,50,.4) 20%,transparent 55%),
    conic-gradient(from 0deg,#c8860a,#ffd700,#f0b800,#e8a000,#ffc800,#d4900a,#ffd700,#c8860a);
  box-shadow:0 0 0 5px rgba(255,180,0,.35),0 0 40px rgba(255,160,0,.5),
    0 12px 40px rgba(0,0,0,.7),inset 0 2px 6px rgba(255,255,200,.6);
  font-size:88px;line-height:1}
.coin-back{background:conic-gradient(from 0deg,#a07000,#d4a010,#b88800,#c89800,#a07000);
  transform:rotateY(180deg);font-size:50px;line-height:1}
.coin-shadow{position:absolute;bottom:-16px;left:50%;transform:translateX(-50%);
  width:160px;height:20px;border-radius:50%;background:rgba(0,0,0,.4);filter:blur(8px)}
@keyframes tapBounce{
  0%{transform:scale(1)}15%{transform:scale(.82) translateY(6px)}
  50%{transform:scale(1.06)}100%{transform:scale(1)}}
.coin-3d.tapped{animation:tapBounce .35s cubic-bezier(.25,.46,.45,.94)}
.coin-3d.dead{filter:grayscale(.7) brightness(.5)}

/* ── FLOATING TEXT ── */
.ft{position:fixed;pointer-events:none;z-index:9999;font-size:26px;font-weight:900;
  color:#fff;text-shadow:0 0 8px rgba(255,200,0,1);
  animation:floatUp 1s ease-out forwards;white-space:nowrap}
.ft.crit{font-size:32px;text-shadow:0 0 10px rgba(255,80,0,1)}
@keyframes floatUp{
  0%{opacity:1;transform:translateY(0) scale(.85)}
  15%{opacity:1;transform:translateY(-8px) scale(1.2)}
  100%{opacity:0;transform:translateY(-100px) scale(.9)}}
.rp{position:fixed;pointer-events:none;z-index:9998;border-radius:50%;
  background:rgba(255,200,0,.25);animation:ripple .4s ease-out forwards}
@keyframes ripple{0%{transform:scale(0);opacity:.7}100%{transform:scale(3.5);opacity:0}}

/* ── BOTTOM NAV ── */
#bnav{position:fixed;bottom:12px;left:10px;right:10px;z-index:90;
  background:rgba(18,18,30,.96);border:1px solid rgba(255,215,0,.15);
  border-radius:20px;display:flex;padding:6px 4px;
  box-shadow:0 4px 24px rgba(0,0,0,.5)}
.bnb{flex:1;background:transparent;border:none;color:var(--mt);
  font-family:'Nunito',sans-serif;cursor:pointer;padding:8px 2px 6px;
  display:flex;flex-direction:column;align-items:center;gap:3px;
  transition:all .2s;border-radius:14px}
.bnb.on{color:var(--gd);background:rgba(255,215,0,.08)}
.bnb-i{font-size:20px;line-height:1}
.bnb-l{font-size:8px;font-weight:800;letter-spacing:.5px}

/* ── UPGRADE PANEL ── */
.ubtabs{display:flex;gap:8px;padding:12px 14px 4px}
.ubtab{flex:1;padding:12px;border-radius:12px;border:1.5px solid rgba(255,255,255,.08);
  background:var(--c1);color:var(--mt);font-family:'Nunito',sans-serif;
  font-size:13px;font-weight:800;cursor:pointer;transition:all .2s}
.ubtab.on{background:linear-gradient(135deg,rgba(255,100,0,.2),rgba(255,200,0,.1));
  border-color:rgba(255,215,0,.4);color:var(--gd)}
.ubpan{display:none;padding:0 14px}
.ubpan.on{display:block}
.upg{background:linear-gradient(160deg,rgba(30,28,52,1),rgba(18,18,32,1));
  border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:14px;
  display:flex;align-items:center;gap:12px;margin-bottom:10px;cursor:pointer;
  position:relative;overflow:hidden}
.upg.canBuy{border-color:rgba(255,200,0,.35);
  box-shadow:0 4px 20px rgba(255,150,0,.15)}
.upg.maxed{opacity:.45;cursor:default}
.upg.busy{border-color:rgba(255,100,0,.4)}
.uico{width:54px;height:54px;border-radius:12px;flex-shrink:0;font-size:26px;
  display:flex;align-items:center;justify-content:center;
  background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.12)}
.ubod{flex:1;min-width:0}
.unam{font-size:13px;font-weight:800;color:var(--tx);margin-bottom:2px}
.udsc{font-size:11px;color:var(--mt);line-height:1.3}
.ueff{font-size:11px;color:var(--bl);font-weight:700;margin-top:2px}
.ulvl{font-size:10px;color:var(--or);font-weight:700;margin-top:2px}
.utmr{font-size:10px;color:var(--or);font-weight:800;margin-top:3px}
.utmr.rdy{color:var(--gn)}
.uprg{position:absolute;bottom:0;left:0;height:3px;
  background:linear-gradient(90deg,var(--or),var(--gd));border-radius:0 0 0 14px}
.uprc{flex-shrink:0;text-align:right;min-width:58px}
.uprv{font-size:13px;font-weight:900;color:var(--gd)}
.uprv.no{color:var(--rd)}
.uprl{font-size:10px;color:var(--mt);margin-top:1px}

/* ── CRASH PANEL ── */
.crash-wrap{padding:10px 14px 0}
.crash-hdr{text-align:center;margin-bottom:12px}
.crash-title{font-size:28px;font-weight:900;color:var(--rd);text-shadow:0 0 20px rgba(255,34,68,.5)}
.crash-sub{font-size:11px;color:var(--mt);margin-top:3px}
.crash-screen{background:var(--c1);border:1px solid rgba(255,34,68,.2);
  border-radius:16px;padding:18px;text-align:center;margin-bottom:14px;
  min-height:130px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:8px}
.crash-mult{font-size:52px;font-weight:900;color:var(--gd);
  text-shadow:0 0 30px rgba(255,200,0,.6);line-height:1;transition:color .2s}
.crash-icon{font-size:38px;animation:coinBounce .6s ease-in-out infinite}
@keyframes coinBounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.crash-icon.idle{animation:none}
.crash-stat{font-size:12px;color:var(--mt);font-weight:700}
.crash-betw{background:var(--c1);border:1px solid rgba(255,215,0,.1);
  border-radius:14px;padding:14px;margin-bottom:12px}
.crash-betl{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);
  text-transform:uppercase;margin-bottom:8px}
.crash-betr{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px}
.cbb{flex:1;min-width:38px;padding:8px 4px;background:var(--c2);
  border:1px solid rgba(255,215,0,.12);border-radius:8px;color:var(--gd);
  font-family:'Nunito',sans-serif;font-size:11px;font-weight:800;cursor:pointer}
.cbb.sel{background:rgba(255,150,0,.15);border-color:rgba(255,215,0,.4)}
.crash-custr{display:flex;gap:8px;margin-bottom:10px}
.game-inp{flex:1;padding:9px 12px;border-radius:9px;
  border:1.5px solid rgba(255,215,0,.2);background:rgba(255,255,255,.06);
  color:var(--tx);font-family:'Nunito',sans-serif;font-size:14px;
  font-weight:700;outline:none}
.game-inp:focus{border-color:rgba(255,215,0,.5)}
.game-setb{padding:9px 14px;border-radius:9px;
  background:linear-gradient(135deg,var(--or),var(--gd));border:none;
  font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;color:#000;cursor:pointer}
.crash-betdisp{font-size:13px;font-weight:800;color:var(--gd);text-align:center}
.crash-btnr{display:flex;gap:10px;margin-bottom:14px}
.crash-startb,.crash-cashb{flex:1;padding:14px;border:none;border-radius:12px;
  font-family:'Nunito',sans-serif;font-size:14px;font-weight:900;cursor:pointer}
.crash-startb{background:linear-gradient(135deg,var(--or),var(--gd));color:#000}
.crash-cashb{background:linear-gradient(135deg,#00aa00,var(--gn));color:#000}
.crash-startb:disabled,.crash-cashb:disabled{opacity:.35;cursor:not-allowed}
.crash-hist-w{background:var(--c1);border:1px solid rgba(255,255,255,.05);
  border-radius:12px;padding:12px 14px}
.crash-histt{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);
  text-transform:uppercase;margin-bottom:8px}
.crash-histl{display:flex;flex-wrap:wrap;gap:5px}
.ch{padding:4px 9px;border-radius:20px;font-size:11px;font-weight:800}
.ch.w{background:rgba(57,255,20,.12);color:var(--gn);border:1px solid rgba(57,255,20,.25)}
.ch.l{background:rgba(255,34,68,.1);color:var(--rd);border:1px solid rgba(255,34,68,.2)}

/* ── SLOTS PANEL ── */
.slots-wrap{padding:10px 14px 0}
.slots-title{text-align:center;font-size:26px;font-weight:900;color:var(--gd);
  margin-bottom:2px;text-shadow:0 0 20px rgba(255,200,0,.5);letter-spacing:2px}
.slots-sub{text-align:center;font-size:11px;color:var(--mt);margin-bottom:14px}
.slots-machine{background:linear-gradient(160deg,rgba(30,28,52,1),rgba(18,18,32,1));
  border:2px solid rgba(255,215,0,.25);border-radius:20px;padding:18px 14px 14px;
  margin-bottom:12px}
.slots-reels{display:flex;gap:8px;justify-content:center;margin-bottom:12px}
.slot-reel{width:88px;height:96px;background:rgba(0,0,0,.55);
  border:2px solid rgba(255,215,0,.18);border-radius:14px;
  display:flex;align-items:center;justify-content:center;overflow:hidden;
  box-shadow:inset 0 2px 8px rgba(0,0,0,.7)}
.slot-sym{font-size:52px;line-height:1;transition:filter .06s}
.slot-reel.spinning .slot-sym{filter:blur(2.5px)}
.slot-reel.win-reel{border-color:rgba(57,255,20,.8)!important;
  box-shadow:0 0 18px rgba(57,255,20,.5),inset 0 2px 8px rgba(0,0,0,.6)!important;
  animation:reelWin .5s ease-in-out infinite}
@keyframes reelWin{0%,100%{box-shadow:0 0 10px rgba(57,255,20,.4)}
  50%{box-shadow:0 0 28px rgba(57,255,20,.9)}}
.slots-payline{height:2px;background:linear-gradient(90deg,transparent,rgba(255,215,0,.4),transparent);margin-bottom:14px}
.slots-result{text-align:center;min-height:36px;display:flex;
  align-items:center;justify-content:center;margin-bottom:2px}
.slots-res{font-size:14px;font-weight:900;animation:resAppear .3s ease-out}
@keyframes resAppear{from{opacity:0;transform:scale(.7)}to{opacity:1;transform:scale(1)}}
.slots-bet-w{background:rgba(0,0,0,.3);border-radius:12px;padding:12px;
  margin-bottom:10px;border:1px solid rgba(255,255,255,.05)}
.slots-bet-l{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);
  text-transform:uppercase;margin-bottom:8px}
.sbet-btns{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px}
.sbb2{flex:1;min-width:38px;padding:8px 4px;background:var(--c2);
  border:1px solid rgba(255,215,0,.12);border-radius:8px;color:var(--gd);
  font-family:'Nunito',sans-serif;font-size:11px;font-weight:800;cursor:pointer}
.sbb2.sel{background:rgba(255,150,0,.15);border-color:rgba(255,215,0,.4)}
.slots-bet-disp{font-size:13px;font-weight:800;color:var(--gd);text-align:center}
.slots-ctrl{display:flex;gap:8px;margin-bottom:12px}
.slots-spin-btn{flex:1;padding:16px;border:none;border-radius:12px;
  background:linear-gradient(135deg,var(--or),var(--gd));
  font-family:'Nunito',sans-serif;font-size:16px;font-weight:900;color:#000;
  cursor:pointer;box-shadow:0 4px 16px rgba(255,150,0,.3)}
.slots-spin-btn:disabled{opacity:.35;cursor:not-allowed;box-shadow:none}
.slots-vol{flex:0 0 auto;padding:14px 16px;border:1.5px solid rgba(255,255,255,.1);
  border-radius:12px;background:rgba(255,255,255,.05);color:var(--mt);
  font-size:18px;cursor:pointer;transition:all .2s}
.slots-vol.on{color:var(--gd);border-color:rgba(255,215,0,.3);background:rgba(255,215,0,.06)}
.slots-paytable{background:rgba(0,0,0,.25);border-radius:12px;padding:12px;
  border:1px solid rgba(255,255,255,.05)}
.slots-pay-t{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--mt);
  text-transform:uppercase;margin-bottom:10px}
.pay-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.pay-row{display:flex;align-items:center;gap:6px;padding:5px 8px;
  background:rgba(255,255,255,.03);border-radius:7px;border:1px solid rgba(255,255,255,.05)}
.pay-sym{font-size:18px;width:22px;text-align:center}
.pay-info{flex:1}
.pay-name{font-size:10px;color:var(--mt)}
.pay-mult{font-size:12px;font-weight:900;color:var(--gd)}
.pay-row.special{grid-column:1/-1;background:rgba(0,200,255,.04);border-color:rgba(0,200,255,.1)}
.pay-row.special .pay-mult{color:var(--bl)}

/* ── LEADERBOARD ── */
.lb-wrap{padding:10px 14px 0}
.lb-me{background:rgba(57,255,20,.06);border:1px solid rgba(57,255,20,.18);
  border-radius:12px;padding:12px 14px;margin-bottom:10px;
  display:flex;justify-content:space-between;align-items:center}
.lb-mel{font-size:11px;color:var(--gn);font-weight:800}
.lb-mev{font-size:16px;font-weight:900;color:var(--gd)}
.lb-ref{width:100%;padding:10px;border-radius:10px;
  border:1px solid rgba(255,100,0,.3);background:rgba(255,100,0,.08);
  color:var(--or);font-family:'Nunito',sans-serif;font-size:13px;font-weight:700;cursor:pointer;margin-bottom:10px}
.pod{text-align:center;padding:4px 0 16px}
.podt{font-size:10px;font-weight:800;letter-spacing:3px;color:var(--mt);margin-bottom:12px}
.pods{display:flex;align-items:flex-end;justify-content:center;gap:8px}
.podsl{display:flex;flex-direction:column;align-items:center;flex:1;max-width:110px}
.podc{font-size:18px;margin-bottom:2px;min-height:22px}
.podci{border-radius:50%;display:flex;align-items:center;justify-content:center;margin-bottom:5px}
.p1 .podci{width:78px;height:78px;font-size:42px;background:linear-gradient(135deg,#f5c518,#ffd700,#d4a010);box-shadow:0 0 20px rgba(255,200,0,.5)}
.p2 .podci{width:64px;height:64px;font-size:34px;background:linear-gradient(135deg,#bdbdbd,#e0e0e0,#9e9e9e)}
.p3 .podci{width:56px;height:56px;font-size:30px;background:linear-gradient(135deg,#bf7b3b,#d4924a,#9e5e1e)}
.podnm{font-size:11px;font-weight:800;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;width:100%;margin-bottom:2px}
.podcp{font-size:10px;color:var(--gd);font-weight:700}
.podbk{border-radius:9px 9px 0 0;width:100%;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:rgba(0,0,0,.35)}
.p1 .podbk{height:66px;background:linear-gradient(180deg,#c49a00,#a07800)}
.p2 .podbk{height:48px;background:linear-gradient(180deg,#8f8f8f,#6e6e6e)}
.p3 .podbk{height:36px;background:linear-gradient(180deg,#8f5a18,#6a3e0c)}
.poddiv{height:1px;background:rgba(255,255,255,.05);margin:8px 0 12px}
.lbrow{background:var(--c1);border:1px solid rgba(255,255,255,.05);
  border-radius:11px;padding:11px 14px;margin-bottom:6px;
  display:flex;align-items:center;gap:10px}
.lbrow.me{border-color:rgba(57,255,20,.35);background:rgba(57,255,20,.05)}
.lbrk{width:26px;text-align:center;font-size:13px;font-weight:900;color:var(--mt)}
.lbsk{font-size:20px}
.lbnm{flex:1;font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lbrow.me .lbnm{color:var(--gn)}
.lbcp{font-size:13px;font-weight:900;color:var(--gd)}
.lb-empty{text-align:center;padding:24px;color:var(--mt);font-size:13px}

/* ── EXTRA PANEL ── */
.extra-wrap{padding:10px 14px 0}
.task{background:var(--c1);border:1px solid rgba(255,215,0,.12);border-radius:14px;
  padding:14px;display:flex;align-items:center;gap:12px;margin-bottom:10px}
.task.done{opacity:.5;pointer-events:none}
.taskico{font-size:34px;flex-shrink:0}
.taskbod{flex:1;min-width:0}
.tasknam{font-size:13px;font-weight:800;margin-bottom:2px}
.taskdsc{font-size:11px;color:var(--mt);line-height:1.3}
.taskrew{font-size:11px;color:var(--gd);font-weight:700;margin-top:3px}
.taskbtn{flex-shrink:0;padding:9px 12px;border-radius:9px;
  background:linear-gradient(135deg,var(--or),var(--gd));border:none;
  font-family:'Nunito',sans-serif;font-size:12px;font-weight:900;color:#000;cursor:pointer}
.coin-soon{background:var(--c1);border:1px solid rgba(255,215,0,.12);border-radius:14px;
  padding:20px;text-align:center}
.coin-spin{font-size:70px;animation:spinY 2s linear infinite;display:inline-block;margin-bottom:10px}
@keyframes spinY{0%{transform:rotateY(0)}25%{transform:rotateY(90deg) scaleX(.1)}
  50%{transform:rotateY(180deg)}75%{transform:rotateY(270deg) scaleX(.1)}100%{transform:rotateY(360deg)}}
.soon-title{font-size:22px;font-weight:900;color:var(--gd);margin-bottom:4px}
.soon-desc{font-size:12px;color:var(--mt);line-height:1.6;margin-bottom:14px}
.soon-btn{display:inline-block;padding:12px 24px;border-radius:12px;
  background:linear-gradient(135deg,var(--or),var(--gd));color:#000;
  font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;text-decoration:none}

/* ── PROFILE DRAWER ── */
#ov{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,0);
  pointer-events:none;transition:background .3s}
#ov.on{background:rgba(0,0,0,.65);pointer-events:all}
#dr{position:fixed;top:0;left:-110%;width:88%;max-width:380px;height:100vh;
  z-index:201;background:var(--c2);border-right:1px solid rgba(255,215,0,.1);
  display:flex;flex-direction:column;transition:left .35s cubic-bezier(.25,.46,.45,.94)}
#dr.on{left:0}
.drh{padding:18px 16px 0;background:linear-gradient(180deg,rgba(255,100,0,.08),transparent);
  border-bottom:1px solid rgba(255,215,0,.08);flex-shrink:0}
.drhead{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.drava{width:60px;height:60px;border-radius:50%;
  background:linear-gradient(135deg,var(--or),var(--gd));
  display:flex;align-items:center;justify-content:center;font-size:30px;
  border:3px solid rgba(255,215,0,.4)}
.drname{font-size:18px;font-weight:900;color:var(--gd)}
.drsub{font-size:11px;color:var(--mt);margin-top:2px}
.drcl{width:32px;height:32px;border-radius:50%;background:rgba(255,255,255,.06);
  border:none;color:var(--mt);font-size:16px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;margin-left:auto}
.nick-row{display:flex;gap:8px;margin-bottom:14px}
.nick-inp{flex:1;padding:9px 12px;border-radius:9px;
  border:1.5px solid rgba(255,215,0,.18);background:rgba(255,255,255,.05);
  color:var(--tx);font-family:'Nunito',sans-serif;font-size:14px;
  font-weight:700;outline:none}
.nick-inp:focus{border-color:rgba(255,215,0,.45)}
.nick-btn{padding:9px 14px;border-radius:9px;
  background:linear-gradient(135deg,var(--or),var(--gd));border:none;
  font-family:'Nunito',sans-serif;font-size:13px;font-weight:900;color:#000;cursor:pointer}
.drtabs{display:flex;background:rgba(0,0,0,.25);flex-shrink:0}
.drtab{flex:1;padding:12px 6px;background:transparent;border:none;
  color:var(--mt);font-family:'Nunito',sans-serif;font-size:11px;
  font-weight:700;cursor:pointer;border-bottom:2px solid transparent}
.drtab.on{color:var(--gd);border-bottom-color:var(--gd)}
.drbody{flex:1;overflow-y:auto;padding:14px 16px 40px;scrollbar-width:none}
.drbody::-webkit-scrollbar{display:none}
.drp{display:none}.drp.on{display:block}
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px}
.sc{background:var(--c1);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:13px}
.scv{font-size:19px;font-weight:900;color:var(--gd)}
.scl{font-size:10px;color:var(--mt);margin-top:2px}
.reset-btn{width:100%;padding:11px;margin-top:12px;border:1px solid rgba(255,34,68,.35);
  border-radius:11px;background:rgba(255,34,68,.07);color:var(--rd);
  font-family:'Nunito',sans-serif;font-size:13px;font-weight:800;cursor:pointer}
.ach{background:var(--c1);border:1px solid rgba(255,255,255,.05);border-radius:14px;
  padding:13px;margin-bottom:9px;display:flex;align-items:center;gap:11px;opacity:.35}
.ach.on{opacity:1;border-color:rgba(255,215,0,.15);background:rgba(255,100,0,.04)}
.achi{font-size:28px;width:38px;text-align:center;flex-shrink:0}
.achb{flex:1;min-width:0}
.achn{font-size:13px;font-weight:800}
.achd{font-size:11px;color:var(--mt);margin-top:2px;line-height:1.3}
.achr{font-size:10px;color:var(--bl);font-weight:700;margin-top:4px}
.achbtn{background:linear-gradient(135deg,var(--or),var(--gd));border:none;
  border-radius:8px;padding:7px 11px;font-family:'Nunito',sans-serif;
  font-size:11px;font-weight:900;color:#000;cursor:pointer;flex-shrink:0}
.achgot{font-size:11px;color:var(--gn);font-weight:700;flex-shrink:0}
.skgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.sk{background:var(--c1);border:2px solid rgba(255,255,255,.07);border-radius:14px;
  padding:15px 10px;display:flex;flex-direction:column;align-items:center;
  gap:9px;cursor:pointer;position:relative}
.sk.canBuy{border-color:rgba(255,215,0,.25)}
.sk.owned{border-color:rgba(57,255,20,.25)}
.sk.equipped{border-color:rgba(57,255,20,.65);background:rgba(57,255,20,.05)}
.sk.locked{opacity:.5}
.sk.achLocked{opacity:.55;cursor:default}
.skprev{width:84px;height:84px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:48px}
.skn{font-size:12px;font-weight:800;text-align:center;color:var(--tx);line-height:1.3}
.skp{font-size:12px;font-weight:700;color:var(--gd);text-align:center}
.skp.no{color:var(--rd)}.skp.green{color:var(--gn)}.skp.blue{font-size:10px;color:var(--bl)}
.skbdg{position:absolute;top:5px;right:5px;font-size:9px;font-weight:800;
  padding:2px 6px;border-radius:20px}
.beq{background:rgba(57,255,20,.18);color:var(--gn)}
.bown{background:rgba(57,255,20,.1);color:var(--gn)}
.blk{background:rgba(255,255,255,.06);color:var(--mt)}
.bac{background:rgba(0,200,255,.12);color:var(--bl)}
.bgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.bgcard{background:var(--c1);border:2px solid rgba(255,255,255,.07);border-radius:14px;
  padding:14px 10px;display:flex;flex-direction:column;align-items:center;
  gap:8px;cursor:pointer;position:relative}
.bgcard.equipped{border-color:rgba(57,255,20,.6);background:rgba(57,255,20,.04)}
.bgcard.owned{border-color:rgba(57,255,20,.22)}
.bgcard.canBuy{border-color:rgba(255,215,0,.22)}
.bgcard.locked{opacity:.5}
.bgprev{width:80px;height:56px;border-radius:10px;border:1.5px solid rgba(255,255,255,.1)}
.bgname{font-size:12px;font-weight:800;color:var(--tx);text-align:center}
.bgprice{font-size:12px;font-weight:700;color:var(--gd);text-align:center}
.bgprice.no{color:var(--rd)}.bgprice.green{color:var(--gn)}

/* ── NICK POPUP ── */
#nickpop{position:fixed;inset:0;z-index:99999;display:none;
  align-items:center;justify-content:center;background:rgba(0,0,0,.92)}
#nickpop.on{display:flex}
.nmod{background:var(--c2);border:1px solid rgba(255,215,0,.25);border-radius:20px;
  padding:30px 24px 24px;text-align:center;width:88%;max-width:330px;
  animation:popIn .35s cubic-bezier(.175,.885,.32,1.275)}
@keyframes popIn{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
.nin{width:100%;padding:12px 14px;border-radius:10px;outline:none;
  background:rgba(255,255,255,.06);border:2px solid rgba(255,215,0,.18);
  color:var(--tx);font-family:'Nunito',sans-serif;font-size:16px;
  font-weight:700;text-align:center;margin-bottom:6px}
.nin:focus{border-color:rgba(255,215,0,.5)}
.nhint{font-size:11px;color:var(--rd);min-height:16px;margin-bottom:12px}
.nbtn{width:100%;padding:14px;border:none;border-radius:12px;
  background:linear-gradient(135deg,var(--or),var(--gd));
  font-family:'Nunito',sans-serif;font-size:15px;font-weight:900;color:#000;cursor:pointer}

/* ── OFFLINE POPUP ── */
#offpop{position:fixed;inset:0;z-index:99998;display:none;
  align-items:center;justify-content:center;background:rgba(0,0,0,.82)}
#offpop.on{display:flex}
.offmod{background:var(--c2);border:1px solid rgba(255,215,0,.28);border-radius:20px;
  padding:28px 24px;text-align:center;width:88%;max-width:320px;
  animation:popIn .35s cubic-bezier(.175,.885,.32,1.275)}
.offic{font-size:50px;margin-bottom:8px;animation:float 2s ease-in-out infinite}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.offbtn{width:100%;padding:14px;border:none;border-radius:12px;
  background:linear-gradient(135deg,var(--or),var(--gd));
  font-family:'Nunito',sans-serif;font-size:15px;font-weight:900;color:#000;cursor:pointer;margin-top:16px}

/* ── ACH POPUP ── */
#apop{position:fixed;bottom:-100px;left:50%;transform:translateX(-50%);
  background:var(--c2);border:1px solid rgba(255,215,0,.3);border-radius:14px;
  padding:12px 18px;display:flex;align-items:center;gap:10px;z-index:9999;
  transition:bottom .35s cubic-bezier(.175,.885,.32,1.275);min-width:260px}
#apop.on{bottom:90px}
#apopi{font-size:32px}
.apl{font-size:9px;color:var(--gd);letter-spacing:2px;font-weight:800}
.apn{font-size:13px;font-weight:900}
.apr{font-size:11px;color:var(--bl);margin-top:1px}

/* ── NOTIF ── */
#notif{position:fixed;top:64px;left:50%;transform:translateX(-50%) translateY(-12px);
  background:linear-gradient(135deg,var(--or),var(--gd));color:#000;
  font-weight:900;font-size:13px;padding:9px 20px;border-radius:30px;
  z-index:9999;opacity:0;pointer-events:none;transition:all .25s;white-space:nowrap}
#notif.on{opacity:1;transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>

<!-- HEADER -->
<div id="hdr">
  <button id="profBtn">&#x1F4AA;</button>
  <div class="hm">
    <div class="hc" id="hCoins">0</div>
    <div class="hl">&#x1F4AA; БИЦУШКИ</div>
  </div>
  <div class="hr">
    <div class="hcph" id="hCph">0/ч</div>
    <div class="hcphl">&#x1F4C8; В ЧАС</div>
  </div>
</div>

<!-- XP BAR -->
<div id="xpbar">
  <div class="xrow">
    <span style="color:var(--or);font-weight:800">&#x2B50; <span id="lvlName">Новичок</span> — Ур.<span id="lvlNum">1</span></span>
    <span id="xpTxt">0/100</span>
  </div>
  <div class="xt"><div class="xf" id="xpFill" style="width:0%"></div></div>
</div>

<!-- CHIPS -->
<div id="chips">
  <div class="chip"><div class="chipv" id="cCpc">+1</div><div class="chipl">за клик</div></div>
  <div class="chip"><div class="chipv" id="cCps">0</div><div class="chipl">пассив/с</div></div>
  <div class="chip"><div class="chipv" id="cCrit">0%</div><div class="chipl">крит</div></div>
  <div class="chip"><div class="chipv" id="cLuck">0%</div><div class="chipl">удача</div></div>
</div>

<!-- MINE PANEL -->
<div class="panel on" id="panel-mine">
  <div class="nrg">
    <div class="nrgt"><span class="nrgl">&#x26A1; ЭНЕРГИЯ</span><span id="nTxt">100/100</span></div>
    <div class="nrgb"><div class="nrgf" id="nFill" style="width:100%"></div></div>
  </div>
  <div class="coinwrap">
    <div class="glow" id="cglow"></div>
    <div class="coin-scene" id="coinScene">
      <div class="coin-3d" id="coin3d">
        <div class="coin-face" id="coinFace">&#x1F4AA;</div>
        <div class="coin-back">&#x1FA99;</div>
      </div>
      <div class="coin-shadow"></div>
    </div>
  </div>
</div>

<!-- UPGRADE PANEL -->
<div class="panel" id="panel-upgrade">
  <div class="ubtabs">
    <button class="ubtab on" data-u="hit">&#x1F44A; Удар</button>
    <button class="ubtab" data-u="income">&#x1F4B0; Доход</button>
  </div>
  <div class="ubpan on" id="ubpan-hit">
    <div class="sec">Сила удара</div><div id="listClick"></div>
    <div class="sec">Энергия</div><div id="listEnergy"></div>
    <div class="sec">Критический удар</div><div id="listCrit"></div>
    <div class="sec">Специальные</div><div id="listSpecial"></div>
  </div>
  <div class="ubpan" id="ubpan-income">
    <div class="sec">Инвестиции в страны</div><div id="listPassive"></div>
  </div>
</div>

<!-- CRASH PANEL -->
<div class="panel" id="panel-crash">
  <div class="crash-wrap">
    <div class="crash-hdr">
      <div class="crash-title">&#x1F4A5; CRASH</div>
      <div class="crash-sub">Забери до краша или потеряй всё</div>
    </div>
    <div class="crash-screen">
      <div class="crash-mult" id="crashMult">x1.00</div>
      <div class="crash-icon idle" id="crashIcon">&#x1F4AA;</div>
      <div class="crash-stat" id="crashStat">Сделай ставку и нажми НАЧАТЬ</div>
    </div>
    <div class="crash-betw">
      <div class="crash-betl">Ставка (&#x1F4AA; бицушки)</div>
      <div class="crash-betr" id="crashBetBtns">
        <button class="cbb" data-bet="100">100</button>
        <button class="cbb" data-bet="500">500</button>
        <button class="cbb" data-bet="1000">1K</button>
        <button class="cbb" data-bet="5000">5K</button>
        <button class="cbb" data-bet="10000">10K</button>
        <button class="cbb" data-bet="all">ВСЕ</button>
      </div>
      <div class="crash-custr">
        <input class="game-inp" id="crashBetIn" type="number" placeholder="Своя ставка..." min="1">
        <button class="game-setb" id="crashSetBtn">&#x2713;</button>
      </div>
      <div class="crash-betdisp" id="crashBetDisp">Ставка: 0 &#x1F4AA;</div>
    </div>
    <div class="crash-btnr">
      <button class="crash-startb" id="crashStartBtn">&#x1F680; НАЧАТЬ</button>
      <button class="crash-cashb" id="crashCashBtn" disabled>&#x1F4B0; ЗАБРАТЬ</button>
    </div>
    <div class="crash-hist-w">
      <div class="crash-histt">История</div>
      <div class="crash-histl" id="crashHistList"></div>
    </div>
  </div>
</div>

<!-- SLOTS PANEL -->
<div class="panel" id="panel-slots">
  <div class="slots-wrap">
    <div class="slots-title">&#x1F3B0; СЛОТЫ</div>
    <div class="slots-sub">Крути барабаны — выиграй бицушки!</div>
    <div class="slots-machine">
      <div class="slots-reels">
        <div class="slot-reel" id="reel0"><div class="slot-sym" id="sym0">&#x1F4AA;</div></div>
        <div class="slot-reel" id="reel1"><div class="slot-sym" id="sym1">&#x1F4AA;</div></div>
        <div class="slot-reel" id="reel2"><div class="slot-sym" id="sym2">&#x1F4AA;</div></div>
      </div>
      <div class="slots-payline"></div>
      <div class="slots-result" id="slotsRes">
        <div class="slots-res" style="color:var(--mt)">Нажми КРУТИТЬ!</div>
      </div>
    </div>
    <div class="slots-bet-w">
      <div class="slots-bet-l">Ставка (&#x1F4AA; бицушки)</div>
      <div class="sbet-btns" id="slotBetBtns">
        <button class="sbb2" data-sbet="100">100</button>
        <button class="sbb2" data-sbet="500">500</button>
        <button class="sbb2" data-sbet="1000">1K</button>
        <button class="sbb2" data-sbet="5000">5K</button>
        <button class="sbb2" data-sbet="10000">10K</button>
        <button class="sbb2" data-sbet="all">ВСЕ</button>
      </div>
      <div class="slots-bet-disp" id="slotBetDisp">Ставка: 0 &#x1F4AA;</div>
    </div>
    <div class="slots-ctrl">
      <button class="slots-spin-btn" id="spinBtn">&#x1F3B0; КРУТИТЬ!</button>
      <button class="slots-vol on" id="volBtn">&#x1F50A;</button>
    </div>
    <div class="slots-paytable">
      <div class="slots-pay-t">&#x1F4B0; Таблица выплат</div>
      <div class="pay-grid">
        <div class="pay-row"><div class="pay-sym">&#x1F3AF;</div><div class="pay-info"><div class="pay-name">Цель x3</div><div class="pay-mult">x50</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F525;</div><div class="pay-info"><div class="pay-name">Огонь x3</div><div class="pay-mult">x30</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F48E;</div><div class="pay-info"><div class="pay-name">Бриллиант x3</div><div class="pay-mult">x20</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F3C6;</div><div class="pay-info"><div class="pay-name">Трофей x3</div><div class="pay-mult">x10</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x26A1;</div><div class="pay-info"><div class="pay-name">Энергия x3</div><div class="pay-mult">x6</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F94A;</div><div class="pay-info"><div class="pay-name">Перчатки x3</div><div class="pay-mult">x5</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F3CB;</div><div class="pay-info"><div class="pay-name">Штанга x3</div><div class="pay-mult">x4</div></div></div>
        <div class="pay-row"><div class="pay-sym">&#x1F4AA;</div><div class="pay-info"><div class="pay-name">Бицепс x3</div><div class="pay-mult">x3</div></div></div>
        <div class="pay-row special"><div class="pay-sym">&#x2728;</div><div class="pay-info"><div class="pay-name">Любые 2 одинаковых</div><div class="pay-mult">x1.5</div></div></div>
      </div>
    </div>
  </div>
</div>

<!-- TOP PANEL -->
<div class="panel" id="panel-top">
  <div class="lb-wrap">
    <div class="lb-me">
      <span class="lb-mel">&#x1F4C8; МОЙ ДОХОД / ЧАС</span>
      <span class="lb-mev" id="lbMe">0</span>
    </div>
    <button class="lb-ref" id="lbRefBtn">&#x1F504; Обновить таблицу</button>
    <div id="lbPod"></div>
    <div id="lbList"></div>
  </div>
</div>

<!-- EXTRA PANEL -->
<div class="panel" id="panel-extra">
  <div class="extra-wrap">
    <div class="sec" style="margin-top:4px">Задания</div>
    <div class="task" id="taskTg">
      <div class="taskico">&#x1F4E2;</div>
      <div class="taskbod">
        <div class="tasknam">Подписаться на канал</div>
        <div class="taskdsc">Подпишись на официальный Telegram-канал GymClicker</div>
        <div class="taskrew">&#x1F4AA; Награда: 10,000 бицушек</div>
      </div>
      <button class="taskbtn" id="taskTgBtn">ПЕРЕЙТИ</button>
    </div>
    <div class="sec">COIN</div>
    <div class="coin-soon">
      <div class="coin-spin">&#x1FA99;</div>
      <div class="soon-title">GymCoin</div>
      <div class="soon-desc">Собственная монета GymClicker.<br>Следи за обновлениями в нашем канале!</div>
      <a class="soon-btn" href="https://t.me/gymclicker" target="_blank">&#x1F4E2; Канал</a>
    </div>
  </div>
</div>

<!-- BOTTOM NAV -->
<nav id="bnav">
  <button class="bnb on" data-t="mine"><span class="bnb-i">&#x1F4AA;</span><span class="bnb-l">ДОБЫЧА</span></button>
  <button class="bnb" data-t="upgrade"><span class="bnb-i">&#x2B06;&#xFE0F;</span><span class="bnb-l">ПРОКАЧКА</span></button>
  <button class="bnb" data-t="crash"><span class="bnb-i">&#x1F4A5;</span><span class="bnb-l">КРАШ</span></button>
  <button class="bnb" data-t="slots"><span class="bnb-i">&#x1F3B0;</span><span class="bnb-l">СЛОТЫ</span></button>
  <button class="bnb" data-t="top"><span class="bnb-i">&#x1F451;</span><span class="bnb-l">ТОП</span></button>
  <button class="bnb" data-t="extra"><span class="bnb-i">&#x2795;</span><span class="bnb-l">ДОП</span></button>
</nav>

<!-- NOTIF -->
<div id="notif"></div>

<!-- ACH POPUP -->
<div id="apop">
  <div id="apopi">&#x1F3C6;</div>
  <div>
    <div class="apl">ДОСТИЖЕНИЕ!</div>
    <div class="apn" id="apN">-</div>
    <div class="apr" id="apR"></div>
  </div>
</div>

<!-- OFFLINE POPUP -->
<div id="offpop">
  <div class="offmod">
    <div class="offic">&#x1F4A4;</div>
    <div style="font-size:15px;font-weight:900;margin-bottom:4px">Пока тебя не было...</div>
    <div style="font-size:12px;color:var(--mt);margin-bottom:12px" id="offT"></div>
    <div style="font-size:11px;color:var(--mt);letter-spacing:1px;margin-bottom:4px">КАЧАЛКА ЗАРАБОТАЛА:</div>
    <div style="font-size:38px;font-weight:900;color:var(--gd);line-height:1" id="offE">+0</div>
    <button class="offbtn" id="offBtn">ЗАБРАТЬ &#x1F4AA;</button>
  </div>
</div>

<!-- NICK POPUP -->
<div id="nickpop">
  <div class="nmod">
    <div style="font-size:54px;margin-bottom:10px">&#x1F4AA;</div>
    <div style="font-size:20px;font-weight:900;color:var(--gd);margin-bottom:4px">Добро пожаловать!</div>
    <div style="font-size:12px;color:var(--mt);margin-bottom:16px">Введи никнейм для таблицы лидеров</div>
    <input class="nin" id="nickIn" type="text" maxlength="20" placeholder="Твой никнейм..." autocomplete="off">
    <div class="nhint" id="nickHint"></div>
    <button class="nbtn" id="nickSaveBtn">В КАЧАЛКУ! &#x1F4AA;</button>
  </div>
</div>

<!-- OVERLAY + DRAWER -->
<div id="ov"></div>
<div id="dr">
  <div class="drh">
    <div class="drhead">
      <div class="drava" id="drAva">&#x1F4AA;</div>
      <div>
        <div class="drname" id="drName">Игрок</div>
        <div class="drsub">Ур.<span id="drLvl">1</span> &middot; <span id="drLvlN">Новичок</span></div>
      </div>
      <button class="drcl" id="drCloseBtn">&#x2715;</button>
    </div>
    <div class="nick-row">
      <input class="nick-inp" id="nickEdit" type="text" maxlength="20" placeholder="Изменить ник...">
      <button class="nick-btn" id="nickEditBtn">&#x2713;</button>
    </div>
  </div>
  <div class="drtabs">
    <button class="drtab on" data-p="stats">&#x1F4CA; Стат</button>
    <button class="drtab" data-p="achs">&#x1F3C6; Ачив</button>
    <button class="drtab" data-p="skins">&#x1F3A8; Скины</button>
    <button class="drtab" data-p="bgs">&#x1F5BC; Фон</button>
  </div>
  <div class="drbody">
    <div class="drp on" id="drp-stats">
      <div class="sgrid" style="margin-top:4px">
        <div class="sc"><div class="scv" id="stTC">0</div><div class="scl">Всего бицушек</div></div>
        <div class="sc"><div class="scv" id="stCL">0</div><div class="scl">Кликов</div></div>
        <div class="sc"><div class="scv" id="stPT">0м</div><div class="scl">Время игры</div></div>
        <div class="sc"><div class="scv" id="stMS">0</div><div class="scl">Макс /сек</div></div>
        <div class="sc"><div class="scv" id="stMC">+1</div><div class="scl">Макс за клик</div></div>
        <div class="sc"><div class="scv" id="stCR">0</div><div class="scl">Критов</div></div>
        <div class="sc"><div class="scv" id="stSW">0</div><div class="scl">Побед слотов</div></div>
        <div class="sc"><div class="scv" id="stAC">0/0</div><div class="scl">Достижений</div></div>
      </div>
      <button class="reset-btn" id="resetBtn">&#x1F5D1; Сбросить прогресс</button>
    </div>
    <div class="drp" id="drp-achs"><div id="achList"></div></div>
    <div class="drp" id="drp-skins"><div class="skgrid" id="skinList"></div></div>
    <div class="drp" id="drp-bgs"><div class="bgrid" id="bgList"></div></div>
  </div>
</div>

<script>
'use strict';

// ─── DATA ──────────────────────────────────────────────────────────────────
var LEVELS = [
  {n:'Новичок',x:0},{n:'Любитель',x:100},{n:'Спортсмен',x:300},
  {n:'Атлет',x:700},{n:'Культурист',x:1500},{n:'Чемпион',x:3500},
  {n:'Мастер',x:8000},{n:'Легенда',x:20000},{n:'Бог Железа',x:50000},
  {n:'АБСОЛЮТ',x:120000},{n:'Железный Кулак',x:200000},{n:'Стальная Воля',x:350000},
  {n:'Гранитный',x:550000},{n:'Титановый',x:850000},{n:'Алмазный',x:1300000},
  {n:'Платиновый',x:2000000},{n:'Космический',x:3000000},{n:'Галактический',x:4500000},
  {n:'Вселенский',x:7000000},{n:'Квантовый',x:10000000},{n:'Ультра',x:15000000},
  {n:'Мега',x:22000000},{n:'Гига',x:32000000},{n:'Тера',x:47000000},
  {n:'Пета',x:70000000},{n:'ЛЕГЕНДА ВСЕХ ВРЕМЁН',x:100000000},
  {n:'БОГ КАЧАЛКИ',x:150000000},{n:'СОЗДАТЕЛЬ',x:220000000},
  {n:'БЕСКОНЕЧНЫЙ',x:330000000}
];

var UPGRADES = {
  click:[
    {id:'c1',n:'Протеиновый шейк',i:'🥤',d:'Больше сил в руках',bp:25,pg:2.1,mx:20,ef:'cpc',v:1},
    {id:'c2',n:'Спортперчатки',i:'🥊',d:'Точный удар',bp:120,pg:2.2,mx:20,ef:'cpc',v:3},
    {id:'c3',n:'Предтрен',i:'⚡',d:'Взрывная сила',bp:600,pg:2.3,mx:20,ef:'cpc',v:10},
    {id:'c4',n:'Анаболики',i:'💉',d:'Сила зашкаливает',bp:4000,pg:2.4,mx:15,ef:'cpc',v:40},
    {id:'c5',n:'Режим зверя',i:'🦁',d:'Ты непобедим',bp:30000,pg:2.5,mx:12,ef:'cpc',v:200},
    {id:'c6',n:'Бог качалки',i:'🏛',d:'Запредельная мощь',bp:300000,pg:2.6,mx:10,ef:'cpc',v:1200},
    {id:'c7',n:'Квантовый удар',i:'⚛',d:'Разрушает пространство',bp:3000000,pg:2.7,mx:8,ef:'cpc',v:8000},
    {id:'c8',n:'Перчатки Титана',i:'🧤',d:'Сила запредельная',bp:25000000,pg:2.8,mx:6,ef:'cpc',v:60000}
  ],
  energy:[
    {id:'e1',n:'Расширенный запас',i:'🔋',d:'Больше максимальной энергии',bp:150,pg:2.2,mx:20,ef:'mxE',v:50},
    {id:'e2',n:'Быстрое восст.',i:'🔄',d:'+0.3 восст./сек за уровень',bp:400,pg:2.3,mx:20,ef:'rgE',v:0.3}
  ],
  crit:[
    {id:'cr1',n:'Меткость',i:'🎯',d:'Шанс крита +5%',bp:800,pg:2.3,mx:5,ef:'critC',v:5},
    {id:'cr2',n:'Снайпер',i:'🔭',d:'Шанс крита +10%',bp:25000,pg:2.5,mx:5,ef:'critC',v:10}
  ],
  special:[
    {id:'sp1',n:'Комбо-удар',i:'🎰',d:'Каждый 10-й клик даёт x10',bp:50000,pg:999,mx:1,ef:'combo',v:1},
    {id:'sp2',n:'Фортуна',i:'🍀',d:'15% шанс удвоить бицушки',bp:35000,pg:999,mx:1,ef:'luck',v:15}
  ],
  passive:[
    {id:'p1',n:'Россия',i:'🇷🇺',d:'Российские качалки',bp:50,pg:1.8,mx:20,ef:'cps',v:0.25},
    {id:'p2',n:'Исландия',i:'🇮🇸',d:'Залы Рейкьявика',bp:300,pg:1.9,mx:20,ef:'cps',v:1},
    {id:'p3',n:'США',i:'🇺🇸',d:'American Gym',bp:1500,pg:2.0,mx:20,ef:'cps',v:4},
    {id:'p4',n:'ОАЭ',i:'🇦🇪',d:'Люкс залы Дубая',bp:8000,pg:2.1,mx:20,ef:'cps',v:15},
    {id:'p5',n:'Япония',i:'🇯🇵',d:'Japanese Fit',bp:50000,pg:2.2,mx:18,ef:'cps',v:75},
    {id:'p6',n:'Германия',i:'🇩🇪',d:'Немецкая инженерия',bp:200000,pg:2.3,mx:16,ef:'cps',v:300},
    {id:'p7',n:'Великобритания',i:'🇬🇧',d:'Королевские залы',bp:800000,pg:2.3,mx:15,ef:'cps',v:1250},
    {id:'p8',n:'Китай',i:'🇨🇳',d:'Миллиард качающихся',bp:3000000,pg:2.4,mx:12,ef:'cps',v:5000},
    {id:'p9',n:'Бразилия',i:'🇧🇷',d:'Пляжные качалки Рио',bp:12000000,pg:2.4,mx:10,ef:'cps',v:20000},
    {id:'p10',n:'Весь мир',i:'🌍',d:'Залы на всех континентах',bp:50000000,pg:2.5,mx:8,ef:'cps',v:90000},
    {id:'p11',n:'МКС',i:'🚀',d:'В невесомости',bp:200000000,pg:2.5,mx:6,ef:'cps',v:400000},
    {id:'p12',n:'Луна',i:'🌙',d:'Первый зал на Луне',bp:800000000,pg:2.6,mx:5,ef:'cps',v:1750000},
    {id:'p13',n:'Марс',i:'🔴',d:'Красная планета',bp:3500000000,pg:2.7,mx:4,ef:'cps',v:8000000},
    {id:'p14',n:'Галактика',i:'🌌',d:'Галактические качалки',bp:20000000000,pg:2.8,mx:3,ef:'cps',v:60000000}
  ]
};

var ALL_UPG = [];
['click','energy','crit','special','passive'].forEach(function(k){
  ALL_UPG = ALL_UPG.concat(UPGRADES[k]);
});

var SKINS = [
  {id:'default',n:'Золотая Классика',e:'💪',p:0,ach:null,
    bg:'conic-gradient(from 0deg,#c8860a,#ffd700,#f0b800,#e8a000,#ffc800,#d4900a,#ffd700,#c8860a)',
    sh:'0 0 0 5px rgba(255,180,0,.35),0 0 40px rgba(255,160,0,.5)',gl:'rgba(255,200,0,.18)'},
  {id:'fire',n:'Огненный Атлет',e:'🔥',p:0,ach:'a14',
    bg:'linear-gradient(135deg,#ff4500,#ff6b00,#ff0000,#cc2200)',
    sh:'0 0 0 4px rgba(255,80,0,.4),0 0 35px rgba(255,60,0,.6)',gl:'rgba(255,80,0,.2)'},
  {id:'ice',n:'Ледяной Колосс',e:'❄',p:5000,ach:null,
    bg:'linear-gradient(135deg,#00c8ff,#0080cc,#004488)',
    sh:'0 0 0 4px rgba(0,180,255,.4),0 0 35px rgba(0,180,255,.5)',gl:'rgba(0,180,255,.18)'},
  {id:'toxic',n:'Токсичный',e:'☢',p:0,ach:'a5',
    bg:'linear-gradient(135deg,#39ff14,#22cc00,#009900)',
    sh:'0 0 0 4px rgba(57,255,20,.4),0 0 40px rgba(57,255,20,.6)',gl:'rgba(57,255,20,.2)'},
  {id:'galaxy',n:'Галактика',e:'🌌',p:25000,ach:null,
    bg:'linear-gradient(135deg,#6600cc,#9933ff,#3300aa)',
    sh:'0 0 0 4px rgba(180,0,255,.4),0 0 40px rgba(150,0,255,.6)',gl:'rgba(150,0,255,.2)'},
  {id:'diamond',n:'Бриллиант',e:'💎',p:0,ach:'a8',
    bg:'linear-gradient(135deg,#a8d8ff,#e0f4ff,#b8e8ff)',
    sh:'0 0 0 4px rgba(150,210,255,.5),0 0 50px rgba(100,200,255,.7)',gl:'rgba(150,220,255,.25)'},
  {id:'lava',n:'Магма',e:'🌋',p:0,ach:'a18',
    bg:'linear-gradient(135deg,#ff8c00,#cc2200,#ff4400)',
    sh:'0 0 0 4px rgba(255,100,0,.5),0 0 50px rgba(255,80,0,.7)',gl:'rgba(255,80,0,.25)'},
  {id:'rainbow',n:'Радуга',e:'🦄',p:0,ach:'a15',
    bg:'linear-gradient(135deg,#ff0080,#ff8c00,#ffed00,#00c800,#0080ff,#8000ff)',
    sh:'0 0 0 4px rgba(255,0,128,.4),0 0 50px rgba(128,0,255,.5)',gl:'rgba(200,0,200,.2)'},
  {id:'cyber',n:'Кибер',e:'🤖',p:0,ach:'a20',
    bg:'linear-gradient(135deg,#001a1a,#003333,#00ff88)',
    sh:'0 0 0 4px rgba(0,255,180,.4),0 0 50px rgba(0,255,150,.5)',gl:'rgba(0,255,150,.2)'},
  {id:'gold',n:'Золотой Царь',e:'👑',p:200000,ach:null,
    bg:'linear-gradient(135deg,#b8860b,#ffd700,#ffec8b,#b8860b)',
    sh:'0 0 0 4px rgba(255,215,0,.6),0 0 50px rgba(255,200,0,.8)',gl:'rgba(255,215,0,.3)'},
  {id:'neon',n:'Неон',e:'👾',p:120000,ach:null,
    bg:'linear-gradient(135deg,#000033,#003333,#00ffff)',
    sh:'0 0 0 4px rgba(0,255,255,.5),0 0 50px rgba(0,255,255,.6)',gl:'rgba(0,255,255,.2)'},
  {id:'ocean',n:'Океан',e:'🌊',p:60000,ach:null,
    bg:'linear-gradient(135deg,#003366,#0066cc,#0099ff)',
    sh:'0 0 0 4px rgba(0,100,200,.4),0 0 40px rgba(0,120,255,.5)',gl:'rgba(0,150,255,.2)'},
  {id:'matrix',n:'Матрица',e:'🟩',p:300000,ach:null,
    bg:'linear-gradient(135deg,#000800,#001a00,#003300)',
    sh:'0 0 0 4px rgba(0,255,0,.4),0 0 40px rgba(0,200,0,.6)',gl:'rgba(0,200,0,.2)'}
];

var BGS = [
  {id:'bg0',n:'Тёмный космос',p:0,css:'#0d0d16'},
  {id:'bg1',n:'Глубокий синий',p:10000,css:'linear-gradient(180deg,#0a0a2e,#0d0d40)'},
  {id:'bg2',n:'Огненный ад',p:10000,css:'linear-gradient(180deg,#1a0000,#2d0000)'},
  {id:'bg3',n:'Тёмный лес',p:10000,css:'linear-gradient(180deg,#001a00,#002800)'},
  {id:'bg4',n:'Фиолетовый туман',p:10000,css:'linear-gradient(180deg,#0d0020,#1a0035)'},
  {id:'bg5',n:'Золотые тени',p:10000,css:'linear-gradient(180deg,#1a1200,#2d2000)'},
  {id:'bg6',n:'Ледяная пещера',p:10000,css:'linear-gradient(180deg,#001a2d,#00263d)'},
  {id:'bg7',n:'Матрица',p:10000,css:'linear-gradient(180deg,#000d00,#001800)'}
];

var ACHS = [
  {id:'a1',i:'👆',n:'Первый клик',d:'Нажми на монету',c:function(s){return s.clicks>=1;},r:{t:'c',v:10}},
  {id:'a2',i:'💪',n:'100 кликов',d:'Сделай 100 кликов',c:function(s){return s.clicks>=100;},r:{t:'c',v:200}},
  {id:'a3',i:'🔥',n:'1000 кликов',d:'Сделай 1000 кликов',c:function(s){return s.clicks>=1000;},r:{t:'c',v:2000}},
  {id:'a4',i:'💥',n:'10K кликов',d:'Машина для кликов!',c:function(s){return s.clicks>=10000;},r:{t:'c',v:20000}},
  {id:'a5',i:'🦾',n:'100K кликов',d:'Ты кликер-легенда',c:function(s){return s.clicks>=100000;},r:{t:'s',v:'toxic'}},
  {id:'a6',i:'💰',n:'100 бицушек',d:'Накопи 100 бицушек',c:function(s){return s.allC>=100;},r:{t:'c',v:50}},
  {id:'a7',i:'💎',n:'10K бицушек',d:'Накопи 10K бицушек',c:function(s){return s.allC>=10000;},r:{t:'c',v:5000}},
  {id:'a8',i:'🏦',n:'1M бицушек',d:'Миллионер!',c:function(s){return s.allC>=1000000;},r:{t:'s',v:'diamond'}},
  {id:'a9',i:'⬆',n:'Первый апгрейд',d:'Купи улучшение',c:function(s){return s.allU>=1;},r:{t:'c',v:100}},
  {id:'a10',i:'🛒',n:'25 апгрейдов',d:'Инвестор!',c:function(s){return s.allU>=25;},r:{t:'c',v:25000}},
  {id:'a11',i:'😴',n:'Пассивный доход',d:'1 бицушка/сек',c:function(s){return s.cps>=1;},r:{t:'c',v:500}},
  {id:'a12',i:'⭐',n:'Стахановец',d:'100 бицушек/сек',c:function(s){return s.cps>=100;},r:{t:'s',v:'galaxy'}},
  {id:'a13',i:'🏅',n:'Уровень 5',d:'Достигни 5-го уровня',c:function(s){return s.lvl>=5;},r:{t:'c',v:10000}},
  {id:'a14',i:'🥇',n:'Уровень 10',d:'Достигни 10-го уровня',c:function(s){return s.lvl>=10;},r:{t:'s',v:'fire'}},
  {id:'a15',i:'👑',n:'Уровень 20',d:'Достигни 20-го уровня',c:function(s){return s.lvl>=20;},r:{t:'s',v:'rainbow'}},
  {id:'a16',i:'🎯',n:'Критикан',d:'100 критических ударов',c:function(s){return s.crits>=100;},r:{t:'c',v:15000}},
  {id:'a17',i:'🎰',n:'Комбо-мастер',d:'Комбо 10 раз',c:function(s){return s.combos>=10;},r:{t:'c',v:30000}},
  {id:'a18',i:'💸',n:'Крэш-победитель',d:'Выиграй 5 раз в Crash',c:function(s){return (s.crashWins||0)>=5;},r:{t:'s',v:'lava'}},
  {id:'a19',i:'🎰',n:'Удачливый',d:'Выиграй 10 раз в Слотах',c:function(s){return (s.slotWins||0)>=10;},r:{t:'c',v:50000}},
  {id:'a20',i:'♾',n:'Бесконечный',d:'Достигни уровня 29',c:function(s){return s.lvl>=29;},r:{t:'s',v:'cyber'}}
];

// ─── STATE ─────────────────────────────────────────────────────────────────
var SK = 'gym_v1';
var DEF = {
  coins:0,allC:0,clicks:0,allU:0,crits:0,combos:0,
  crashWins:0,slotWins:0,lvl:1,xp:0,nrg:100,mxE:100,rgE:2,
  cpc:1,cps:0,critC:0,critM:2,luck:0,combo:0,
  pt:0,mxCps:0,mxCpc:1,comboN:0,
  ul:{},achs:[],claimed:[],
  sk:['default'],skin:'default',bg:'bg0',bgs:['bg0'],lastSeen:null
};
var G = {};
var TIMERS = {};

function loadGame() {
  try {
    var s = localStorage.getItem(SK);
    G = Object.assign({}, DEF, s ? JSON.parse(s) : {});
  } catch(e) { G = Object.assign({}, DEF); }
  try {
    var t = localStorage.getItem(SK+'_t');
    if(t) {
      var td = JSON.parse(t);
      Object.keys(td).forEach(function(k){ if(!td[k].done) TIMERS[k] = td[k]; });
    }
  } catch(e) {}
}
function saveGame() {
  G.lastSeen = Date.now();
  try { localStorage.setItem(SK, JSON.stringify(G)); } catch(e) {}
  try { localStorage.setItem(SK+'_t', JSON.stringify(TIMERS)); } catch(e) {}
}

function fmt(n) {
  n = Math.floor(n);
  if(n >= 1e15) return (n/1e15).toFixed(1)+'Q';
  if(n >= 1e12) return (n/1e12).toFixed(1)+'T';
  if(n >= 1e9)  return (n/1e9).toFixed(1)+'B';
  if(n >= 1e6)  return (n/1e6).toFixed(1)+'M';
  if(n >= 1e3)  return (n/1e3).toFixed(1)+'K';
  return String(n);
}
function fmtTime(s) {
  if(s<=0) return '0с';
  if(s<60) return s+'с';
  var m=Math.floor(s/60), r=s%60;
  return m+'м'+(r?' '+r+'с':'');
}
function uLvl(id) { return G.ul[id] || 0; }
function uPrice(u) { return Math.floor(u.bp * Math.pow(u.pg, uLvl(u.id))); }

// ─── RECALC ────────────────────────────────────────────────────────────────
function recalc() {
  var cpc=1,cps=0,mxE=100,rgE=2,critC=0,luck=0,combo=0;
  for(var i=0;i<ALL_UPG.length;i++) {
    var u=ALL_UPG[i]; var l=uLvl(u.id); if(!l) continue;
    var tot=0;
    for(var lv=0;lv<l;lv++) tot += u.v * Math.pow(1.10, lv);
    tot = parseFloat(tot.toFixed(4));
    if(u.ef==='cpc') cpc += tot;
    else if(u.ef==='cps') cps += tot;
    else if(u.ef==='mxE') mxE += tot;
    else if(u.ef==='rgE') rgE += tot;
    else if(u.ef==='critC') critC += tot;
    else if(u.ef==='luck') luck += tot;
    else if(u.ef==='combo') combo = Math.min(1, combo+tot);
  }
  G.cpc = Math.max(1, Math.floor(cpc));
  G.cps = parseFloat(cps.toFixed(2));
  G.mxE = Math.floor(mxE);
  G.rgE = parseFloat(rgE.toFixed(2));
  G.critC = Math.min(critC, 80);
  G.luck = Math.min(luck, 80);
  G.combo = combo;
  if(G.nrg > G.mxE) G.nrg = G.mxE;
  if(G.cps > G.mxCps) G.mxCps = G.cps;
  if(G.cpc > G.mxCpc) G.mxCpc = G.cpc;
}

// ─── LEVEL / ACH ───────────────────────────────────────────────────────────
function checkLevel() {
  while(G.lvl < LEVELS.length) {
    var nx = LEVELS[G.lvl];
    if(!nx || G.xp < nx.x) break;
    G.lvl++;
    showNotif('🎉 Уровень '+G.lvl+' — '+LEVELS[G.lvl-1].n);
  }
}
function checkAchs() {
  var snap = {clicks:G.clicks,allC:G.allC,allU:G.allU,cps:G.cps,
    lvl:G.lvl,crits:G.crits,combos:G.combos,
    crashWins:G.crashWins||0,slotWins:G.slotWins||0,sk:G.sk};
  for(var i=0;i<ACHS.length;i++) {
    var a = ACHS[i];
    if(G.achs.indexOf(a.id)>=0) continue;
    if(!a.c(snap)) continue;
    G.achs.push(a.id);
    if(a.r.t==='s' && G.sk.indexOf(a.r.v)<0) { G.sk.push(a.r.v); G.claimed.push(a.id); }
    showAchPopup(a);
  }
}
function claimReward(id) {
  if(G.claimed.indexOf(id)>=0) return;
  var a = null;
  for(var i=0;i<ACHS.length;i++) { if(ACHS[i].id===id){a=ACHS[i];break;} }
  if(!a || G.achs.indexOf(id)<0) return;
  G.claimed.push(id);
  if(a.r.t==='c') { G.coins+=a.r.v; G.allC+=a.r.v; updateHUD(); showNotif('+'+fmt(a.r.v)+' бицушек!'); }
  else if(a.r.t==='s' && G.sk.indexOf(a.r.v)<0) { G.sk.push(a.r.v); showNotif('Скин разблокирован!'); }
  saveGame(); renderAchs();
}

// ─── BUY UPGRADE ───────────────────────────────────────────────────────────
function buyUpg(id) {
  var u = null;
  for(var i=0;i<ALL_UPG.length;i++) { if(ALL_UPG[i].id===id){u=ALL_UPG[i];break;} }
  if(!u) return;
  if(TIMERS[id] && !TIMERS[id].done) {
    var rem = Math.ceil((TIMERS[id].end - Date.now())/1000);
    if(rem>0) { showNotif('Прокачка: '+fmtTime(rem)); return; }
  }
  var l = uLvl(id);
  if(l >= u.mx) return;
  var p = uPrice(u);
  if(G.coins < p) { showNotif('Недостаточно бицушек!'); return; }
  G.coins -= p; G.allU++;
  var dur = l<5 ? 30+Math.floor(Math.random()*270) : l<15 ? 300+Math.floor(Math.random()*600) : 900+Math.floor(Math.random()*900);
  TIMERS[id] = {end: Date.now()+dur*1000, total:dur, done:false};
  updateHUD(); renderUpgrades();
  showNotif(u.n+' — прокачка '+fmtTime(dur)+'...');
}

// ─── CLICK ─────────────────────────────────────────────────────────────────
function doClick(x, y) {
  if(G.nrg < 1) { showNotif('Нет энергии!'); return; }
  G.nrg = Math.max(0, G.nrg-1);
  var earn = G.cpc, isCrit = false;
  if(G.combo > 0) {
    G.comboN = (G.comboN||0)+1;
    if(G.comboN >= 10) {
      earn *= 10; G.comboN = 0; G.combos = (G.combos||0)+1;
      spawnFlt('КОМБО x10!', x, y-30, '#ffaa00');
    }
  }
  if(G.critC>0 && Math.random()*100 < G.critC) {
    earn = Math.floor(earn * G.critM); isCrit = true; G.crits++;
  }
  if(G.luck>0 && Math.random()*100 < G.luck) {
    earn *= 2; spawnFlt('УДАЧА x2!', x, y-40, '#00c8ff');
  }
  earn = Math.floor(earn);
  G.coins += earn; G.allC += earn; G.clicks++; G.xp += 1;
  checkLevel(); checkAchs();
  spawnFlt((isCrit?'x':'+')+fmt(earn), x, y, isCrit ? '#ff5500' : null);
  spawnRipple(x, y);
  playSound('click');
  updateHUD();
}

// ─── SKIN / BG ─────────────────────────────────────────────────────────────
function getSkin(id) { for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===id)return SKINS[i];} return SKINS[0]; }
function getBg(id)   { for(var i=0;i<BGS.length;i++){if(BGS[i].id===id)return BGS[i];} return BGS[0]; }
function getSkinEmoji(id) { return getSkin(id).e; }

function applySkin(id) {
  var s = getSkin(id);
  var face = document.getElementById('coinFace');
  if(face) { face.style.background=s.bg; face.style.boxShadow=s.sh; face.innerHTML=s.e; }
  var gl = document.getElementById('cglow');
  if(gl) gl.style.background='radial-gradient(circle,'+s.gl+' 0%,transparent 70%)';
  var pb = document.getElementById('profBtn'); if(pb) pb.innerHTML=s.e;
  var da = document.getElementById('drAva');  if(da) da.innerHTML=s.e;
}
function applyBg(id) {
  var bg = getBg(id);
  document.body.style.background = bg.css;
}
function tapSkin(id) {
  var s = getSkin(id);
  if(s.ach && G.sk.indexOf(id)<0) { showNotif('Нужно достижение!'); return; }
  if(G.sk.indexOf(id)>=0) {
    G.skin = id; applySkin(id); saveGame(); renderSkins(); showNotif('Скин надет!');
  } else {
    if(G.coins < s.p) { showNotif('Недостаточно бицушек!'); return; }
    G.coins -= s.p; G.sk.push(id); G.skin=id; applySkin(id);
    saveGame(); updateHUD(); renderSkins(); showNotif('Скин куплен!');
  }
}
function tapBg(id) {
  var bg = getBg(id);
  if(G.bgs.indexOf(id)>=0) {
    applyBg(id); saveGame(); renderBgs(); showNotif('Фон применён!');
  } else {
    if(G.coins < bg.p) { showNotif('Недостаточно бицушек!'); return; }
    G.coins -= bg.p; G.bgs.push(id); applyBg(id);
    saveGame(); updateHUD(); renderBgs(); showNotif('Фон куплен!');
  }
}

// ─── HUD ───────────────────────────────────────────────────────────────────
function updateHUD() {
  var ci = G.lvl-1;
  var cx = LEVELS[ci] ? LEVELS[ci].x : 0;
  var nx = LEVELS[G.lvl] ? LEVELS[G.lvl].x : cx+1000000;
  var pct = nx>cx ? Math.min(100,(G.xp-cx)/(nx-cx)*100) : 100;
  document.getElementById('hCoins').textContent = fmt(G.coins);
  document.getElementById('hCph').textContent   = fmt(G.cps*3600)+'/ч';
  document.getElementById('cCpc').textContent   = '+'+fmt(G.cpc);
  document.getElementById('cCps').textContent   = fmt(G.cps);
  document.getElementById('cCrit').textContent  = Math.round(G.critC)+'%';
  document.getElementById('cLuck').textContent  = Math.round(G.luck)+'%';
  document.getElementById('nTxt').textContent   = Math.floor(G.nrg)+'/'+G.mxE;
  document.getElementById('nFill').style.width  = (G.nrg/G.mxE*100)+'%';
  document.getElementById('xpFill').style.width = pct+'%';
  document.getElementById('xpTxt').textContent  = fmt(G.xp-cx)+'/'+fmt(nx-cx);
  document.getElementById('lvlNum').textContent = G.lvl;
  document.getElementById('lvlName').textContent= LEVELS[ci]?LEVELS[ci].n:'MAX';
  document.getElementById('lbMe').textContent   = fmt(G.cps*3600)+'/ч';
  var coin3d = document.getElementById('coin3d');
  if(coin3d) coin3d.classList.toggle('dead', G.nrg<1);
  // Drawer stats
  var nick = getNick()||'Игрок';
  var el;
  el=document.getElementById('drName'); if(el) el.textContent=nick;
  el=document.getElementById('drLvl');  if(el) el.textContent=G.lvl;
  el=document.getElementById('drLvlN'); if(el) el.textContent=LEVELS[ci]?LEVELS[ci].n:'MAX';
  el=document.getElementById('stTC');   if(el) el.textContent=fmt(G.allC);
  el=document.getElementById('stCL');   if(el) el.textContent=fmt(G.clicks);
  var m=Math.floor(G.pt/60),h=Math.floor(m/60);
  el=document.getElementById('stPT');   if(el) el.textContent=h>0?h+'ч':m+'м';
  el=document.getElementById('stMS');   if(el) el.textContent=fmt(G.mxCps);
  el=document.getElementById('stMC');   if(el) el.textContent='+'+fmt(G.mxCpc);
  el=document.getElementById('stCR');   if(el) el.textContent=fmt(G.crits||0);
  el=document.getElementById('stSW');   if(el) el.textContent=fmt(G.slotWins||0);
  el=document.getElementById('stAC');   if(el) el.textContent=G.achs.length+'/'+ACHS.length;
}

// ─── RENDER UPGRADES ───────────────────────────────────────────────────────
function effLabel(u) {
  var v = parseFloat((u.v * Math.pow(1.10, uLvl(u.id))).toFixed(4));
  if(u.ef==='cpc') return '+'+fmt(v)+' 💪 за клик';
  if(u.ef==='cps') return '+'+fmt(v)+'/сек (+'+fmt(Math.round(v*3600))+'/ч)';
  if(u.ef==='mxE') return '+'+fmt(v)+' энергии';
  if(u.ef==='rgE') return '+'+v.toFixed(1)+' восст./сек';
  if(u.ef==='critC') return '+'+v+'% шанс крита';
  if(u.ef==='luck') return '+'+v+'% удвоить';
  if(u.ef==='combo') return 'каждый 10-й клик x10';
  return '';
}
function renderList(elId, list) {
  var el = document.getElementById(elId); if(!el) return;
  var rows = [];
  for(var i=0;i<list.length;i++) {
    var u=list[i]; var l=uLvl(u.id); var mx=(l>=u.mx);
    var tmr = TIMERS[u.id];
    var cls, priceH, timerH='', progH='';
    if(tmr && !tmr.done) {
      var rem = Math.max(0, Math.ceil((tmr.end-Date.now())/1000));
      var pct = Math.min(100, Math.round((1-(tmr.end-Date.now())/(tmr.total*1000))*100));
      if(pct<0) pct=0;
      if(rem<=0) {
        cls='upg canBuy'; priceH='<div class="uprv" style="color:var(--gn)">ГОТОВО!</div>';
        timerH='<div class="utmr rdy">✅ Нажми получить</div>';
      } else {
        cls='upg busy'; priceH='<div class="uprv" style="color:var(--or)">'+fmtTime(rem)+'</div>';
        timerH='<div class="utmr">⏳ '+fmtTime(rem)+'</div>';
        progH='<div class="uprg" style="width:'+pct+'%"></div>';
      }
    } else {
      var p=uPrice(u); var ok=!mx&&G.coins>=p;
      cls='upg'+(mx?' maxed':ok?' canBuy':'');
      priceH = mx ? '<div class="uprv" style="color:var(--gn)">МАКС</div>'
        : '<div class="uprv'+(ok?'':' no')+'">'+fmt(p)+'</div><div class="uprl">💪</div>';
    }
    rows.push('<div class="'+cls+'" data-uid="'+u.id+'">'
      +'<div class="uico">'+u.i+'</div>'
      +'<div class="ubod"><div class="unam">'+u.n+'</div>'
      +'<div class="udsc">'+u.d+'</div>'
      +'<div class="ueff">'+effLabel(u)+'</div>'
      +'<div class="ulvl">Ур. '+l+' / '+u.mx+'</div>'
      +timerH+'</div>'
      +'<div class="uprc">'+priceH+'</div>'
      +progH+'</div>');
  }
  el.innerHTML = rows.join('');
}
function renderUpgrades() {
  renderList('listClick',   UPGRADES.click);
  renderList('listEnergy',  UPGRADES.energy);
  renderList('listCrit',    UPGRADES.crit);
  renderList('listSpecial', UPGRADES.special);
  renderList('listPassive', UPGRADES.passive);
}

// ─── RENDER PROFILE ────────────────────────────────────────────────────────
function renderAchs() {
  var el = document.getElementById('achList'); if(!el) return;
  var canClaim = ACHS.filter(function(a){
    return G.achs.indexOf(a.id)>=0 && G.claimed.indexOf(a.id)<0;
  }).length;
  var rows = ['<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">'
    +'<div style="flex:1;font-size:11px;color:var(--mt)">'+G.achs.length+'/'+ACHS.length+' выполнено</div>'
    +(canClaim>0?'<button onclick="claimAll()" style="padding:7px 12px;border-radius:8px;background:linear-gradient(135deg,var(--or),var(--gd));border:none;font-family:Nunito,sans-serif;font-size:11px;font-weight:900;color:#000;cursor:pointer">ЗАБРАТЬ ВСЕ ('+canClaim+')</button>':'')
    +'</div>'];
  for(var i=0;i<ACHS.length;i++) {
    var a=ACHS[i]; var done=G.achs.indexOf(a.id)>=0; var cl=G.claimed.indexOf(a.id)>=0;
    var rv = a.r.t==='c' ? fmt(a.r.v)+' 💪' : '';
    if(a.r.t==='s') { for(var j=0;j<SKINS.length;j++){if(SKINS[j].id===a.r.v){rv='🎨 '+SKINS[j].n;break;}} }
    var btn = '';
    if(done && !cl) btn='<button class="achbtn" data-aid="'+a.id+'">ЗАБРАТЬ</button>';
    else if(done && cl) btn='<div class="achgot">✓</div>';
    rows.push('<div class="ach'+(done?' on':'')+'">'
      +'<div class="achi">'+a.i+'</div>'
      +'<div class="achb"><div class="achn">'+a.n+'</div>'
      +'<div class="achd">'+(done?a.d:'???')+'</div>'
      +'<div class="achr">'+rv+'</div></div>'
      +(done?'<div>'+btn+'</div>':'')+'</div>');
  }
  el.innerHTML = rows.join('');
}
function claimAll() {
  var coins=0, count=0;
  for(var i=0;i<ACHS.length;i++) {
    var a=ACHS[i];
    if(G.achs.indexOf(a.id)>=0 && G.claimed.indexOf(a.id)<0) {
      G.claimed.push(a.id);
      if(a.r.t==='c') { coins+=a.r.v; G.coins+=a.r.v; G.allC+=a.r.v; count++; }
      else if(a.r.t==='s' && G.sk.indexOf(a.r.v)<0) { G.sk.push(a.r.v); count++; }
    }
  }
  if(count>0){ updateHUD(); saveGame(); renderAchs(); renderSkins(); showNotif('+'+fmt(coins)+' 💪'); }
  else showNotif('Нет новых наград');
}
function renderSkins() {
  var el = document.getElementById('skinList'); if(!el) return;
  var rows = [];
  for(var i=0;i<SKINS.length;i++) {
    var s=SKINS[i]; var own=G.sk.indexOf(s.id)>=0; var eq=G.skin===s.id;
    var alck=s.ach&&!own; var ok=!own&&!alck&&G.coins>=s.p;
    var badge = eq?'<span class="skbdg beq">✓ НАДЕТ</span>'
      :own?'<span class="skbdg bown">КУПЛЕН</span>'
      :alck?'<span class="skbdg bac">АЧИВ</span>'
      :s.p>0?'<span class="skbdg blk">🔒</span>':'';
    var price = s.p===0&&!alck?'<div class="skp green">БЕСПЛАТНО</div>'
      :alck?'<div class="skp blue">Через достижение</div>'
      :own?(eq?'<div class="skp green">НАДЕТ</div>':'<div class="skp" style="color:var(--or)">НАДЕТЬ</div>')
      :'<div class="skp'+(ok?'':' no')+'">'+fmt(s.p)+' 💪</div>';
    var cls = 'sk'+(eq?' equipped':own?' owned':alck?' achLocked':ok?' canBuy':' locked');
    rows.push('<div class="'+cls+'" data-sid="'+s.id+'">'+badge
      +'<div class="skprev" style="background:'+s.bg+';box-shadow:'+s.sh+'">'+s.e+'</div>'
      +'<div class="skn">'+s.n+'</div>'+price+'</div>');
  }
  el.innerHTML = rows.join('');
}
function renderBgs() {
  var el = document.getElementById('bgList'); if(!el) return;
  var rows = [];
  for(var i=0;i<BGS.length;i++) {
    var bg=BGS[i]; var own=G.bgs.indexOf(bg.id)>=0; var eq=G.bg===bg.id; var ok=!own&&G.coins>=bg.p;
    var badge = eq?'<span class="skbdg beq">✓</span>':own?'<span class="skbdg bown">куплен</span>':'';
    var price = bg.p===0?'<div class="bgprice green">БЕСПЛАТНО</div>'
      :own?(eq?'<div class="bgprice green">АКТИВЕН</div>':'<div class="bgprice" style="color:var(--or)">ПРИМЕНИТЬ</div>')
      :'<div class="bgprice'+(ok?'':' no')+'">'+fmt(bg.p)+' 💪</div>';
    var cls='bgcard'+(eq?' equipped':own?' owned':ok?' canBuy':' locked');
    rows.push('<div class="'+cls+'" data-bgid="'+bg.id+'">'+badge
      +'<div class="bgprev" style="background:'+bg.css+'"></div>'
      +'<div class="bgname">'+bg.n+'</div>'+price+'</div>');
  }
  el.innerHTML = rows.join('');
}

// ─── FLOAT TEXT / RIPPLE ───────────────────────────────────────────────────
function spawnFlt(txt, x, y, col) {
  var el = document.createElement('div');
  el.className = 'ft'+(col?' crit':'');
  el.textContent = txt;
  if(col) el.style.color = col;
  var sp = col?60:40;
  el.style.left = (x + (Math.random()*sp - sp/2))+'px';
  el.style.top  = (y-20)+'px';
  document.body.appendChild(el);
  setTimeout(function(){ el.remove(); }, 1000);
}
function spawnRipple(x, y) {
  var el = document.createElement('div');
  el.className = 'rp';
  el.style.cssText = 'left:'+(x-25)+'px;top:'+(y-25)+'px;width:50px;height:50px';
  document.body.appendChild(el);
  setTimeout(function(){ el.remove(); }, 400);
}

// ─── NOTIF / ACH POPUP ─────────────────────────────────────────────────────
var _ntT = null;
function showNotif(msg) {
  var el = document.getElementById('notif');
  el.textContent = msg; el.classList.add('on');
  clearTimeout(_ntT);
  _ntT = setTimeout(function(){ el.classList.remove('on'); }, 2200);
}
var _apQ=[], _apB=false;
function showAchPopup(a) { _apQ.push(a); if(!_apB) nextAch(); }
function nextAch() {
  if(!_apQ.length){ _apB=false; return; }
  _apB=true; var a=_apQ.shift();
  document.getElementById('apopi').innerHTML = a.i;
  document.getElementById('apN').textContent = a.n;
  var rw = a.r.t==='c' ? '+ '+fmt(a.r.v)+' 💪' : '';
  if(a.r.t==='s') { for(var i=0;i<SKINS.length;i++){if(SKINS[i].id===a.r.v){rw='🎨 '+SKINS[i].n;break;}} }
  document.getElementById('apR').textContent = rw;
  document.getElementById('apop').classList.add('on');
  setTimeout(function(){
    document.getElementById('apop').classList.remove('on');
    setTimeout(nextAch, 400);
  }, 3000);
}

// ─── NICK / ID ─────────────────────────────────────────────────────────────
function getNick() {
  var s = localStorage.getItem('gymNick'); if(s) return s;
  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user) {
    var u = Telegram.WebApp.initDataUnsafe.user;
    return u.username || u.first_name || ('user'+u.id);
  }
  return null;
}
function getId() {
  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user)
    return ''+Telegram.WebApp.initDataUnsafe.user.id;
  var id = localStorage.getItem('gymId');
  if(!id){ id='anon_'+Date.now(); localStorage.setItem('gymId',id); }
  return id;
}
function openDrawer() {
  document.getElementById('ov').classList.add('on');
  document.getElementById('dr').classList.add('on');
  updateHUD(); renderAchs(); renderSkins(); renderBgs();
  var n = getNick(); if(n) document.getElementById('nickEdit').value=n;
}
function closeDrawer() {
  document.getElementById('ov').classList.remove('on');
  document.getElementById('dr').classList.remove('on');
}
function saveNick() {
  var v = document.getElementById('nickIn').value.trim();
  var hint = document.getElementById('nickHint');
  if(v.length<2){hint.textContent='Минимум 2 символа!';return;}
  if(v.length>20){hint.textContent='Максимум 20 символов!';return;}
  localStorage.setItem('gymNick',v);
  document.getElementById('nickpop').classList.remove('on');
  showNotif('Привет, '+v+'!'); pushScore();
}
function changeNick() {
  var v = document.getElementById('nickEdit').value.trim();
  if(v.length<2||v.length>20){showNotif('Ник: 2-20 символов');return;}
  localStorage.setItem('gymNick',v); updateHUD(); saveGame(); showNotif('Ник: '+v); pushScore();
}

// ─── OFFLINE ───────────────────────────────────────────────────────────────
var _offE = 0;
function checkOffline() {
  if(!G.lastSeen || G.cps<=0) return;
  var sec = Math.min((Date.now()-G.lastSeen)/1000, 7200);
  if(sec<30) return;
  _offE = Math.floor(G.cps*sec); if(!_offE) return;
  var h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60);
  document.getElementById('offT').textContent='Отсутствовал: '+(h?h+'ч ':'')+m+'мин';
  document.getElementById('offE').textContent='+'+fmt(_offE);
  document.getElementById('offpop').classList.add('on');
}
function claimOffline() {
  G.coins+=_offE; G.allC+=_offE; checkAchs(); updateHUD();
  document.getElementById('offpop').classList.remove('on');
  showNotif('+'+fmt(_offE)+' бицушек!');
}

// ─── LEADERBOARD ───────────────────────────────────────────────────────────
var API = window.location.origin;
function pushScore() {
  var nick = getNick(); if(!nick || G.cps<=0) return;
  try {
    fetch(API+'/api/score',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user_id:getId(),username:nick,cph:Math.floor(G.cps*3600),skin:G.skin||'default'})});
  } catch(e) {}
}
function loadLB() {
  var el=document.getElementById('lbList'),pod=document.getElementById('lbPod');
  el.innerHTML='<div class="lb-empty">Загрузка...</div>'; pod.innerHTML='';
  fetch(API+'/api/leaderboard').then(function(r){return r.json();}).then(function(rows){
    if(!rows||!rows.length){el.innerHTML='<div class="lb-empty">Пока никого нет</div>';return;}
    var myN=getNick();
    // Podium
    var t3=rows.slice(0,3);
    var ord=t3.length>=2?[t3[1],t3[0],t3[2]].filter(Boolean):[t3[0]];
    var cls2=t3.length>=2?['p2','p1','p3']:['p1'];
    var num=t3.length>=2?[2,1,3]:[1];
    var ph='<div class="pod"><div class="podt">🏆 Зал Славы</div><div class="pods">';
    for(var i=0;i<ord.length;i++){
      var r=ord[i];var me=r.username===myN;
      ph+='<div class="podsl '+cls2[i]+'"><div class="podc">'+(num[i]===1?'👑':'')+'</div>'
        +'<div class="podci">'+getSkinEmoji(r.skin||'default')+'</div>'
        +'<div class="podnm"'+(me?' style="color:var(--gn)"':'')+'>'+r.username+(me?' 👈':'')+'</div>'
        +'<div class="podcp">'+fmt(r.cph)+'/ч</div><div class="podbk">'+num[i]+'</div></div>';
    }
    ph+='</div></div>'; pod.innerHTML=ph;
    var rest=rows.slice(3); if(!rest.length){el.innerHTML='';return;}
    var h='<div class="poddiv"></div>';
    for(var j=0;j<rest.length;j++){
      var rr=rest[j];var me2=rr.username===myN;
      h+='<div class="lbrow'+(me2?' me':'')+'">'
        +'<div class="lbrk">'+(j+4)+'</div>'
        +'<div class="lbsk">'+getSkinEmoji(rr.skin||'default')+'</div>'
        +'<div class="lbnm">'+rr.username+(me2?' 👈':'')+'</div>'
        +'<div class="lbcp">'+fmt(rr.cph)+'/ч</div></div>';
    }
    el.innerHTML=h;
  }).catch(function(){el.innerHTML='<div class="lb-empty">Ошибка загрузки</div>';});
}

// ─── CRASH ─────────────────────────────────────────────────────────────────
var CR = {bet:0, running:false, mult:1.0, timer:null, crashAt:1.0, history:[]};
try { CR.history=JSON.parse(localStorage.getItem('crH')||'[]'); } catch(e){}
function crashGenPt() {
  var r=Math.random();
  if(r<.50) return 1.01+Math.random()*.29;
  if(r<.75) return 1.30+Math.random()*.70;
  if(r<.90) return 2.0+Math.random()*2;
  if(r<.97) return 4+Math.random()*6;
  return 10+Math.random()*15;
}
function setCrashBet(val) {
  if(CR.running) return;
  var b = val==='all' ? Math.floor(G.coins) : parseInt(val);
  if(isNaN(b)||b<=0) return;
  b = Math.min(b, Math.floor(G.coins)); CR.bet=b;
  document.getElementById('crashBetDisp').innerHTML='Ставка: '+fmt(b)+' 💪';
  document.querySelectorAll('.cbb').forEach(function(btn){
    btn.classList.toggle('sel', btn.dataset.bet==val);
  });
}
function crashStart() {
  if(CR.running) return;
  if(CR.bet<=0){showNotif('Сделай ставку!');return;}
  if(G.coins<CR.bet){showNotif('Недостаточно бицушек!');return;}
  G.coins -= CR.bet; updateHUD();
  CR.running=true; CR.mult=1.0; CR.crashAt=parseFloat(crashGenPt().toFixed(2));
  var ico=document.getElementById('crashIcon');
  ico.classList.remove('idle'); ico.innerHTML=getSkinEmoji(G.skin||'default');
  document.getElementById('crashStartBtn').disabled=true;
  document.getElementById('crashCashBtn').disabled=false;
  document.getElementById('crashStat').textContent='Монетка бежит! Забери вовремя!';
  document.getElementById('crashMult').style.color='';
  playSound('crash_start');
  var spd=0.015;
  CR.timer = setInterval(function(){
    CR.mult = parseFloat((CR.mult+spd).toFixed(2));
    spd = Math.min(spd+0.0005, 0.1);
    document.getElementById('crashMult').textContent='x'+CR.mult.toFixed(2);
    if(CR.mult >= CR.crashAt) crashEnd(false);
  }, 100);
}
function crashCash() { if(CR.running) crashEnd(true); }
function crashEnd(won) {
  clearInterval(CR.timer); CR.running=false;
  var ico=document.getElementById('crashIcon');
  ico.classList.add('idle');
  document.getElementById('crashStartBtn').disabled=false;
  document.getElementById('crashCashBtn').disabled=true;
  if(won) {
    var win=Math.floor(CR.bet*CR.mult);
    G.coins+=win; G.allC+=win; updateHUD();
    CR.history.unshift({m:CR.mult.toFixed(2),w:true});
    G.crashWins=(G.crashWins||0)+1; checkAchs();
    document.getElementById('crashStat').textContent='Выиграл! +'+fmt(win)+' (x'+CR.mult.toFixed(2)+')';
    document.getElementById('crashMult').style.color='var(--gn)';
    showNotif('+'+fmt(win)+' бицушек!');
    playSound('win');
  } else {
    CR.history.unshift({m:CR.crashAt.toFixed(2),w:false});
    ico.innerHTML='💀';
    document.getElementById('crashStat').textContent='КРАШ на x'+CR.crashAt+'! Потерял '+fmt(CR.bet);
    document.getElementById('crashMult').style.color='var(--rd)';
    showNotif('Краш на x'+CR.crashAt+'!');
    playSound('lose');
    setTimeout(function(){
      ico.innerHTML=getSkinEmoji(G.skin||'default');
      document.getElementById('crashMult').textContent='x1.00';
      document.getElementById('crashMult').style.color='';
    },1800);
  }
  if(CR.history.length>20) CR.history=CR.history.slice(0,20);
  try{localStorage.setItem('crH',JSON.stringify(CR.history));}catch(e){}
  renderCrashHist();
}
function renderCrashHist() {
  var el=document.getElementById('crashHistList'); if(!el) return;
  el.innerHTML=CR.history.map(function(h){
    return '<span class="ch '+(h.w?'w':'l')+'">x'+h.m+'</span>';
  }).join('');
}

// ─── SLOTS ─────────────────────────────────────────────────────────────────
var SLOT_SYMS = [
  {e:'💪',pay3:3, w:35},
  {e:'🏋️',pay3:4, w:25},
  {e:'🥊',pay3:5, w:18},
  {e:'⚡',pay3:6, w:14},
  {e:'🏆',pay3:10,w:10},
  {e:'💎',pay3:20,w:6 },
  {e:'🔥',pay3:30,w:4 },
  {e:'🎯',pay3:50,w:2 }
];
var SL = {bet:0, spinning:false, soundOn:true};

function slotRand() {
  var tot=SLOT_SYMS.reduce(function(s,x){return s+x.w;},0);
  var r=Math.random()*tot;
  for(var i=0;i<SLOT_SYMS.length;i++){r-=SLOT_SYMS[i].w; if(r<=0) return i;}
  return 0;
}
function setSlotBet(val) {
  if(SL.spinning) return;
  var b = val==='all' ? Math.floor(G.coins) : parseInt(val);
  if(isNaN(b)||b<=0) return;
  b = Math.min(b, Math.floor(G.coins)); SL.bet=b;
  document.getElementById('slotBetDisp').innerHTML='Ставка: '+fmt(b)+' 💪';
  document.querySelectorAll('.sbb2').forEach(function(btn){
    btn.classList.toggle('sel', btn.dataset.sbet==val);
  });
}
function doSpin() {
  if(SL.spinning) return;
  if(SL.bet<=0){showNotif('Сделай ставку!');return;}
  if(G.coins<SL.bet){showNotif('Недостаточно бицушек!');return;}
  var ac = getAC(); if(ac&&ac.state==='suspended') ac.resume();
  G.coins -= SL.bet; updateHUD();
  SL.spinning=true;
  document.getElementById('spinBtn').disabled=true;
  document.getElementById('slotsRes').innerHTML='';
  for(var r=0;r<3;r++){
    document.getElementById('reel'+r).classList.remove('win-reel');
    document.getElementById('reel'+r).classList.add('spinning');
  }
  playSound('slot_spin');
  var results=[slotRand(),slotRand(),slotRand()];
  var stops=[1100,1900,2700];
  for(var ri=0;ri<3;ri++){
    (function(idx){
      var iv=setInterval(function(){
        document.getElementById('sym'+idx).textContent=SLOT_SYMS[Math.floor(Math.random()*SLOT_SYMS.length)].e;
      },80);
      setTimeout(function(){
        clearInterval(iv);
        document.getElementById('reel'+idx).classList.remove('spinning');
        document.getElementById('sym'+idx).textContent=SLOT_SYMS[results[idx]].e;
        playSound('slot_stop');
        if(idx===2) setTimeout(function(){slotCheckWin(results);},300);
      },stops[idx]);
    })(ri);
  }
}
function slotCheckWin(res) {
  var bet=SL.bet, win=0, msg='';
  if(res[0]===res[1]&&res[1]===res[2]) {
    var sym=SLOT_SYMS[res[0]], mult=sym.pay3;
    win=Math.floor(bet*mult);
    for(var r=0;r<3;r++) document.getElementById('reel'+r).classList.add('win-reel');
    if(mult>=20){
      playSound('jackpot');
      msg='<span style="color:#ffd700;font-size:15px">🎉 ДЖЕКПОТ! '+sym.e+sym.e+sym.e+' x'+mult+' = +'+fmt(win)+' 💪</span>';
    } else {
      playSound('win');
      msg='<span style="color:var(--gn)">✅ ПОБЕДА! '+sym.e+sym.e+sym.e+' x'+mult+' = +'+fmt(win)+' 💪</span>';
    }
    G.slotWins = (G.slotWins||0)+1;
  } else if(res[0]===res[1]||res[1]===res[2]||res[0]===res[2]) {
    win=Math.floor(bet*1.5); playSound('win');
    msg='<span style="color:var(--bl)">✨ Два совпадения! x1.5 = +'+fmt(win)+' 💪</span>';
    if(res[0]===res[1]){document.getElementById('reel0').classList.add('win-reel');document.getElementById('reel1').classList.add('win-reel');}
    else if(res[1]===res[2]){document.getElementById('reel1').classList.add('win-reel');document.getElementById('reel2').classList.add('win-reel');}
    else{document.getElementById('reel0').classList.add('win-reel');document.getElementById('reel2').classList.add('win-reel');}
    G.slotWins = (G.slotWins||0)+1;
  } else {
    playSound('lose');
    msg='<span style="color:var(--mt)">😔 Не повезло... -'+fmt(bet)+' 💪</span>';
  }
  if(win>0){ G.coins+=win; G.allC+=win; updateHUD(); checkAchs(); showNotif('+'+fmt(win)+' бицушек!'); }
  document.getElementById('slotsRes').innerHTML='<div class="slots-res">'+msg+'</div>';
  SL.spinning=false;
  document.getElementById('spinBtn').disabled=false;
  saveGame();
}

// ─── SOUND ─────────────────────────────────────────────────────────────────
var _ac = null;
function getAC() {
  if(!_ac) { try{ _ac=new(window.AudioContext||window.webkitAudioContext)(); }catch(e){} }
  return _ac;
}
function tone(freq, endFreq, dur, vol, type, delay) {
  var ctx=getAC(); if(!ctx) return;
  delay=delay||0;
  var o=ctx.createOscillator(), g=ctx.createGain();
  o.connect(g); g.connect(ctx.destination);
  o.type=type||'sine';
  var t=ctx.currentTime+delay;
  o.frequency.setValueAtTime(freq, t);
  if(endFreq) o.frequency.exponentialRampToValueAtTime(endFreq, t+dur);
  g.gain.setValueAtTime(vol, t);
  g.gain.exponentialRampToValueAtTime(0.001, t+dur);
  o.start(t); o.stop(t+dur);
}
function playSound(type) {
  if(!SL.soundOn) return;
  var ctx=getAC(); if(!ctx) return;
  if(ctx.state==='suspended') ctx.resume();
  if(type==='click'){
    tone(480,220,.07,.09,'sine');
  } else if(type==='slot_spin'){
    for(var i=0;i<10;i++) tone(150+Math.random()*200,null,.05,.05,'square',i*0.07);
  } else if(type==='slot_stop'){
    tone(300,140,.12,.2,'sine');
  } else if(type==='win'){
    [440,554,659,880].forEach(function(f,i){ tone(f,null,.25,.15,'sine',i*.09); });
  } else if(type==='jackpot'){
    [440,554,659,880,1100,880,1100,1320].forEach(function(f,i){ tone(f,null,.2,.2,'triangle',i*.07); });
  } else if(type==='lose'){
    tone(280,80,.4,.1,'sawtooth');
  } else if(type==='crash_start'){
    tone(220,440,.3,.1,'sine');
  }
}

// ─── TIMER AUTO COLLECT ────────────────────────────────────────────────────
function autoCollect() {
  var changed=false;
  Object.keys(TIMERS).forEach(function(id){
    if(!TIMERS[id].done && Date.now()>=TIMERS[id].end) {
      TIMERS[id].done=true;
      G.ul[id]=(G.ul[id]||0)+1; G.allU++; G.xp+=10;
      changed=true;
      var u=null;
      for(var i=0;i<ALL_UPG.length;i++){if(ALL_UPG[i].id===id){u=ALL_UPG[i];break;}}
      recalc(); checkLevel(); checkAchs();
      if(u) showNotif('✅ '+u.n+' Ур.'+uLvl(id)+' готово!');
      delete TIMERS[id];
    }
  });
  if(changed){ updateHUD(); renderUpgrades(); }
}

// ─── MAIN TICK ─────────────────────────────────────────────────────────────
var _lastT = Date.now();
function tick() {
  var now=Date.now(); var dt=Math.min((now-_lastT)/1000,.5); _lastT=now;
  if(G.cps>0){ G.coins+=G.cps*dt; G.allC+=G.cps*dt; }
  G.nrg=Math.min(G.mxE, G.nrg+G.rgE*dt);
  G.pt+=dt;
  updateHUD();
}

function resetProgress() {
  if(!confirm('Сбросить весь прогресс? Это необратимо!')) return;
  localStorage.removeItem(SK); localStorage.removeItem(SK+'_t');
  TIMERS={}; G=Object.assign({},DEF);
  recalc(); applySkin('default'); applyBg('bg0');
  updateHUD(); renderUpgrades(); renderAchs(); renderSkins(); renderBgs();
  showNotif('Прогресс сброшен!');
}

// ─── INIT ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  loadGame();
  recalc();
  applySkin(G.skin || 'default');
  applyBg(G.bg || 'bg0');
  updateHUD();
  renderUpgrades();
  renderCrashHist();

  // Offline check
  checkOffline();

  // Nick check
  if(!getNick()) document.getElementById('nickpop').classList.add('on');

  // Timers
  setInterval(tick, 100);
  setInterval(saveGame, 5000);
  setInterval(renderUpgrades, 1500);
  setInterval(checkAchs, 3000);
  setInterval(pushScore, 30000);
  setInterval(autoCollect, 500);
  document.addEventListener('visibilitychange', function(){ if(document.hidden) saveGame(); });

  // ── COIN 3D ──
  var scene = document.getElementById('coinScene');
  if(scene) {
    function triggerCoin(x, y) {
      var c3 = document.getElementById('coin3d');
      c3.classList.remove('tapped'); void c3.offsetWidth; c3.classList.add('tapped');
      setTimeout(function(){ c3.classList.remove('tapped'); }, 350);
      playSound('click');
      doClick(x, y);
    }
    scene.addEventListener('touchstart', function(e){
      e.preventDefault();
      var ac=getAC(); if(ac&&ac.state==='suspended') ac.resume();
      for(var i=0;i<e.changedTouches.length;i++){
        triggerCoin(e.changedTouches[i].clientX, e.changedTouches[i].clientY);
      }
    },{passive:false});
    scene.addEventListener('mousedown', function(e){
      var ac=getAC(); if(ac&&ac.state==='suspended') ac.resume();
      triggerCoin(e.clientX, e.clientY);
    });
  }

  // ── PROFILE BUTTON ──
  document.getElementById('profBtn').addEventListener('click', openDrawer);
  document.getElementById('drCloseBtn').addEventListener('click', closeDrawer);
  document.getElementById('ov').addEventListener('click', closeDrawer);

  // ── NICK ──
  document.getElementById('nickSaveBtn').addEventListener('click', saveNick);
  document.getElementById('nickIn').addEventListener('keydown', function(e){
    if(e.key==='Enter') saveNick();
  });
  document.getElementById('nickEditBtn').addEventListener('click', changeNick);

  // ── OFFLINE ──
  document.getElementById('offBtn').addEventListener('click', claimOffline);

  // ── LB ──
  document.getElementById('lbRefBtn').addEventListener('click', loadLB);

  // ── RESET ──
  document.getElementById('resetBtn').addEventListener('click', resetProgress);

  // ── BOTTOM NAV ──
  document.getElementById('bnav').addEventListener('click', function(e){
    var b = e.target.closest('.bnb'); if(!b) return;
    var t = b.dataset.t;
    document.querySelectorAll('.bnb').forEach(function(x){ x.classList.toggle('on', x.dataset.t===t); });
    document.querySelectorAll('.panel').forEach(function(x){ x.classList.toggle('on', x.id==='panel-'+t); });
    if(t==='top') loadLB();
  });

  // ── UPGRADE TABS ──
  document.querySelectorAll('.ubtab').forEach(function(b){
    b.addEventListener('click', function(){
      var u=this.dataset.u;
      document.querySelectorAll('.ubtab').forEach(function(x){ x.classList.toggle('on', x.dataset.u===u); });
      document.querySelectorAll('.ubpan').forEach(function(x){ x.classList.toggle('on', x.id==='ubpan-'+u); });
    });
  });

  // ── PROFILE TABS ──
  document.querySelectorAll('.drtab').forEach(function(b){
    b.addEventListener('click', function(){
      var p=this.dataset.p;
      document.querySelectorAll('.drtab').forEach(function(x){ x.classList.toggle('on', x.dataset.p===p); });
      document.querySelectorAll('.drp').forEach(function(x){ x.classList.toggle('on', x.id==='drp-'+p); });
      if(p==='achs') renderAchs();
      if(p==='skins') renderSkins();
      if(p==='bgs') renderBgs();
    });
  });

  // ── DELEGATION ──
  document.addEventListener('click', function(e){
    var u=e.target.closest('[data-uid]'); if(u){buyUpg(u.dataset.uid);return;}
    var s=e.target.closest('[data-sid]'); if(s){tapSkin(s.dataset.sid);return;}
    var bg=e.target.closest('[data-bgid]'); if(bg){tapBg(bg.dataset.bgid);return;}
    var a=e.target.closest('[data-aid]'); if(a){claimReward(a.dataset.aid);return;}
  });

  // ── CRASH ──
  document.getElementById('crashStartBtn').addEventListener('click', crashStart);
  document.getElementById('crashCashBtn').addEventListener('click', crashCash);
  document.getElementById('crashSetBtn').addEventListener('click', function(){
    var v=parseInt(document.getElementById('crashBetIn').value); if(v>0) setCrashBet(v);
  });
  document.getElementById('crashBetIn').addEventListener('keydown', function(e){
    if(e.key==='Enter'){var v=parseInt(this.value);if(v>0)setCrashBet(v);}
  });
  document.querySelectorAll('.cbb').forEach(function(btn){
    btn.addEventListener('click', function(){ setCrashBet(this.dataset.bet); });
  });

  // ── SLOTS ──
  document.querySelectorAll('.sbb2').forEach(function(btn){
    btn.addEventListener('click', function(){ setSlotBet(this.dataset.sbet); });
  });
  document.getElementById('spinBtn').addEventListener('click', doSpin);
  document.getElementById('volBtn').addEventListener('click', function(){
    SL.soundOn=!SL.soundOn;
    this.classList.toggle('on', SL.soundOn);
    this.textContent=SL.soundOn?'🔊':'🔇';
  });

  // ── TG TASK ──
  var tb=document.getElementById('taskTgBtn');
  if(tb){
    if(localStorage.getItem('tg_task')){
      tb.textContent='Выполнено'; tb.disabled=true;
      document.getElementById('taskTg').classList.add('done');
    }
    tb.addEventListener('click', function(){
      window.open('https://t.me/gymclicker','_blank');
      var btn=this;
      setTimeout(function(){
        if(!localStorage.getItem('tg_task')){
          localStorage.setItem('tg_task','1');
          G.coins+=10000; G.allC+=10000; updateHUD(); saveGame();
          showNotif('+10,000 бицушек!');
          btn.textContent='Выполнено'; btn.disabled=true;
          document.getElementById('taskTg').classList.add('done');
        }
      },3000);
    });
  }

  // ── TELEGRAM ──
  if(window.Telegram && Telegram.WebApp){ Telegram.WebApp.ready(); Telegram.WebApp.expand(); }
});
</script>
</body>
</html>"""

# ─── HTTP HANDLER ─────────────────────────────────────────────────────────────
class GameHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Frame-Options", "ALLOWALL")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/leaderboard":
            data = json.dumps(get_top(20)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors(); self.end_headers(); self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors(); self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/score":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                upsert_score(data.get("user_id","unknown"),
                             data.get("username","Игрок")[:32],
                             float(data.get("cph",0)),
                             data.get("skin","default"))
                self.send_response(200); self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers(); self.wfile.write(b'{"ok":true}')
            except Exception as ex:
                logger.warning("[API] score error: %s", ex)
                self.send_response(400); self._cors(); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, fmt_str, *args):
        logger.info("[WEB] %s - %s", self.address_string(), fmt_str % args)


def run_web():
    server = HTTPServer(("0.0.0.0", PORT), GameHandler)
    logger.info("[WEB] Running on http://0.0.0.0:%s", PORT)
    server.serve_forever()


# ─── TELEGRAM BOT ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("💪 Играть в Качалку!", web_app=WebAppInfo(url=GAME_URL))]]
    await update.message.reply_text(
        f"Привет, {user.first_name}! 💪\n\n"
        "🏋️ *Качалка Кликер* — прокачай своего качка!\n\n"
        "• Тыкай на монету с бицепсом 💪\n"
        "• Покупай улучшения для роста дохода\n"
        "• Инвестируй в страны для пассивного дохода\n"
        "• Играй в Краш и Слоты 🎰\n"
        "• Разблокируй скины и достижения 🏆\n\n"
        "Нажми кнопку ниже чтобы начать!",
        parse_mode="Markdown",
        reply_markup=__import__('telegram').InlineKeyboardMarkup(keyboard),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏋️ *Как играть:*\n\n"
        "1. Нажимай на монету 💪 — даёт бицушки\n"
        "2. *Прокачка → Удар* — больше монет за клик\n"
        "3. *Прокачка → Доход* — пассивный доход/ч\n"
        "4. *Краш* — рискованная игра на множитель\n"
        "5. *Слоты* — крути барабаны, выигрывай бицушки!\n"
        "6. *Профиль* — скины, достижения, статистика",
        parse_mode="Markdown",
    )

def run_bot():
    if BOT_TOKEN in ("YOUR_TOKEN", ""):
        logger.error("Укажи BOT_TOKEN!"); return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    logger.info("[BOT] Running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ─── ENTRY ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    run_bot()

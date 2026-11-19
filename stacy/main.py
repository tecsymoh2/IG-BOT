"""FastAPI app: Meta webhook + admin API for STACY XMD."""
import asyncio
import json
import logging

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from . import bot, db
from . import instagram as ig
from .config import settings as S

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stacy.main")

app = FastAPI(title=f"{S.BOT_NAME} Instagram Bot", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>{S.BOT_NAME}</title>
<body style="font-family:system-ui;display:grid;place-items:center;min-height:90vh;text-align:center">
<div><h1>🤖 {S.BOT_NAME}</h1><p>Instagram assistant is online.</p></div></body>"""


@app.get("/health")
async def health():
    return {
        "ok": True,
        "bot": S.BOT_NAME,
        "configured": {
            "instagram": bool(S.IG_ACCESS_TOKEN and S.IG_USER_ID and S.IG_APP_SECRET),
            "groq": bool(S.GROQ_API_KEY),
            "supabase": bool(S.SUPABASE_URL and S.SUPABASE_KEY),
        },
    }


# ------------------------------------------------------------- Webhook -------
@app.get("/webhook")
async def verify(
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
):
    if mode == "subscribe" and S.IG_VERIFY_TOKEN and token == S.IG_VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    raise HTTPException(403, "Verification failed")


@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    if not ig.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"ok": False}

    tasks = []
    for entry in payload.get("entry", []):
        for ev in entry.get("messaging") or []:
            tasks.append(bot.handle_message(ev))
        for ch in entry.get("changes") or []:
            if ch.get("field") in {"comments", "live_comments"}:
                tasks.append(bot.handle_comment(ch.get("value") or {}))

    # Serverless functions can freeze after responding, so finish the work before returning 200.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            log.error("handler failed", exc_info=r)
    return {"ok": True}


# --------------------------------------------------------------- Admin -------
async def admin(x_admin_token: str | None = Header(None)):
    if not S.ADMIN_TOKEN or x_admin_token != S.ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")


class RuleIn(BaseModel):
    trigger: str
    reply: str = ""
    dm_reply: str | None = None
    match_type: str = "contains"  # contains | exact
    scope: str = "both"  # dm | comment | both
    active: bool = True


class SendIn(BaseModel):
    user_id: str
    text: str


@app.get("/admin/stats", dependencies=[Depends(admin)])
async def stats():
    return {
        "paused": await db.get_setting("paused") == "true",
        "users": await db.count("ig_users"),
        "messages": await db.count("ig_messages"),
        "comments": await db.count("ig_comments"),
        "rules": await db.count("ig_rules"),
        "handoffs_waiting": await db.count("ig_users", {"human_handoff": "eq.true"}),
    }


@app.post("/admin/pause", dependencies=[Depends(admin)])
async def pause():
    await db.set_setting("paused", "true")
    return {"paused": True}


@app.post("/admin/resume", dependencies=[Depends(admin)])
async def resume():
    await db.set_setting("paused", "false")
    return {"paused": False}


@app.get("/admin/users", dependencies=[Depends(admin)])
async def users():
    return await db.list_users()


@app.post("/admin/users/{uid}/{action}", dependencies=[Depends(admin)])
async def user_action(uid: str, action: str):
    fields = {
        "pause": {"paused": True},
        "resume": {"paused": False, "human_handoff": False},
        "block": {"blocked": True},
        "unblock": {"blocked": False},
    }.get(action)
    if fields is None:
        raise HTTPException(400, "action must be pause|resume|block|unblock")
    await db.update_user(uid, fields)
    return {"ok": True}


@app.get("/admin/conversations/{uid}", dependencies=[Depends(admin)])
async def conversation(uid: str, limit: int = 50):
    return await db.get_history(uid, limit)


@app.post("/admin/send", dependencies=[Depends(admin)])
async def send(body: SendIn):
    ok = await ig.send_dm(body.user_id, body.text)
    if ok:
        await db.add_message(body.user_id, "assistant", body.text)
    return {"sent": ok}


@app.get("/admin/rules", dependencies=[Depends(admin)])
async def rules():
    return await db.list_rules()


@app.post("/admin/rules", dependencies=[Depends(admin)])
async def add_rule(rule: RuleIn):
    return await db.add_rule(rule.model_dump())


@app.delete("/admin/rules/{rule_id}", dependencies=[Depends(admin)])
async def del_rule(rule_id: int):
    await db.delete_rule(rule_id)
    return {"deleted": rule_id}


@app.post("/admin/refresh-token", dependencies=[Depends(admin)])
async def refresh_token():
    """Long-lived Instagram tokens last 60 days. Call this, then update IG_ACCESS_TOKEN on Vercel."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": S.IG_ACCESS_TOKEN},
        )
    return r.json()

"""STACY XMD brain: decides how to answer DMs, story replies/mentions, and comments."""
import logging
import re

from . import ai, db
from . import instagram as ig
from .config import settings as S

log = logging.getLogger("stacy.bot")

LINK_RE = re.compile(r"(https?://|www\.)", re.I)


def fmt(text: str) -> str:
    return text.replace("{bot}", S.BOT_NAME).replace("{owner}", S.OWNER_NAME)


def match_rule(text: str, rules: list[dict]) -> dict | None:
    t = text.lower().strip()
    for r in rules:
        trig = (r.get("trigger") or "").lower().strip()
        if not trig:
            continue
        hit = t == trig if r.get("match_type") == "exact" else trig in t
        if hit:
            return r
    return None


def wants_human(low: str) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\b", low) for k in S.HANDOFF_KEYWORDS)


async def _reply(uid: str, text: str) -> None:
    if await ig.send_dm(uid, text):
        await db.add_message(uid, "assistant", text)


# ------------------------------------------------------------------ DMs ------
async def handle_message(ev: dict) -> None:
    sender = (ev.get("sender") or {}).get("id")
    msg = ev.get("message") or {}
    if not sender or not msg or msg.get("is_echo") or sender == S.IG_USER_ID:
        return

    mid = msg.get("mid")
    if mid and not await db.claim_event(f"msg:{mid}"):
        return

    text = (msg.get("text") or "").strip()
    context = None
    if (msg.get("reply_to") or {}).get("story"):
        context = "The user is replying to one of your Instagram stories."
    for a in msg.get("attachments") or []:
        kind = a.get("type")
        if kind == "story_mention":
            context = "The user just mentioned you in their Instagram story. Thank them warmly."
            text = text or "[mentioned you in their story]"
        elif kind in {"image", "video", "audio", "share", "reel", "ig_reel"} and not text:
            context = f"The user sent a {kind} you cannot view. Ask them to describe it in text."
            text = f"[sent a {kind}]"
    if not text:
        return

    if await db.get_setting("paused") == "true":
        return

    low = text.lower().strip()
    user = await db.get_user(sender)
    is_new = user is None
    user = user or {}
    await db.upsert_user(sender)

    # Opt-out / opt-in commands
    if low in {"stop", "unsubscribe", "/stop"}:
        await db.update_user(sender, {"paused": True})
        await ig.send_dm(sender, "Done, I won't auto-reply anymore. Send START anytime to turn me back on.")
        return
    if low in {"start", "/start"} and (user.get("paused") or user.get("human_handoff")):
        await db.update_user(sender, {"paused": False, "human_handoff": False})
        await ig.send_dm(sender, "Welcome back! How can I help? 😊")
        return

    await db.add_message(sender, "user", text)

    if user.get("blocked") or user.get("paused") or user.get("human_handoff"):
        return
    if await db.count_recent_user_messages(sender, 60) > S.RATE_LIMIT_PER_MIN:
        return

    # Human handoff
    if wants_human(low):
        await db.update_user(sender, {"human_handoff": True})
        await _reply(sender, fmt(S.HANDOFF_MESSAGE))
        return

    # Welcome message for first-time users (short greetings end here)
    if is_new and S.WELCOME_MESSAGE:
        await _reply(sender, fmt(S.WELCOME_MESSAGE))
        if len(text.split()) <= 3 and not context:
            return

    # Keyword rules from Supabase
    rule = match_rule(text, await db.get_rules("dm"))
    if rule and rule.get("reply"):
        await _reply(sender, fmt(rule["reply"]))
        return

    # AI reply
    if not (S.AI_DM_REPLIES and S.GROQ_API_KEY):
        return
    await ig.typing(sender)
    history = await db.get_history(sender, S.HISTORY_LIMIT)
    answer = await ai.reply_dm(history, context)
    if not answer:
        answer = f"Thanks for your message! {S.OWNER_NAME} will get back to you soon. 🙏"
    await _reply(sender, answer)


# ------------------------------------------------------------- Comments ------
async def handle_comment(v: dict) -> None:
    cid = v.get("id")
    text = (v.get("text") or "").strip()
    frm = v.get("from") or {}
    uid, uname = frm.get("id"), frm.get("username")
    media_id = (v.get("media") or {}).get("id")

    if not cid or not text or uid == S.IG_USER_ID:
        return
    if S.COMMENT_TOPLEVEL_ONLY and v.get("parent_id"):
        return
    if not await db.claim_event(f"cmt:{cid}"):
        return
    if await db.get_setting("paused") == "true":
        return

    low = text.lower()

    # Spam filter
    if S.HIDE_SPAM and (LINK_RE.search(text) or any(w in low for w in S.BLOCKED_WORDS)):
        await ig.hide_comment(cid)
        await db.log_comment(cid, media_id, uid, uname, text, None, "hidden_spam")
        return

    # Keyword rules (public reply and/or private DM)
    rule = match_rule(text, await db.get_rules("comment"))
    if rule:
        public = fmt(rule.get("reply") or "")
        dm = fmt(rule.get("dm_reply") or "")
        if public:
            await ig.reply_comment(cid, public)
        if dm and await ig.private_reply(cid, dm):
            await db.upsert_user(uid, uname)
            await db.add_message(uid, "assistant", dm)
        await db.log_comment(cid, media_id, uid, uname, text, public or dm, "rule")
        return

    # AI public reply
    reply = None
    if S.AI_COMMENT_REPLIES and S.GROQ_API_KEY:
        reply = await ai.reply_comment(uname, text)
        if reply:
            await ig.reply_comment(cid, reply)

    # Optional DM to every commenter
    if S.COMMENT_DM_TEXT and await ig.private_reply(cid, fmt(S.COMMENT_DM_TEXT)):
        await db.upsert_user(uid, uname)
        await db.add_message(uid, "assistant", fmt(S.COMMENT_DM_TEXT))

    await db.log_comment(cid, media_id, uid, uname, text, reply, "ai" if reply else "ignored")

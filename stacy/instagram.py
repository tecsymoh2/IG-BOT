"""Instagram Graph API helpers: send DMs, reply to / hide comments, verify webhooks."""
import hashlib
import hmac
import logging

import httpx

from .config import settings

log = logging.getLogger("stacy.ig")


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Validate Meta's X-Hub-Signature-256 header. Fails closed if the app secret is missing."""
    if not settings.IG_APP_SECRET:
        log.error("IG_APP_SECRET is not set; rejecting webhook")
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.IG_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def _auth() -> dict:
    return {"Authorization": f"Bearer {settings.IG_ACCESS_TOKEN}"}


async def _post(path: str, *, json=None, data=None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(
                f"{settings.IG_GRAPH_URL}/{path}", headers=_auth(), json=json, data=data
            )
        if r.status_code >= 400:
            log.warning("IG %s -> %s %s", path, r.status_code, r.text[:300])
            return False
        return True
    except httpx.HTTPError as e:
        log.error("IG %s failed: %s", path, e)
        return False


def _chunks(text: str, size: int = 900) -> list[str]:
    """Instagram DMs are capped at 1000 bytes; split long answers on sentence/space boundaries."""
    text = text.strip()
    out = []
    while len(text) > size:
        cut = max(text.rfind(". ", 0, size), text.rfind("\n", 0, size), text.rfind(" ", 0, size))
        cut = cut if cut > size // 2 else size
        out.append(text[: cut + 1].strip())
        text = text[cut + 1 :].strip()
    if text:
        out.append(text)
    return out


async def send_dm(recipient_id: str, text: str) -> bool:
    ok = True
    for part in _chunks(text):
        ok &= await _post(
            f"{settings.IG_USER_ID}/messages",
            json={"recipient": {"id": recipient_id}, "message": {"text": part}},
        )
    return ok


async def typing(recipient_id: str) -> None:
    await _post(
        f"{settings.IG_USER_ID}/messages",
        json={"recipient": {"id": recipient_id}, "sender_action": "typing_on"},
    )


async def private_reply(comment_id: str, text: str) -> bool:
    """DM a commenter directly from their comment (allowed once, within 7 days)."""
    return await _post(
        f"{settings.IG_USER_ID}/messages",
        json={"recipient": {"comment_id": comment_id}, "message": {"text": text[:900]}},
    )


async def reply_comment(comment_id: str, text: str) -> bool:
    return await _post(f"{comment_id}/replies", data={"message": text[:2000]})


async def hide_comment(comment_id: str) -> bool:
    return await _post(comment_id, data={"hide": "true"})

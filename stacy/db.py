"""Thin async Supabase client over the PostgREST API (no heavy SDK = small Vercel bundle)."""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .config import settings

log = logging.getLogger("stacy.db")


def _base() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def _headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _request(method: str, table: str, *, params=None, json=None, prefer=None):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.request(
                method, f"{_base()}/{table}", params=params, json=json, headers=_headers(prefer)
            )
        if r.status_code >= 400 and r.status_code != 409:
            log.warning("supabase %s %s -> %s %s", method, table, r.status_code, r.text[:200])
        return r
    except httpx.HTTPError as e:
        log.error("supabase %s %s failed: %s", method, table, e)
        return None


def _rows(r) -> list:
    if r is None or r.status_code >= 400:
        return []
    try:
        data = r.json()
        return data if isinstance(data, list) else []
    except ValueError:
        return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def count(table: str, params: dict | None = None) -> int:
    p = {"select": "*", "limit": "1", **(params or {})}
    r = await _request("GET", table, params=p, prefer="count=exact")
    if r is None or r.status_code >= 400:
        return 0
    try:
        return int(r.headers.get("content-range", "*/0").split("/")[-1])
    except ValueError:
        return 0


# --- Dedup -------------------------------------------------------------------
async def claim_event(event_id: str) -> bool:
    """True if this event is new. Meta retries webhooks, so we never process one twice."""
    r = await _request("POST", "processed_events", json={"id": event_id}, prefer="return=minimal")
    if r is None:
        return True  # fail open
    return r.status_code != 409


# --- Users -------------------------------------------------------------------
async def get_user(uid: str) -> dict | None:
    rows = _rows(await _request("GET", "ig_users", params={"id": f"eq.{uid}", "limit": "1"}))
    return rows[0] if rows else None


async def upsert_user(uid: str, username: str | None = None) -> None:
    body = {"id": uid, "last_seen": _now()}
    if username:
        body["username"] = username
    await _request(
        "POST", "ig_users", json=body, prefer="resolution=merge-duplicates,return=minimal"
    )


async def update_user(uid: str, fields: dict) -> None:
    await _request("PATCH", "ig_users", params={"id": f"eq.{uid}"}, json=fields, prefer="return=minimal")


async def list_users(limit: int = 50) -> list:
    return _rows(
        await _request("GET", "ig_users", params={"order": "last_seen.desc", "limit": str(limit)})
    )


# --- Messages ----------------------------------------------------------------
async def add_message(uid: str, role: str, content: str) -> None:
    await _request(
        "POST",
        "ig_messages",
        json={"user_id": uid, "role": role, "content": content[:4000]},
        prefer="return=minimal",
    )


async def get_history(uid: str, limit: int) -> list[dict]:
    rows = _rows(
        await _request(
            "GET",
            "ig_messages",
            params={
                "user_id": f"eq.{uid}",
                "select": "role,content",
                "order": "created_at.desc,id.desc",
                "limit": str(limit),
            },
        )
    )
    return list(reversed(rows))


async def count_recent_user_messages(uid: str, seconds: int) -> int:
    since = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    return await count(
        "ig_messages", {"user_id": f"eq.{uid}", "role": "eq.user", "created_at": f"gte.{since}"}
    )


# --- Rules -------------------------------------------------------------------
async def get_rules(scope: str) -> list:
    return _rows(
        await _request(
            "GET",
            "ig_rules",
            params={"active": "eq.true", "scope": f"in.({scope},both)", "order": "id.asc"},
        )
    )


async def list_rules() -> list:
    return _rows(await _request("GET", "ig_rules", params={"order": "id.asc"}))


async def add_rule(rule: dict) -> list:
    return _rows(await _request("POST", "ig_rules", json=rule, prefer="return=representation"))


async def delete_rule(rule_id: int) -> None:
    await _request("DELETE", "ig_rules", params={"id": f"eq.{rule_id}"}, prefer="return=minimal")


# --- Comments ----------------------------------------------------------------
async def log_comment(comment_id, media_id, user_id, username, text, reply, action) -> None:
    await _request(
        "POST",
        "ig_comments",
        json={
            "comment_id": comment_id,
            "media_id": media_id,
            "user_id": user_id,
            "username": username,
            "text": (text or "")[:2200],
            "reply": reply,
            "action": action,
        },
        prefer="resolution=ignore-duplicates,return=minimal",
    )


# --- Settings (global kill switch etc.) ---------------------------------------
async def get_setting(key: str) -> str | None:
    rows = _rows(
        await _request("GET", "bot_settings", params={"key": f"eq.{key}", "limit": "1"})
    )
    return rows[0]["value"] if rows else None


async def set_setting(key: str, value: str) -> None:
    await _request(
        "POST",
        "bot_settings",
        json={"key": key, "value": value},
        prefer="resolution=merge-duplicates,return=minimal",
    )

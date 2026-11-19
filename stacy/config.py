"""All settings come from environment variables (.env locally, Vercel env vars in production)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _s(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _i(name: str, default: int) -> int:
    try:
        return int(_s(name, str(default)))
    except ValueError:
        return default


def _l(name: str, default: str = "") -> list[str]:
    return [x.strip().lower() for x in _s(name, default).split(",") if x.strip()]


class Settings:
    # --- Identity -----------------------------------------------------------
    BOT_NAME = _s("BOT_NAME", "STACY XMD")
    OWNER_NAME = _s("OWNER_NAME", "the owner")
    PERSONA = _s("PERSONA", "Friendly, warm, a little playful, and concise.")
    BUSINESS_INFO = _s("BUSINESS_INFO", "")

    # --- Instagram (Instagram API with Instagram Login) ----------------------
    IG_USER_ID = _s("IG_USER_ID")
    IG_ACCESS_TOKEN = _s("IG_ACCESS_TOKEN")
    IG_APP_SECRET = _s("IG_APP_SECRET")
    IG_VERIFY_TOKEN = _s("IG_VERIFY_TOKEN")
    IG_GRAPH_URL = _s("IG_GRAPH_URL", "https://graph.instagram.com/v21.0")

    # --- Groq ---------------------------------------------------------------
    GROQ_API_KEY = _s("GROQ_API_KEY")
    GROQ_MODEL = _s("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_FALLBACK_MODEL = _s("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

    # --- Supabase -----------------------------------------------------------
    SUPABASE_URL = _s("SUPABASE_URL")
    SUPABASE_KEY = _s("SUPABASE_SERVICE_KEY")

    # --- Admin API ----------------------------------------------------------
    ADMIN_TOKEN = _s("ADMIN_TOKEN")

    # --- Feature toggles ----------------------------------------------------
    AI_DM_REPLIES = _b("AI_DM_REPLIES", True)
    AI_COMMENT_REPLIES = _b("AI_COMMENT_REPLIES", True)
    COMMENT_TOPLEVEL_ONLY = _b("COMMENT_TOPLEVEL_ONLY", True)
    COMMENT_DM_TEXT = _s("COMMENT_DM_TEXT")  # if set, DM every commenter (private reply)
    HIDE_SPAM = _b("HIDE_SPAM", True)
    BLOCKED_WORDS = _l("BLOCKED_WORDS", "free followers,buy followers,crypto giveaway,dm me to earn")
    RATE_LIMIT_PER_MIN = _i("RATE_LIMIT_PER_MIN", 8)
    HISTORY_LIMIT = _i("HISTORY_LIMIT", 12)

    WELCOME_MESSAGE = _s(
        "WELCOME_MESSAGE",
        "Hey! 👋 I'm {bot}, {owner}'s automated assistant. Ask me anything, "
        "or type 'human' anytime to reach a real person.",
    )
    HANDOFF_KEYWORDS = _l("HANDOFF_KEYWORDS", "human,real person,agent,talk to owner")
    HANDOFF_MESSAGE = _s(
        "HANDOFF_MESSAGE",
        "Got it! I've flagged this for {owner} and they'll reply personally as soon as they can. 🙏",
    )


settings = Settings()

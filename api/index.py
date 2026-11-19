import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stacy.main import app  # noqa: E402,F401  (Vercel serves this ASGI app)

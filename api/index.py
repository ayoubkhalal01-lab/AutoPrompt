"""
api/index.py — Vercel Python Serverless Function entrypoint for AutoPrompt.

This module acts as the bridge between Vercel's Python runtime and the
existing FastAPI application. Vercel discovers this file via vercel.json
rewrites and invokes the ASGI `app` object directly.

Path setup
----------
Adds `backend/` to sys.path so that `from app.main import app` resolves
correctly when Vercel runs this file from the repo root.

No application code lives here — all logic stays in backend/app/.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure backend/ is on the module search path.
# When Vercel invokes this file, cwd is the repo root.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# Import the FastAPI ASGI application.
# Vercel's Python runtime looks for a module-level `app` (ASGI callable).
# ---------------------------------------------------------------------------
from app.main import app  # noqa: E402  (import after sys.path mutation is intentional)

__all__ = ["app"]

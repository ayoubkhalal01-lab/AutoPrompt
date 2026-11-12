"""
config.py — Centralized application settings loaded from environment / .env file.

The .env file is NEVER committed to Git (enforced in .gitignore).
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Search candidate locations for backend/.env
_CURRENT_DIR = Path(__file__).resolve().parent
_CANDIDATE_PATHS = [
    _CURRENT_DIR.parent / ".env",                  # e:\prompauto\backend\.env
    _CURRENT_DIR.parent.parent / "backend" / ".env", # fallback if run from outer root
    _CURRENT_DIR.parent.parent / ".env",
]

for env_path in _CANDIDATE_PATHS:
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path, override=False)
        break


class Settings:
    # ── Gemini Provider Settings ──────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Default to a stable, currently available Gemini model.
    # See: https://ai.google.dev/gemini-api/docs/models
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    # Timeouts and retries for AI calls
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30.0"))
    GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
    GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))

    # ── Server & Environment ──────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # ── Database Settings (SQLite) ────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(_CURRENT_DIR.parent / 'autoprompt.db').as_posix()}"
    )

    # ── App Metadata ──────────────────────────────────────────────────────────
    APP_NAME: str = "AutoPrompt Backend"
    APP_VERSION: str = "0.1.0"

    @property
    def has_gemini_key(self) -> bool:
        """True only when the key is set and not the placeholder value."""
        return bool(self.GEMINI_API_KEY) and self.GEMINI_API_KEY != "your_gemini_api_key_here"


settings = Settings()

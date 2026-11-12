"""
AutoPrompt Database Package — Phase 6.
Provides SQLite database engine, session management, and SQLAlchemy models.
"""

from app.db.models import Base, PromptHistory, SavedPrompt
from app.db.session import SessionLocal, engine, get_db, init_db

__all__ = [
    "Base",
    "PromptHistory",
    "SavedPrompt",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
]

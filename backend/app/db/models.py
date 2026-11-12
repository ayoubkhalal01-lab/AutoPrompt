"""
models.py — SQLAlchemy ORM models for AutoPrompt Phase 6.

Tables:
- saved_prompts: Stores user-saved prompts with titles, tags, and category.
- prompt_history: Append-only log of Generate & Optimize executions with token metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SavedPrompt(Base):
    """
    User-saved prompts that can be retrieved, edited, reused, and deleted.
    """
    __tablename__ = "saved_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "generate" or "optimize"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_saved_prompts_category_op", "category", "operation_type"),
        Index("ix_saved_prompts_created_desc", created_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<SavedPrompt(id={self.id}, title='{self.title[:30]}', op='{self.operation_type}')>"


class PromptHistory(Base):
    """
    Immutable audit history recording all Generate and Optimize operations,
    including inputs, generated/optimized outputs, model name, and token metrics.
    """
    __tablename__ = "prompt_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "generate" or "optimize"
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    generated_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    optimized_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tokens_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_after: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_saved: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-3-flash-preview")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_prompt_history_created_desc", created_at.desc()),
        Index("ix_prompt_history_op_created", "operation_type", created_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<PromptHistory(id={self.id}, op='{self.operation_type}', model='{self.model_name}')>"

"""
persistence_service.py — Data access and business logic for Saved Prompts and History (Phase 6).

Implements:
- Parameterized CRUD operations on SavedPrompt.
- Search and filtering by category, operation type, and search keywords.
- Append-only audit recording in PromptHistory.
- Paginated retrieval and atomic deletion for history.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import PromptHistory, SavedPrompt
from app.schemas.persistence_schemas import (
    PromptHistoryCreate,
    SavedPromptCreate,
    SavedPromptUpdate,
)

logger = logging.getLogger("autoprompt.db")


# ── Saved Prompts Service ─────────────────────────────────────────────────────

def create_saved_prompt(db: Session, prompt_in: SavedPromptCreate) -> SavedPrompt:
    """Create and persist a new saved prompt."""
    record = SavedPrompt(
        title=prompt_in.title,
        content=prompt_in.content,
        category=prompt_in.category,
        operation_type=prompt_in.operation_type,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Created saved prompt | id=%d | op=%s", record.id, record.operation_type)
    return record


def get_saved_prompt(db: Session, prompt_id: int) -> Optional[SavedPrompt]:
    """Retrieve a single saved prompt by ID."""
    stmt = select(SavedPrompt).where(SavedPrompt.id == prompt_id)
    return db.scalars(stmt).first()


def list_saved_prompts(
    db: Session,
    search: Optional[str] = None,
    category: Optional[str] = None,
    operation_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[SavedPrompt]]:
    """
    List saved prompts with optional filtering, search, and pagination.
    Returns (total_count, items).
    """
    stmt = select(SavedPrompt)
    count_stmt = select(func.count(SavedPrompt.id))

    filters = []
    if isinstance(category, str) and category.strip():
        filters.append(SavedPrompt.category == category.strip())
    if isinstance(operation_type, str) and operation_type.strip():
        filters.append(SavedPrompt.operation_type == operation_type.strip())
    if isinstance(search, str) and search.strip():
        search_pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                SavedPrompt.title.ilike(search_pattern),
                SavedPrompt.content.ilike(search_pattern),
            )
        )

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    safe_limit = max(1, min(limit if isinstance(limit, int) else 50, 100))
    safe_offset = max(0, offset if isinstance(offset, int) else 0)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(SavedPrompt.created_at.desc()).limit(safe_limit).offset(safe_offset)
    ).all()

    return total, list(items)


def update_saved_prompt(
    db: Session, prompt_id: int, update_in: SavedPromptUpdate
) -> Optional[SavedPrompt]:
    """Update fields of an existing saved prompt."""
    record = get_saved_prompt(db, prompt_id)
    if not record:
        return None

    if update_in.title is not None:
        record.title = update_in.title
    if update_in.content is not None:
        record.content = update_in.content
    if update_in.category is not None:
        record.category = update_in.category

    db.commit()
    db.refresh(record)
    logger.info("Updated saved prompt | id=%d", record.id)
    return record


def delete_saved_prompt(db: Session, prompt_id: int) -> bool:
    """Delete a saved prompt by ID."""
    record = get_saved_prompt(db, prompt_id)
    if not record:
        return False

    db.delete(record)
    db.commit()
    logger.info("Deleted saved prompt | id=%d", prompt_id)
    return True


# ── Prompt History Service ────────────────────────────────────────────────────

def record_history(db: Session, history_in: PromptHistoryCreate) -> PromptHistory:
    """
    Append an execution entry into prompt_history.
    Called automatically on successful Generate or Optimize operations.
    """
    record = PromptHistory(
        operation_type=history_in.operation_type,
        original_input=history_in.original_input,
        generated_output=history_in.generated_output,
        optimized_output=history_in.optimized_output,
        tokens_before=history_in.tokens_before,
        tokens_after=history_in.tokens_after,
        tokens_saved=history_in.tokens_saved,
        model_name=history_in.model_name,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(
        "Recorded prompt history | id=%d | op=%s | model=%s",
        record.id,
        record.operation_type,
        record.model_name,
    )
    return record


def list_history(
    db: Session,
    operation_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[PromptHistory]]:
    """List history entries with pagination."""
    stmt = select(PromptHistory)
    count_stmt = select(func.count(PromptHistory.id))

    if isinstance(operation_type, str) and operation_type.strip():
        stmt = stmt.where(PromptHistory.operation_type == operation_type.strip())
        count_stmt = count_stmt.where(PromptHistory.operation_type == operation_type.strip())

    safe_limit = max(1, min(limit if isinstance(limit, int) else 20, 100))
    safe_offset = max(0, offset if isinstance(offset, int) else 0)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(PromptHistory.created_at.desc()).limit(safe_limit).offset(safe_offset)
    ).all()

    return total, list(items)


def get_history_item(db: Session, history_id: int) -> Optional[PromptHistory]:
    """Retrieve a single history entry by ID."""
    stmt = select(PromptHistory).where(PromptHistory.id == history_id)
    return db.scalars(stmt).first()


def delete_history_item(db: Session, history_id: int) -> bool:
    """Delete a single history entry by ID."""
    record = get_history_item(db, history_id)
    if not record:
        return False

    db.delete(record)
    db.commit()
    logger.info("Deleted history entry | id=%d", history_id)
    return True


def clear_history(db: Session) -> int:
    """Delete all history records. Returns the number of records removed."""
    total_before = db.scalar(select(func.count(PromptHistory.id))) or 0
    db.query(PromptHistory).delete()
    db.commit()
    logger.info("Cleared all prompt history | deleted_count=%d", total_before)
    return total_before

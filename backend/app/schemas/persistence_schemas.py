"""
persistence_schemas.py — Pydantic schemas for Saved Prompts and Prompt History (Phase 6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Saved Prompts Schemas ─────────────────────────────────────────────────────

class SavedPromptBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Human-readable title for the prompt")
    content: str = Field(..., min_length=1, max_length=50000, description="Full prompt text content")
    category: Optional[str] = Field(None, max_length=100, description="Optional domain category (e.g. Coding, Business)")
    operation_type: Literal["generate", "optimize"] = Field("generate", description="Source operation type")

    @field_validator("title", "content", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Field cannot be empty or whitespace only")
        return v


class SavedPromptCreate(SavedPromptBase):
    pass


class SavedPromptUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1, max_length=50000)
    category: Optional[str] = Field(None, max_length=100)

    @field_validator("title", "content", mode="before")
    @classmethod
    def strip_whitespace_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Field cannot be empty string")
        return v


class SavedPromptResponse(SavedPromptBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SavedPromptListResponse(BaseModel):
    total: int
    items: list[SavedPromptResponse]
    limit: int
    offset: int


# ── Prompt History Schemas ────────────────────────────────────────────────────

class PromptHistoryCreate(BaseModel):
    operation_type: Literal["generate", "optimize"]
    original_input: str = Field(..., min_length=1, max_length=50000)
    generated_output: Optional[str] = Field(None, max_length=50000)
    optimized_output: Optional[str] = Field(None, max_length=50000)
    tokens_before: Optional[int] = None
    tokens_after: Optional[int] = None
    tokens_saved: Optional[int] = None
    model_name: str = "gemini-3-flash-preview"


class PromptHistoryResponse(BaseModel):
    id: int
    operation_type: str
    original_input: str
    generated_output: Optional[str]
    optimized_output: Optional[str]
    tokens_before: Optional[int]
    tokens_after: Optional[int]
    tokens_saved: Optional[int]
    model_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromptHistoryListResponse(BaseModel):
    total: int
    items: list[PromptHistoryResponse]
    limit: int
    offset: int


# ── Generic Action Responses ──────────────────────────────────────────────────

class ActionMessageResponse(BaseModel):
    success: bool
    message: str
    id: Optional[int] = None
    deleted_count: Optional[int] = None

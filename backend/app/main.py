"""
main.py — AutoPrompt FastAPI application entry point.

Endpoints:
----------
Diagnostics:
GET  /health            — Liveness probe (no external calls)
GET  /api/test-gemini   — Diagnostics probe for the Gemini API

Prompt Operations:
POST /api/generate      — Generates a structured prompt from an idea
POST /api/optimize      — Optimizes a prompt for clarity and efficiency
POST /api/count-tokens  — Counts tokens in a given text string

Saved Prompts (Phase 6 Persistence):
POST   /api/saved-prompts       — Save a prompt
GET    /api/saved-prompts       — List saved prompts with search/filtering
GET    /api/saved-prompts/{id}   — Retrieve single saved prompt
PUT    /api/saved-prompts/{id}   — Update saved prompt
DELETE /api/saved-prompts/{id}   — Delete saved prompt

Prompt History (Phase 6 Persistence):
GET    /api/history             — List prompt history with pagination
GET    /api/history/{id}        — Retrieve single history record
DELETE /api/history/{id}        — Delete single history record
DELETE /api/history             — Clear all history
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db, init_db
from app.schemas.persistence_schemas import (
    ActionMessageResponse,
    PromptHistoryCreate,
    PromptHistoryListResponse,
    PromptHistoryResponse,
    SavedPromptCreate,
    SavedPromptListResponse,
    SavedPromptResponse,
    SavedPromptUpdate,
)
from app.schemas.prompt_schemas import (
    GenerateRequest,
    GenerateResponse,
    OptimizeRequest,
    OptimizeResponse,
    TokenCountRequest,
    TokenCountResponse,
)
from app.services.gemini_service import (
    count_tokens,
    generate_prompt,
    optimize_prompt,
    test_gemini_connection,
)
from app.services.persistence_service import (
    clear_history,
    create_saved_prompt,
    delete_history_item,
    delete_saved_prompt,
    get_history_item,
    get_saved_prompt,
    list_history,
    list_saved_prompts,
    record_history,
    update_saved_prompt,
)

logger = logging.getLogger("autoprompt.api")


# ── Lifespan Context Manager (Database Initialization) ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database schema safely on application startup."""
    try:
        init_db()
    except Exception as exc:
        logger.error("Failed to initialize database on startup: %s", exc)
    yield


# ── Application Instance ──────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AutoPrompt Backend API — Production endpoints for prompt generation, "
        "optimization, accurate token measurement, and local SQLite persistence."
    ),
    # Interactive API docs are enabled only in DEBUG mode.
    # Set DEBUG=false in production to suppress endpoint enumeration.
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── CORS Middleware (approved local development origins only) ─────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",   # VS Code Live Server / Local dev server
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


# ── Error Status Mapping ──────────────────────────────────────────────────────
ERROR_HTTP_STATUS: dict[str, int] = {
    "api_key_not_found": status.HTTP_503_SERVICE_UNAVAILABLE,
    "api_key_invalid":   status.HTTP_503_SERVICE_UNAVAILABLE,
    "quota_exceeded":    status.HTTP_503_SERVICE_UNAVAILABLE,
    "rate_limit":        status.HTTP_503_SERVICE_UNAVAILABLE,
    "network":           status.HTTP_503_SERVICE_UNAVAILABLE,
    "timeout":           status.HTTP_503_SERVICE_UNAVAILABLE,
    "model_not_found":   status.HTTP_503_SERVICE_UNAVAILABLE,
    "invalid_response":  status.HTTP_502_BAD_GATEWAY,
    "unknown":           status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _resolve_status_code(result: dict) -> int:
    """Returns appropriate HTTP status based on success and standardized error_code."""
    if result.get("success"):
        return status.HTTP_200_OK
    error_code = result.get("error_code")
    return ERROR_HTTP_STATUS.get(error_code, status.HTTP_503_SERVICE_UNAVAILABLE)


# ── Diagnostics Endpoints ─────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Diagnostics"],
    summary="Liveness and configuration probe",
    description="Returns backend server health and environment status without making external provider calls.",
)
def health_check() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Python version and OS platform removed to reduce server fingerprinting surface.
            "gemini_key_configured": settings.has_gemini_key,
            "gemini_model": settings.GEMINI_MODEL,
        },
    )


@app.get(
    "/api/test-gemini",
    tags=["Diagnostics"],
    summary="Gemini API connectivity verification",
    description="Sends a lightweight verification request to Google Gemini to test API key and model validity.",
)
def test_gemini() -> JSONResponse:
    result = test_gemini_connection()
    return JSONResponse(status_code=_resolve_status_code(result), content=result)


# ── Production AI Endpoints ───────────────────────────────────────────────────

@app.post(
    "/api/generate",
    response_model=GenerateResponse,
    tags=["Prompt Services"],
    summary="Generate a structured system prompt",
    description=(
        "Takes a task description or idea and generates a comprehensive, production-ready "
        "prompt with persona, context, objective, instructions, deliverables, and guardrails."
    ),
)
def api_generate_prompt(
    payload: GenerateRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    kwargs = {
        "user_idea": payload.user_idea,
        "mode": payload.mode,
        "category": payload.category,
        "role": payload.role,
        "objective": payload.objective,
        "context": payload.context,
        "constraints": payload.constraints,
        "output_format": payload.output_format,
    }
    if payload.language is not None:
        kwargs["language"] = payload.language
    result = generate_prompt(**kwargs)

    # Automatically record in history on success
    if result.get("success"):
        try:
            record_history(
                db,
                PromptHistoryCreate(
                    operation_type="generate",
                    original_input=payload.user_idea,
                    generated_output=result.get("generated_prompt"),
                    tokens_before=result.get("input_tokens"),
                    tokens_after=result.get("output_tokens"),
                    model_name=result.get("model", settings.GEMINI_MODEL),
                ),
            )
        except Exception as exc:
            logger.warning("Failed to auto-record history entry for generate: %s", exc)

    return JSONResponse(status_code=_resolve_status_code(result), content=result)


@app.post(
    "/api/optimize",
    response_model=OptimizeResponse,
    tags=["Prompt Services"],
    summary="Optimize an existing prompt",
    description=(
        "Refines an existing prompt for clarity, structural rigor, and token efficiency "
        "while strictly preserving user intent and avoiding hallucinated data schemas."
    ),
)
def api_optimize_prompt(
    payload: OptimizeRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    kwargs = {
        "original_prompt": payload.original_prompt,
        "mode": payload.mode,
        "optimization_instructions": payload.optimization_instructions,
        "strategy": payload.strategy,
    }
    if payload.language is not None:
        kwargs["language"] = payload.language
    result = optimize_prompt(**kwargs)

    # Automatically record in history on success
    if result.get("success"):
        try:
            record_history(
                db,
                PromptHistoryCreate(
                    operation_type="optimize",
                    original_input=payload.original_prompt,
                    optimized_output=result.get("optimized_prompt"),
                    tokens_before=result.get("original_tokens"),
                    tokens_after=result.get("optimized_tokens"),
                    tokens_saved=result.get("tokens_saved"),
                    model_name=result.get("model", settings.GEMINI_MODEL),
                ),
            )
        except Exception as exc:
            logger.warning("Failed to auto-record history entry for optimize: %s", exc)

    return JSONResponse(status_code=_resolve_status_code(result), content=result)


@app.post(
    "/api/count-tokens",
    response_model=TokenCountResponse,
    tags=["Token Services"],
    summary="Measure token count",
    description="Counts the exact number of tokens in the provided text using Gemini's official tokenizer.",
)
def api_count_tokens(payload: TokenCountRequest) -> JSONResponse:
    if not settings.has_gemini_key:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "token_count": 0,
                "model": settings.GEMINI_MODEL,
                "error_code": "api_key_not_found",
                "error_message": "No API key configured.",
            },
        )

    count = count_tokens(payload.text)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "token_count": count,
            "model": settings.GEMINI_MODEL,
            "error_code": None,
            "error_message": None,
        },
    )


# ── Saved Prompts Endpoints (Phase 6) ─────────────────────────────────────────

@app.post(
    "/api/saved-prompts",
    response_model=SavedPromptResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Saved Prompts"],
    summary="Create a new saved prompt",
)
def api_create_saved_prompt(
    payload: SavedPromptCreate,
    db: Session = Depends(get_db),
) -> SavedPromptResponse:
    record = create_saved_prompt(db, payload)
    return SavedPromptResponse.model_validate(record)


@app.get(
    "/api/saved-prompts",
    response_model=SavedPromptListResponse,
    tags=["Saved Prompts"],
    summary="List saved prompts with optional filtering, search, and pagination",
)
def api_list_saved_prompts(
    search: Optional[str] = None,
    category: Optional[str] = None,
    operation_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> SavedPromptListResponse:
    safe_limit = max(1, min(limit if isinstance(limit, int) else 50, 100))
    safe_offset = max(0, offset if isinstance(offset, int) else 0)
    safe_search = search if isinstance(search, str) else None
    safe_category = category if isinstance(category, str) else None
    safe_op = operation_type if isinstance(operation_type, str) else None

    total, items = list_saved_prompts(
        db,
        search=safe_search,
        category=safe_category,
        operation_type=safe_op,
        limit=safe_limit,
        offset=safe_offset,
    )
    return SavedPromptListResponse(
        total=total,
        items=[SavedPromptResponse.model_validate(item) for item in items],
        limit=safe_limit,
        offset=safe_offset,
    )


@app.get(
    "/api/saved-prompts/{prompt_id}",
    response_model=SavedPromptResponse,
    tags=["Saved Prompts"],
    summary="Retrieve a single saved prompt by ID",
)
def api_get_saved_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
) -> SavedPromptResponse:
    record = get_saved_prompt(db, prompt_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved prompt with ID {prompt_id} not found",
        )
    return SavedPromptResponse.model_validate(record)


@app.put(
    "/api/saved-prompts/{prompt_id}",
    response_model=SavedPromptResponse,
    tags=["Saved Prompts"],
    summary="Update an existing saved prompt",
)
def api_update_saved_prompt(
    prompt_id: int,
    payload: SavedPromptUpdate,
    db: Session = Depends(get_db),
) -> SavedPromptResponse:
    record = update_saved_prompt(db, prompt_id, payload)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved prompt with ID {prompt_id} not found",
        )
    return SavedPromptResponse.model_validate(record)


@app.delete(
    "/api/saved-prompts/{prompt_id}",
    response_model=ActionMessageResponse,
    tags=["Saved Prompts"],
    summary="Delete a saved prompt by ID",
)
def api_delete_saved_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
) -> ActionMessageResponse:
    deleted = delete_saved_prompt(db, prompt_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved prompt with ID {prompt_id} not found",
        )
    return ActionMessageResponse(
        success=True,
        message=f"Saved prompt with ID {prompt_id} was successfully deleted",
        id=prompt_id,
    )


# ── Prompt History Endpoints (Phase 6) ────────────────────────────────────────

@app.get(
    "/api/history",
    response_model=PromptHistoryListResponse,
    tags=["Prompt History"],
    summary="List prompt execution history with pagination",
)
def api_list_history(
    operation_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> PromptHistoryListResponse:
    safe_limit = max(1, min(limit if isinstance(limit, int) else 20, 100))
    safe_offset = max(0, offset if isinstance(offset, int) else 0)
    safe_op = operation_type if isinstance(operation_type, str) else None

    total, items = list_history(
        db,
        operation_type=safe_op,
        limit=safe_limit,
        offset=safe_offset,
    )
    return PromptHistoryListResponse(
        total=total,
        items=[PromptHistoryResponse.model_validate(item) for item in items],
        limit=safe_limit,
        offset=safe_offset,
    )


@app.get(
    "/api/history/{history_id}",
    response_model=PromptHistoryResponse,
    tags=["Prompt History"],
    summary="Retrieve a single history entry by ID",
)
def api_get_history_item(
    history_id: int,
    db: Session = Depends(get_db),
) -> PromptHistoryResponse:
    record = get_history_item(db, history_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History record with ID {history_id} not found",
        )
    return PromptHistoryResponse.model_validate(record)


@app.delete(
    "/api/history/{history_id}",
    response_model=ActionMessageResponse,
    tags=["Prompt History"],
    summary="Delete a single history entry by ID",
)
def api_delete_history_item(
    history_id: int,
    db: Session = Depends(get_db),
) -> ActionMessageResponse:
    deleted = delete_history_item(db, history_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History record with ID {history_id} not found",
        )
    return ActionMessageResponse(
        success=True,
        message=f"History record with ID {history_id} was successfully deleted",
        id=history_id,
    )


@app.delete(
    "/api/history",
    response_model=ActionMessageResponse,
    tags=["Prompt History"],
    summary="Clear all prompt history records",
)
def api_clear_history(
    db: Session = Depends(get_db),
) -> ActionMessageResponse:
    deleted_count = clear_history(db)
    return ActionMessageResponse(
        success=True,
        message=f"Successfully cleared all history records ({deleted_count} items removed)",
        deleted_count=deleted_count,
    )

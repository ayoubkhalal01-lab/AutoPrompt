# AutoPrompt — Production Backend API (Phase 6.0)

FastAPI production backend for the AutoPrompt platform.  
Orchestrates prompt generation, optimization, exact token measurement powered by Google Gemini (`gemini-3-flash-preview`), and local SQLite persistence for saved prompts and execution history.

---

## Architecture Overview

- **Framework**: FastAPI + Python 3.14
- **ORM & Database**: SQLAlchemy 2.0 + SQLite (`autoprompt.db`) with WAL mode
- **AI SDK**: Official Google GenAI SDK (`google-genai` 2.x)
- **Model**: `gemini-3-flash-preview` (configurable via `GEMINI_MODEL`)
- **Validation**: Strict Pydantic models with defensive string normalization
- **Resilience**: Bounded exponential retries for transient errors, explicit timeouts, and standardized error mapping
- **Observability**: Structured telemetry under `autoprompt.ai` logger with zero secret or prompt leaks
- **Security**: Strict CORS locked to `http://localhost:5500` and `http://127.0.0.1:5500`

---

## Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py                  ← Centralized settings loaded from .env
│   ├── main.py                    ← FastAPI app & route definitions with CORS
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py              ← SQLAlchemy ORM models (SavedPrompt, PromptHistory)
│   │   └── session.py             ← Engine factory, session maker, init_db()
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── persistence_schemas.py ← Pydantic contracts for saved prompts & history
│   │   └── prompt_schemas.py      ← Pydantic request & response contracts
│   └── services/
│       ├── __init__.py
│       ├── gemini_service.py      ← Standardized AI service engine
│       └── persistence_service.py ← Data access & query filters for SQLite
├── reports/
│   ├── PHASE_5_3A_API_REPORT.md
│   ├── PHASE_5_3B_INTEGRATION_REPORT.md
│   ├── PHASE_5_4_INTEGRATION_REPORT.md
│   ├── PHASE_5_5_EVALUATION_REPORT.md
│   ├── PHASE_6_PERSISTENCE_REPORT.md
│   ├── PHASE_7_1_FINAL_FUNCTIONAL_TESTING_REPORT.md
│   ├── PHASE_7_2_RESPONSIVE_CROSS_BROWSER_REPORT.md
│   ├── PHASE_7_3_SECURITY_AUDIT_REPORT.md
│   ├── PHASE_7_4_PERFORMANCE_REPORT.md
│   ├── PHASE_7_5_RELEASE_HANDOVER_REPORT.md
│   ├── evaluation_results.json
│   └── live_integration_results.json
├── tests/
│   ├── evaluation/
│   │   ├── dataset.py             ← 16 curated benchmark prompts across 8 categories
│   │   ├── evaluator.py           ← Multi-dimensional quality rubric
│   │   ├── run_benchmark.py       ← Benchmark execution script
│   │   ├── test_evaluation_framework.py
│   │   └── test_prompt_regression.py
│   ├── test_ai_architecture_reliability.py  ← AI resilience & retry tests
│   ├── test_api_endpoints.py                ← AI endpoint & schema tests
│   ├── test_frontend_integration.py         ← Frontend integration contracts
│   ├── test_live_functional_integration.py  ← Live Gemini diagnostics
│   ├── test_persistence_api.py              ← Persistence CRUD & query tests
│   ├── test_persistence_smoke.py            ← End-to-end smoke tests
│   └── verify_real_browser.py               ← Headless Chrome CDP verification
├── autoprompt.db                  ← Local SQLite database
├── .env                           ← Local environment file (NEVER committed)
├── .env.example                   ← Configuration template
├── .gitignore                     ← Protects keys, DB, and venv from Git
├── README.md                      ← This documentation
└── requirements.txt               ← Backend dependencies
```

---

## Configuration Variables (`.env`)

| Variable | Default Value | Description |
|---|:---:|---|
| `GEMINI_API_KEY` | *(Required)* | Google AI Studio API key. Never share or commit. |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Target Gemini model identifier. |
| `GEMINI_TIMEOUT_SECONDS` | `30.0` | Explicit client timeout in seconds. |
| `GEMINI_MAX_RETRIES` | `2` | Maximum retry attempts for transient errors only. |
| `GEMINI_TEMPERATURE` | `0.2` | Model sampling temperature. |
| `HOST` | `127.0.0.1` | Local server host bind address. |
| `PORT` | `8000` | Local server port. |
| `DEBUG` | `false` | FastAPI debug mode flag. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## Installation & Setup

From the repository root (`e:\prompauto`):

### 1 — Virtual Environment Setup

```powershell
python -m venv backend\venv
backend\venv\Scripts\Activate.ps1
```

### 2 — Install Dependencies

```powershell
pip install -r backend\requirements.txt
```

### 3 — Configure Environment

```powershell
Copy-Item backend\.env.example backend\.env
```

Open `backend\.env` and set your key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
```

Get a free API key at → [Google AI Studio](https://aistudio.google.com/app/apikey).

---

## Running the Backend Server

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Health check**: `http://127.0.0.1:8000/health`
- **Interactive OpenAPI docs**: `http://127.0.0.1:8000/docs`
- **ReDoc documentation**: `http://127.0.0.1:8000/redoc`

---

## Running Frontend with Backend

In a separate terminal, serve the frontend on port 5500 (matching CORS configuration):

```powershell
cd autoprompt-prototype
python -m http.server 5500
```

Open `http://127.0.0.1:5500` in your web browser or use VS Code Live Server.

---

## Automated Test Suites

AutoPrompt includes **129 automated unit, integration, evaluation, and persistence tests** (100% passing):

```powershell
$env:PYTHONPATH="e:\prompauto\backend"
.\backend\venv\Scripts\python.exe -m pytest e:\prompauto\backend\tests -q
```

### Test Suite Breakdown:
- `tests/test_persistence_api.py` (23 tests): Saved Prompts CRUD, search, pagination, transactional rollbacks.
- `tests/test_persistence_smoke.py` (25 tests): HTML loading order, modal bindings, badge counts, engine restart persistence.
- `tests/test_ai_architecture_reliability.py` (18 tests): Configuration validation, error classification taxonomy, bounded transient retries, timeout enforcement, response normalization, and logging privacy.
- `tests/test_api_endpoints.py` (25 tests): Schema constraints, min/max character lengths, mode validation, negative token delta calculations, and endpoint handlers.
- `tests/test_frontend_integration.py` (14 tests): CORS origin restrictions, mode preservation, token counting, responsive layout rules, light/dark theme persistence, and duplicate submission locking.
- `tests/evaluation/test_evaluation_framework.py` (14 tests): Evaluator rubrics and benchmark dataset integrity.
- `tests/evaluation/test_prompt_regression.py` (17 tests): Quality regression tests across 8 categories.
- `tests/test_live_functional_integration.py`: Live diagnostics connecting to Google Gemini.
- `tests/verify_real_browser.py`: End-to-end Chrome DevTools Protocol verification.

---

## API Endpoints Reference

### 1. POST `/api/generate`
Generates a structured, production-ready system prompt from a user idea.

### 2. POST `/api/optimize`
Refines an existing prompt for clarity, conciseness, and token efficiency while strictly preserving user intent.

### 3. POST `/api/count-tokens`
Measures exact token counts using Google Gemini's official tokenizer.

### 4. Saved Prompts Endpoints (Phase 6)
- `POST /api/saved-prompts` — Create a new saved prompt with custom title and category.
- `GET /api/saved-prompts` — List saved prompts with search, category filtering, operation filtering, and pagination.
- `GET /api/saved-prompts/{id}` — Retrieve a single saved prompt.
- `PUT /api/saved-prompts/{id}` — Update title, content, or category.
- `DELETE /api/saved-prompts/{id}` — Delete a saved prompt.

### 5. Prompt History Endpoints (Phase 6)
- `GET /api/history` — List execution audit history with pagination and operation filter.
- `GET /api/history/{id}` — Retrieve an audit record with token metrics.
- `DELETE /api/history/{id}` — Delete a single history record.
- `DELETE /api/history` — Clear all execution history.

---

## Error Handling & Status Codes

All errors return predictable JSON structures:

```json
{
  "success": false,
  "error_code": "quota_exceeded",
  "error_message": "API quota exceeded. Please wait a moment or check your Google AI Studio plan."
}
```

| Error Code | HTTP Status | Meaning |
|---|:---:|---|
| `api_key_not_found` | 503 | Server missing `GEMINI_API_KEY` configuration |
| `api_key_invalid` | 503 | Provided key is invalid or unauthenticated |
| `quota_exceeded` | 503 | Provider daily quota or project limit reached |
| `rate_limit` | 503 | Too many requests in short period |
| `network` | 503 | Network connection failure communicating with Gemini |
| `timeout` | 503 | Request timed out after configured threshold |
| `model_not_found` | 503 | Configured model name unavailable |
| `invalid_response` | 502 | Provider returned empty, null, or filtered output |
| `unknown` | 500 | Unhandled internal exception |

---

## Testing & Quality Assurance (Phase 7 Validation)

- **Total Automated Test Suites**: **183 / 183 Passing Tests**
  - **Backend Unit & Integration Suite**: 129 tests (`backend/tests/`)
  - **Functional QA Suite**: 44 tests (`scratch/test_final_functional_qa.py`)
  - **Security Hardening Suite**: 10 tests (`scratch/test_security_audit.py`)
- **Performance Benchmarks**:
  - `/health` throughput: > 51,700 RPS (0.018 ms mean latency)
  - Concurrent load throughput: 6,743 RPS (5 workers), 2,874 RPS (50 workers) with 0.0% error rate
  - SQLite point lookups: 1.07 ms at 1,000 records (WAL mode enabled)
- **Security Audit**: 0 critical/high vulnerabilities; strict CORS; server-side secret isolation; parameterized queries; XSS prevention.


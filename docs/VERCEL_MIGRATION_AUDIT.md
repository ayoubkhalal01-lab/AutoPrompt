# AutoPrompt — Vercel Architecture & Compatibility Audit (Phase 8.5-A)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Auditor**: Senior Cloud Architect, Python Backend Engineer & Vercel Specialist  
**Status**: Read-Only Architecture & Compatibility Assessment  
**Target Platform**: Vercel Serverless Platform (Python Serverless Functions + Global Edge Network)

---

## 1. Executive Summary

This audit evaluates the feasibility, architectural requirements, limitations, and operational risks of migrating the AutoPrompt application from its current unified Docker/Nginx/SQLite deployment to a fully managed **Vercel Serverless Architecture**.

### Key Audit Conclusions
1. **Frontend Compatibility**: **100% Compatible**. The Vanilla ES6+ HTML/CSS SPA (`autoprompt-prototype`) requires zero framework refactoring and deploys directly to Vercel's Global Edge Network with zero build steps.
2. **FastAPI Engine Compatibility**: **Compatible with Adaptations**. FastAPI runs on Vercel Python Functions (ASGI-wrapped). However, execution models change from long-running stateful processes to stateless, ephemeral Lambda invocations.
3. **Database Incompatibility (Critical)**: **SQLite is Incompatible with Vercel Serverless**. Vercel functions have an ephemeral, read-only filesystem (only `/tmp` is writable, up to 512MB, wiped between invocations and unshared across concurrent instances). Persistence requires migrating to a cloud-managed PostgreSQL provider (e.g. Neon Serverless Postgres or Supabase).
4. **Execution Timeout Constraint (Hobby Plan)**: **Requires Configuration Tuning**. Vercel Hobby plan enforces a hard **15-second maximum function execution timeout**. Default Gemini timeout (30.0s) and multi-attempt retry backoff must be tuned down to `< 12.0s` to prevent unhandled `504 Gateway Timeout` errors.
5. **Connection Pooling Requirement**: Serverless scale-up will exhaust standard PostgreSQL connection pools. A connection pooler (e.g. PgBouncer / Neon pooled connection string) is mandatory.

---

## 2. Current Architecture vs. Target Vercel Architecture

```
CURRENT ARCHITECTURE (Phase 8.1 - 8.4)          TARGET VERCEL ARCHITECTURE (Phase 8.5)
┌───────────────────────────────────────┐       ┌───────────────────────────────────────┐
│ Host Server (Linux VPS - Ubuntu)      │       │ Vercel Global Edge Network            │
│                                       │       │                                       │
│ ┌───────────────────────────────────┐ │       │ ┌───────────────────────────────────┐ │
│ │ Nginx (Ports 80/443, SSL/TLS)     │ │       │ │ Edge CDN / Static Assets          │ │
│ │ Serves HTML/CSS/JS + Gzip         │ │       │ │ autoprompt-prototype/ (Global Any)│ │
│ └─────────────────┬─────────────────┘ │       │ └─────────────────┬─────────────────┘ │
│                   │ Reverse Proxy     │       │                   │ Path Rewrites     │
│                   ▼                   │       │                   ▼                   │
│ ┌───────────────────────────────────┐ │       │ ┌───────────────────────────────────┐ │
│ │ FastAPI + Uvicorn (Docker)        │ │       │ │ Vercel Python Function            │ │
│ │ Long-Running Python Process       │ │       │ │ Stateless /api/index.py (ASGI)    │ │
│ └─────────────────┬─────────────────┘ │       │ └─────────┬───────────────────┬─────┘ │
│                   │ POSIX File IO     │       └───────────┼───────────────────┼───────┘
│                   ▼                   │                   │                   │
│ ┌───────────────────────────────────┐ │                   ▼                   ▼
│ │ SQLite Database (WAL Mode)        │ │       ┌──────────────────┐ ┌──────────────────┐
│ │ /app/data/autoprompt.db           │ │       │ Google Gemini 3  │ │ Cloud PostgreSQL │
│ └───────────────────────────────────┘ │       │ Flash API        │ │ (Neon Serverless)│
└───────────────────────────────────────┘       └──────────────────┘ └──────────────────┘
```

---

## 3. Detailed Component Compatibility Matrix

| Application Component | Current State | Target Vercel State | Compatibility | Required Modification |
| :--- | :--- | :--- | :---: | :--- |
| **Static Frontend** | Pure HTML/CSS/JS in `autoprompt-prototype/` | Vercel Static Asset CDN | **100% Compatible** | Configured via `vercel.json` rewrites; zero build changes. |
| **API Client (`API_BASE_URL`)** | Supports empty string `''` for same-origin | Same-origin relative URLs (`/api/...`) | **100% Compatible** | Verified in Phase 8.3 (`window.AUTOPROMPT_API_URL = ''`). |
| **FastAPI Core Application** | `app.main:app` (FastAPI instance) | Vercel Serverless Function (`api/index.py`) | **Compatible** | Create root wrapper `api/index.py` exporting `app`. |
| **Pydantic Schemas** | Pydantic v2 validation contracts | Pydantic v2 | **100% Compatible** | Runs cleanly under Python 3.12 runtime on Vercel. |
| **Google Gemini SDK** | `google-genai 2.34.0` via HTTPS | `google-genai 2.34.0` via HTTPS | **Compatible** | Bound timeout to ≤ 12s to respect Vercel Hobby limits. |
| **Database Storage** | SQLite (`autoprompt.db`) in WAL mode | Serverless PostgreSQL (Neon / Supabase) | **INCOMPATIBLE** | Replace SQLite with PostgreSQL URI & add `psycopg2-binary`. |
| **Database Models** | SQLAlchemy 2.0 ORM (`models.py`) | SQLAlchemy 2.0 ORM (`models.py`) | **100% Compatible** | Table models use standard types; 100% Postgres-ready. |
| **Database Migrations** | `init_db()` called in `lifespan` | Explicit migration script / idempotent init | **Compatible** | Adjust connection pooling to `NullPool` for serverless. |
| **Nginx Reverse Proxy** | Custom `nginx.conf` with rate limiting | `vercel.json` routing + Vercel Edge Firewall | **Replaced** | Rate limiting moves to Vercel Firewall or application level. |
| **SSL / HTTPS / Domain** | Certbot Let's Encrypt automated daemon | Vercel Automatic SSL & Anycast DNS | **Simplified** | Automatic SSL handled natively by Vercel Edge. |

---

## 4. Incompatible Assumptions & Required Adaptations

### A. The Ephemeral Filesystem (SQLite Elimination)
- **Current Assumption**: The application writes to `/app/data/autoprompt.db` on a persistent local block volume.
- **Vercel Reality**: Vercel Serverless Functions execute in AWS Lambda micro-VMs. The filesystem is read-only except for `/tmp`. Any SQLite file placed in `/tmp` is destroyed when the function scales to zero or moves to another compute node. Concurrency will immediately cause database divergence or lock errors.
- **Adaptation**:
  1. Migrate persistence from SQLite to a serverless-friendly PostgreSQL provider (e.g. **Neon Serverless Postgres**).
  2. Add `psycopg2-binary` (or `pg8000`) to dependencies.
  3. Update `DATABASE_URL` in Vercel Environment Variables to point to the pooled PostgreSQL connection string.

### B. Function Lifespan & Connection Pooling
- **Current Assumption**: FastAPI runs as a persistent daemon with a persistent SQLAlchemy connection pool (`pool_pre_ping=True`).
- **Vercel Reality**: Each incoming concurrent request can spin up an isolated serverless function instance. If 50 concurrent requests arrive, 50 distinct instances attempt to connect to the database. Standard database connection pools will rapidly exceed PostgreSQL connection limits (`max_connections`).
- **Adaptation**:
  1. Configure SQLAlchemy in serverless mode using `NullPool` or a pool size of 1 with fast recycling.
  2. Utilize **Neon's connection pooler** (PgBouncer on port 6543) via the `-pooler` connection string.

### C. Function Execution Timeouts (Vercel Hobby Plan)
- **Current Assumption**: Backend permits up to `30.0s` for complex Gemini prompts, with up to 2 retries (total potential wait > 45s).
- **Vercel Reality**: **Vercel Hobby plan has a hard 15-second timeout limit** per serverless function execution. If an execution reaches 15.01s, Vercel kills the process and returns an unbranded `504 Gateway Timeout` error to the browser.
- **Adaptation**:
  - In Vercel production environment:
    ```ini
    GEMINI_TIMEOUT_SECONDS=10.0
    GEMINI_MAX_RETRIES=1
    ```
  - This ensures that even with a retry, total execution completes within ~12 seconds, leaving a 3-second safety margin before Vercel's 15-second cutoff.

---

## 5. Safe SQLite to PostgreSQL Migration Strategy

To preserve all existing user data (Saved Prompts and Prompt History) during migration:

### A. Schema Parity Verification
The SQLAlchemy models in `backend/app/db/models.py` utilize generic cross-database types:
- `Integer`, `String(255)`, `Text`, `DateTime(timezone=True)`.
- Composite indexes: `ix_saved_prompts_category_op`, `ix_saved_prompts_created_desc`, `ix_prompt_history_op_created`.
- **Finding**: Zero DDL modifications are required. SQLAlchemy's `Base.metadata.create_all()` will generate identical relational schemas in PostgreSQL.

### B. Data Extraction & Transfer Procedure
An automated, non-destructive migration script (`scratch/migrate_sqlite_to_postgres.py`) will be developed:
1. **Extract**: Connect to local `autoprompt.db` in read-only mode and serialize all `SavedPrompt` and `PromptHistory` records.
2. **Schema Init**: Connect to target PostgreSQL database and run `Base.metadata.create_all(bind=pg_engine)`.
3. **Load**: Insert extracted records into PostgreSQL inside a single atomic transaction.
4. **Sequence Reset**: Update PostgreSQL auto-incrementing identity sequences (`SELECT setval('saved_prompts_id_seq', (SELECT MAX(id) FROM saved_prompts));`).
5. **Verify**: Assert record counts, string integrity, and timestamp parity between SQLite and PostgreSQL.

---

## 6. Project Structure & Vercel File Blueprint

To deploy to Vercel without altering existing local development or Docker workflows, the repository structure will incorporate three lightweight Vercel integration files:

```
prompauto/
├── api/
│   └── index.py             # Serverless entrypoint wrapping FastAPI app
├── vercel.json              # Rewrites, routing, and header configurations
├── requirements.txt         # Root requirements for Vercel Python builder
├── autoprompt-prototype/    # Static frontend (untouched)
├── backend/                 # Backend codebase (untouched)
│   ├── app/
│   │   ├── main.py
│   │   └── ...
└── ...
```

### `vercel.json` Specification
```json
{
  "version": 2,
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" },
    { "source": "/health", "destination": "/api/index.py" },
    { "source": "/(.*)", "destination": "/autoprompt-prototype/$1" }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    },
    {
      "source": "/css/(.*)",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
    },
    {
      "source": "/js/(.*)",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
    }
  ]
}
```

### `api/index.py` Serverless Entrypoint
```python
import sys
from pathlib import Path

# Ensure backend modules are in Python import path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
```

---

## 7. Cost & Free-Tier Limitations Analysis

### A. Vercel Hobby Plan (Free)
*Official Reference: [Vercel Pricing & Limits](https://vercel.com/docs/limits/plans)*
- **Monthly Cost**: **$0.00 / month**.
- **Bandwidth**: **100 GB / month** (AutoPrompt transfer is ~46 KB/visit; 100 GB permits > 2,000,000 page views).
- **Serverless Execution**: **100 GB-hours / month**. At ~1.8s per AI request and 512MB RAM allocation, 100 GB-hours permits > 350,000 requests/month.
- **Function Execution Timeout**: **15 seconds** (Hard limit).
- **Cold Start Latency**: ~300 ms to 800 ms on first request after idle period.
- **Overages Policy**: Hard stop upon reaching allowances; no unexpected charges.

### B. Database Provider Options (PostgreSQL Free Tiers)

#### Option 1: Neon Serverless Postgres (*RECOMMENDED*)
*Official Reference: [Neon Pricing Documentation](https://neon.tech/pricing)*
- **Monthly Cost**: **$0.00 / month** (Free Tier).
- **Storage**: **0.5 GiB (~512 MB)** (Sufficient for > 150,000 saved prompts and history entries).
- **Compute Allowance**: 100 Compute Hours / month with automatic scale-to-zero when idle.
- **Connection Pooling**: Native built-in PgBouncer endpoint on port 6543 (supports up to 10,000 concurrent serverless connections).
- **Scale-to-Zero Wakeup Latency**: ~500 ms cold start if database is suspended.
- **Inactivity Deletion**: None (active free projects do not expire).

#### Option 2: Supabase Postgres
*Official Reference: [Supabase Pricing](https://supabase.com/pricing)*
- **Monthly Cost**: **$0.00 / month** (Free Tier).
- **Storage**: 500 MB.
- **Critical Limitation**: **Free projects pause after 7 days of inactivity**. Requires manual restoration in the dashboard or an automated weekly heartbeat ping.

---

## 8. Security & Environment Variable Isolation

1. **Secret Storage**: `GEMINI_API_KEY` and `DATABASE_URL` are stored exclusively in Vercel Project Settings (`Settings -> Environment Variables`) and marked as **Encrypted Secrets**.
2. **Zero Client Exposure**: Vercel separates static hosting from serverless functions. Environment variables configured for the backend function are completely inaccessible to frontend browser requests.
3. **Production Mode Suppression**: Set `DEBUG=false` in Vercel environment variables, automatically disabling Swagger/ReDoc and suppressing internal tracebacks.
4. **Diagnostics Endpoint Gating**: In `main.py`, `/api/test-gemini` is already protected by `settings.DEBUG`. With `DEBUG=false`, it returns HTTP 404.

---

## 9. Migration Risks & Mitigations

| Risk Factor | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Vercel 15s Timeout Cutoff** | Gemini request terminated with HTTP 504 | Set `GEMINI_TIMEOUT_SECONDS=10.0` and `GEMINI_MAX_RETRIES=1` in Vercel environment. |
| **Serverless DB Connection Spikes** | PostgreSQL connection exhaustion | Use Neon's `-pooler` connection string with SQLAlchemy `NullPool`. |
| **Neon Cold Start Latency** | Initial request takes ~2.5s (500ms DB wake + 2s Gemini) | Implement loading indicators; subsequent requests run warm in < 2s. |
| **Database Data Divergence** | Missing prompts during migration | Perform cutover during low traffic; run verification script before DNS switch. |

---

## 10. Ordered Implementation Roadmap (Phase 8.5 Sequence)

```
┌────────────────────────────────────────────────────────┐
│ Phase 8.5-A: Compatibility & Migration Audit (Done)    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.5-B: Database Migration & Parity Script        │
│ Schema creation • Data extraction • Parity validation  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.5-C: Vercel Project Structure & Packaging      │
│ vercel.json • api/index.py • requirements.txt (psycopg)│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.5-D: Local Serverless Simulation & Tests       │
│ Vercel CLI dev test • 183 automated tests verification │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.5-E: Vercel Deployment & Production Smoke Test │
│ Secret injection • Live deployment • End-to-end test   │
└────────────────────────────────────────────────────────┘
```

---

## 11. Final Audit Verdict

# **READY FOR MIGRATION (WITH ARCHITECTURAL ADAPTATIONS)**

The AutoPrompt application is fully viable for Vercel deployment with two mandatory adaptations:
1. Transitioning persistence from SQLite to **Neon Serverless PostgreSQL** (with connection pooling).
2. Tuning `GEMINI_TIMEOUT_SECONDS` to `10.0s` to conform strictly to Vercel's 15-second Hobby timeout window.

All existing application code, prompt quality, security hardening, and test suites remain preserved.

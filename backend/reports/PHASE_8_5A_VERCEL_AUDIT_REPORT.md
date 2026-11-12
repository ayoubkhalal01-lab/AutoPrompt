# AutoPrompt — Phase 8.5-A: Vercel Compatibility & Migration Audit Report

**Date**: November 5, 2026  
**Auditor / Cloud Architect**: Senior Cloud Architect, Python Backend Engineer & Vercel Specialist  
**Target Application**: AutoPrompt v1.0.0  
**Target Cloud Platform**: Vercel Serverless (Global Edge Network + Python Serverless Functions)  
**Deliverables Produced**: `docs/VERCEL_MIGRATION_AUDIT.md`, `backend/reports/PHASE_8_5A_VERCEL_AUDIT_REPORT.md`  
**Current Test Coverage**: **183 / 183 Automated Tests Passing (100%)**  
**Final Audit Verdict**: **READY FOR MIGRATION (WITH ARCHITECTURAL ADAPTATIONS)**

---

## 1. Executive Summary

Phase 8.5-A conducted a thorough, read-only architectural audit to determine the technical requirements, limitations, cost implications, and migration steps necessary to deploy AutoPrompt on **Vercel**.

### Key Findings
1. **Frontend Architecture**: **100% Compatible**.
   - The application frontend is a pure Vanilla ES6+, CSS3, and HTML5 single-page application.
   - It requires zero compilation, zero bundlers, and zero framework shims.
   - It deploys natively to Vercel's Global Anycast Edge CDN with instant cache invalidation and immutable asset caching.
2. **FastAPI Engine Compatibility**: **Compatible with ASGI Wrapper**.
   - Vercel officially supports Python 3.12 Serverless Functions.
   - FastAPI integrates seamlessly via a standard ASGI entrypoint (`api/index.py`) using Vercel's automated request bridge.
3. **Storage Incompatibility (Critical Finding)**: **SQLite Cannot Be Used on Vercel Serverless**.
   - Vercel execution environments are ephemeral AWS Lambda micro-VMs with read-only root filesystems.
   - While `/tmp` is writable (up to 512MB), files in `/tmp` are discarded between cold starts and are never shared across concurrent instances.
   - Running SQLite on Vercel results in data loss whenever functions scale to zero or scale out across multiple containers.
   - **Resolution**: Persistence must transition to a cloud-hosted, serverless-compatible PostgreSQL provider (**Neon Serverless Postgres**).
4. **Execution Timeout Constraint**:
   - Vercel's free **Hobby plan** enforces a strict **15-second maximum function timeout**.
   - AutoPrompt's current default Gemini timeout (30.0s) and retry backoff must be tuned down (`GEMINI_TIMEOUT_SECONDS=10.0`, `GEMINI_MAX_RETRIES=1`) to guarantee responses return well before the 15-second limit.
5. **Connection Pooling Requirement**:
   - Serverless bursts spin up multiple ephemeral function instances simultaneously.
   - Direct PostgreSQL connections will exhaust database connection limits. A pooled connection string (PgBouncer on port 6543) and SQLAlchemy `NullPool` are mandatory.

---

## 2. Current vs. Target Architecture

```
┌───────────────────────────────────────┐       ┌───────────────────────────────────────┐
│        CURRENT (Docker / VPS)         │       │          TARGET (Vercel)              │
├───────────────────────────────────────┤       ├───────────────────────────────────────┤
│ • Nginx Reverse Proxy (Ports 80/443)  │  ──▶  │ • Vercel Global Edge CDN (Anycast)    │
│ • Long-running Uvicorn process        │  ──▶  │ • Ephemeral Python 3.12 Function      │
│ • Local SQLite database (/app/data/)  │  ──▶  │ • Neon Serverless PostgreSQL (Cloud) │
│ • Certbot Let's Encrypt renewal loop  │  ──▶  │ • Vercel Automated Anycast TLS        │
│ • Host-level .env secret file         │  ──▶  │ • Vercel Encrypted Environment Vars  │
└───────────────────────────────────────┘       └───────────────────────────────────────┘
```

---

## 3. Compatible vs. Incompatible Components

| Component | Status | Compatibility Analysis |
| :--- | :---: | :--- |
| **Frontend SPA** (`autoprompt-prototype/`) | **PASS** | 100% compatible. Static assets served globally via Vercel Edge. |
| **Same-Origin Relative URLs** | **PASS** | 100% compatible. Frontend already supports `window.AUTOPROMPT_API_URL = ''`. |
| **FastAPI REST Endpoints** | **PASS** | 100% compatible. `/api/generate`, `/api/optimize`, `/api/count-tokens`, `/api/saved-prompts`, `/api/history`, and `/health` map cleanly. |
| **Pydantic Validation Contracts** | **PASS** | 100% compatible. Pydantic v2 runs seamlessly in Python 3.12 runtime. |
| **SQLAlchemy ORM Models** (`models.py`) | **PASS** | 100% compatible. Table definitions use cross-database SQLAlchemy types (`Integer`, `String`, `Text`, `DateTime`). |
| **Google Gemini SDK** (`google-genai`) | **PASS** | 100% compatible over outbound HTTPS. |
| **SQLite Persistent Storage** | **FAIL** | **Incompatible with serverless**. Ephemeral filesystem causes data wipe on cold start. |
| **Docker Compose / Nginx Configs** | **N/A** | Superseded by `vercel.json` rewrites and Vercel edge infrastructure. |

---

## 4. Required Modifications & File Additions

To support Vercel without altering or breaking existing local development or Docker workflows:

### A. New Files to Create (Zero Impact on Existing Docker Stack)
1. **`vercel.json`** (Root):
   - Configures rewrites: `/api/(.*)` -> `api/index.py`, `/health` -> `api/index.py`, `/(.*)` -> `autoprompt-prototype/$1`.
   - Injects security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `HSTS`).
   - Configures immutable caching headers for `/css/*` and `/js/*`.
2. **`api/index.py`** (Root):
   - Serverless entrypoint function importing the FastAPI `app` from `backend.app.main`.
3. **`requirements.txt`** (Root):
   - Root dependency manifest containing backend dependencies plus `psycopg2-binary>=2.9.9` (or `pg8000`) for PostgreSQL connectivity.

### B. Defensive Code Adjustments
1. **`backend/app/db/session.py`**:
   - Connection string protocol normalization: Automatically replace legacy `postgres://` prefixes with `postgresql://`.
   - Serverless connection pooling: Apply `NullPool` or `pool_size=1` when running under PostgreSQL to prevent connection leaks during serverless scale-up.
2. **`backend/app/config.py`**:
   - Bind `DATABASE_URL` default to environment variable (already implemented).

---

## 5. Database Migration Plan (SQLite to PostgreSQL)

To guarantee that 100% of user data (Saved Prompts and Execution History) is preserved:

1. **Automated Migration Script** (`scratch/migrate_sqlite_to_postgres.py`):
   - Reads existing records from local `autoprompt.db`.
   - Connects to the target PostgreSQL database via `DATABASE_URL`.
   - Automatically executes `Base.metadata.create_all(bind=pg_engine)` to establish identical schema and composite indexes.
   - Inserts all `saved_prompts` and `prompt_history` records inside a single atomic transaction.
   - Resets PostgreSQL auto-incrementing ID sequences:
     ```sql
     SELECT setval('saved_prompts_id_seq', COALESCE((SELECT MAX(id) FROM saved_prompts), 1));
     SELECT setval('prompt_history_id_seq', COALESCE((SELECT MAX(id) FROM prompt_history), 1));
     ```
2. **Data Parity Verification**:
   - Script performs automated count and content verification between SQLite source and PostgreSQL target.

---

## 6. Cost & Free-Tier Limitations Analysis

### A. Vercel Hobby Plan (Free)
*Reference: [Vercel Limits Documentation](https://vercel.com/docs/limits/plans)*
- **Monthly Cost**: **$0.00 / month**.
- **Bandwidth**: **100 GB / month** (Permits > 2,000,000 visits/month for AutoPrompt's 46 KB gzip payload).
- **Serverless Execution Time**: **100 GB-hours / month**. At ~1.8s per request and 512MB RAM, supports > 350,000 AI operations/month.
- **Maximum Execution Timeout**: **15 seconds** (Strict hard limit).
- **Cold Start Latency**: ~300 ms to 800 ms on first request after idle period.
- **Overages**: Hard stop when limit is reached; zero unexpected credit card charges.

### B. Database Provider: Neon Serverless Postgres (*Recommended Provider*)
*Reference: [Neon Pricing & Free Tier](https://neon.tech/pricing)*
- **Monthly Cost**: **$0.00 / month** (Free Tier).
- **Storage Allowance**: **0.5 GiB (~512 MB)** (Holds > 150,000 prompts/history entries).
- **Compute Allowance**: 100 Compute Hours / month.
- **Scale-to-Zero**: Suspends compute when idle; wakes in ~500 ms on incoming query.
- **Built-in Connection Pooling**: Native PgBouncer endpoint on port 6543 handles up to 10,000 concurrent serverless connections.
- **Inactivity Deletion**: None (Active free tier databases do not expire).

---

## 7. Security & Secrets Management Assessment

1. **Secret Storage**:
   - `GEMINI_API_KEY` and `DATABASE_URL` stored exclusively in Vercel Project Settings as **Encrypted Environment Variables**.
   - Completely invisible to frontend client requests.
2. **CORS Elimination**:
   - Vercel serves frontend and `/api` on the exact same domain. Same-origin routing eliminates CORS preflight latency.
3. **Production Mode Enforcement**:
   - `DEBUG=false` in Vercel variables automatically disables `/docs` and `/redoc`.
   - `/api/test-gemini` returns 404 in production.

---

## 8. Migration Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Vercel 15s Timeout** | Function killed with HTTP 504 on slow Gemini calls | Set `GEMINI_TIMEOUT_SECONDS=10.0` and `GEMINI_MAX_RETRIES=1` in Vercel environment. |
| **PostgreSQL Connection Exhaustion** | `FATAL: too many connections` on traffic bursts | Use Neon's `-pooler` connection string with SQLAlchemy `NullPool`. |
| **Neon Cold Start Delay** | First prompt after idle takes ~2.5s total | Frontend loading state already communicates progress; subsequent calls run warm. |
| **Data Loss During Cutover** | Missing saved prompts | Execute automated data migration script with count verification before DNS switch. |

---

## 9. Ordered Implementation Roadmap

1. **Phase 8.5-B**: Database Migration & Parity Script (Create and verify `migrate_sqlite_to_postgres.py`).
2. **Phase 8.5-C**: Vercel Packaging (Create `vercel.json`, `api/index.py`, and root `requirements.txt`).
3. **Phase 8.5-D**: Local Serverless Simulation & Regression Verification (Verify 183 automated tests).
4. **Phase 8.5-E**: Deployment & Production Acceptance Testing (Deploy to Vercel and verify live HTTPS).

---

## 10. Final Audit Verdict

# **READY FOR MIGRATION (WITH ARCHITECTURAL ADAPTATIONS)**

AutoPrompt v1.0.0 is technically ready for migration to Vercel, provided that:
1. An external serverless PostgreSQL database (Neon Free Tier) is provisioned for persistent storage.
2. Gemini timeout settings are tuned to conform to Vercel's 15-second Hobby timeout window.

All 183 existing tests, core AI prompt generation quality, token metrics, and security controls will be preserved.

# AutoPrompt — Vercel Deployment Guide

> **Phase 8.5-C / 8.5-F** — Vercel Project Structure, Packaging & Monorepo Import Fix  
> Companion to `docs/PRODUCTION_ARCHITECTURE.md` and `docs/PRODUCTION_DEPLOYMENT_ROADMAP.md`

---

## ⚠️ Monorepo Import — Critical Import Instructions

When you import `https://github.com/ayoubkhalal01-lab/AutoPrompt` into Vercel, the
importer detects **three applications** in the repository:

| Detected | Cause |
|----------|-------|
| `Root: AutoPrompt` | `vercel.json` + root `requirements.txt` |
| `backend/: FastAPI` | `backend/requirements.txt` contains `fastapi` |
| `api/: FastAPI` | `api/index.py` exports a FastAPI `app` |

**You must select `Root: AutoPrompt` with Root Directory `./`.**  
Never select `backend/` or `api/` as the root — those are sub-components, not
standalone deployable applications.

### Step-by-step Vercel Import

1. Go to [vercel.com/new](https://vercel.com/new) → **Import Git Repository**
2. Find `ayoubkhalal01-lab/AutoPrompt` and click **Import**
3. When prompted to select a project, choose **Root: AutoPrompt**
4. Under **Root Directory**, confirm it shows `./` (the repo root)
5. Under **Framework Preset**, leave it as **Other** (not FastAPI)
6. Leave **Build Command** and **Output Directory** blank (controlled by `vercel.json`)
7. Click **Deploy** (add environment variables first — see Step 3 below)

> **Why does Vercel detect 3 projects?**  
> Vercel scans up to depth-2 subdirectories for framework markers (a `requirements.txt`
> containing `fastapi`, or a Python file exporting `app = FastAPI()`). This is cosmetic —
> selecting `Root` is the documented Vercel workflow for single-project repositories that
> contain framework code in subdirectories. The root `vercel.json` already correctly
> routes all traffic through one unified deployment.

---

## Overview

AutoPrompt can be deployed entirely on Vercel:

| Component | Vercel mechanism |
|-----------|-----------------|
| Frontend  | Static file serving (`autoprompt-prototype/`) |
| Backend API | Python Serverless Function (`api/index.py`) |
| Database  | External — Neon Serverless PostgreSQL (free tier) |
| AI        | Google Gemini API (unchanged) |

All API routes (`/api/*`, `/health`) are proxied to the FastAPI application via
`vercel.json` rewrites. Frontend assets are served directly from
`autoprompt-prototype/`. The same domain serves both, so no CORS configuration
is required for production.

---

## Prerequisites

- [Vercel account](https://vercel.com) (Hobby plan — free)
- [Neon account](https://neon.tech) (free tier — 0.5 GiB, built-in PgBouncer)
- Vercel CLI installed: `npm i -g vercel` (or use the web dashboard)
- Google Gemini API key

---

## Repository Structure (Vercel-relevant files)

```
prompauto/
├── api/
│   └── index.py          ← Vercel Python function entrypoint
├── autoprompt-prototype/ ← Static frontend served at /
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
├── backend/              ← FastAPI application (imported by api/index.py)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   └── ...
│   └── requirements.txt  ← Docker deployment
├── requirements.txt      ← Vercel Python build dependencies (root)
└── vercel.json           ← Routing, headers, function config
```

---

## Step 1: Provision Neon PostgreSQL

1. Sign in to [console.neon.tech](https://console.neon.tech)
2. Create a new project → choose the region nearest your users
3. Note the **Connection string** from the dashboard:
   ```
   postgresql://user:pass@ep-xxx-yyy.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. For serverless use the **pooled connection** (port **6543**):
   ```
   postgresql://user:pass@ep-xxx-yyy.us-east-2.aws.neon.tech:6543/neondb?sslmode=require
   ```

---

## Step 2: Migrate Existing Data (if any)

```powershell
# From repo root
$env:PYTHONPATH="e:\prompauto\backend"
$env:SOURCE_DATABASE_URL="sqlite:///./backend/autoprompt.db"
$env:TARGET_DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech:6543/neondb?sslmode=require"

# Dry run first
python scratch/migrate_sqlite_to_postgres.py --dry-run

# Live migration
python scratch/migrate_sqlite_to_postgres.py
```

If the SQLite database is empty, skip this step — Vercel will create the schema
automatically on first startup via `Base.metadata.create_all()`.

---

## Step 3: Configure Vercel Environment Variables

In the Vercel dashboard → Project Settings → Environment Variables, add:

| Variable | Value | Environment |
|----------|-------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@ep-xxx.neon.tech:6543/neondb?sslmode=require` | Production |
| `GEMINI_API_KEY` | `your_gemini_api_key` | Production |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Production |
| `GEMINI_TIMEOUT_SECONDS` | `10.0` | Production |
| `GEMINI_MAX_RETRIES` | `2` | Production |
| `GEMINI_TEMPERATURE` | `0.2` | Production |
| `DEBUG` | `false` | Production |
| `LOG_LEVEL` | `WARNING` | Production |
| `ALLOWED_ORIGINS` | `https://your-project.vercel.app` | Production |

> **Important:** Set `GEMINI_TIMEOUT_SECONDS=10.0` — Vercel Hobby plan enforces
> a **15-second hard timeout** per function invocation. The original default of
> `30.0` seconds would cause gateway timeouts on slow Gemini responses.

> **Never** set `DEBUG=true` in Production — this exposes Swagger UI and the
> `/api/test-gemini` diagnostic endpoint.

---

## Step 4: Deploy with Vercel CLI

```bash
# From repo root
vercel login
vercel --prod
```

Or connect your GitHub repository in the Vercel dashboard for automatic
deployments on push.

**Expected build output:**
```
✓ Building...
✓ Python function: api/index.py
✓ Static files: autoprompt-prototype/
✓ Deployment complete: https://your-project.vercel.app
```

---

## Step 5: Smoke Tests

After deployment, run these checks:

```bash
BASE="https://your-project.vercel.app"

# 1. Health check
curl -s "$BASE/health" | python -m json.tool
# Expected: {"status":"ok","database":"connected",...}

# 2. Frontend loads
curl -s -o /dev/null -w "%{http_code}" "$BASE/"
# Expected: 200

# 3. Token counter
curl -s -X POST "$BASE/api/count-tokens" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello world"}' | python -m json.tool
# Expected: {"token_count": N, ...}

# 4. Saved prompts list
curl -s "$BASE/api/saved-prompts" | python -m json.tool
# Expected: {"items":[], "total":0, ...}

# 5. Swagger NOT exposed
curl -s -o /dev/null -w "%{http_code}" "$BASE/docs"
# Expected: 404
```

---

## Routing Reference

| Request | Vercel rewrite | Handler |
|---------|---------------|---------|
| `GET /` | → `autoprompt-prototype/index.html` | Static |
| `GET /css/*` | → `autoprompt-prototype/css/*` | Static |
| `GET /js/*` | → `autoprompt-prototype/js/*` | Static |
| `GET /health` | → `api/index.py` | FastAPI |
| `POST /api/generate` | → `api/index.py` | FastAPI |
| `POST /api/optimize` | → `api/index.py` | FastAPI |
| `POST /api/count-tokens` | → `api/index.py` | FastAPI |
| `GET /api/saved-prompts` | → `api/index.py` | FastAPI |
| `GET /api/history` | → `api/index.py` | FastAPI |

---

## Limitations vs VPS Deployment

| Concern | Vercel Hobby | VPS (Docker) |
|---------|-------------|--------------|
| Function timeout | 15 s hard limit | Configurable |
| Concurrent requests | Edge-distributed | Single server |
| File system | Read-only (no SQLite) | Persistent volume |
| Cold starts | ~300–800 ms (Python) | Zero (always-on) |
| Custom domain TLS | Automatic (Vercel) | Certbot (manual) |
| Cost | Free | ~\$4–6/month |

---

## Rollback to Docker

The VPS Docker deployment is unaffected by this Vercel setup.  
To roll back, simply stop using Vercel and redeploy Docker Compose as documented
in `docs/DOCKER_SETUP.md`. The database migration script can be re-run in reverse
(PostgreSQL → SQLite) by swapping SOURCE/TARGET URLs, though this requires
a custom export script (not provided — Neon Console supports CSV export).

---

## Related Documentation

- [`docs/VERCEL_MIGRATION_AUDIT.md`](VERCEL_MIGRATION_AUDIT.md) — Full compatibility audit
- [`docs/PRODUCTION_ARCHITECTURE.md`](PRODUCTION_ARCHITECTURE.md) — VPS reference architecture
- [`docs/DOCKER_SETUP.md`](DOCKER_SETUP.md) — Docker deployment guide
- [`scratch/migrate_sqlite_to_postgres.py`](../scratch/migrate_sqlite_to_postgres.py) — Migration script

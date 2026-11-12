# AutoPrompt — Phase 8.5-F: Vercel Monorepo Import Fix Report

**Date:** 2026-11-12  
**Commit:** `c1e994e`  
**Branch:** `main`  
**Repository:** `https://github.com/ayoubkhalal01-lab/AutoPrompt`

---

## 1. Root Cause Analysis

When importing `https://github.com/ayoubkhalal01-lab/AutoPrompt` into Vercel, the
importer showed three detected applications:

| Detected Label | Root Cause |
|---------------|------------|
| `Root: AutoPrompt` | Root `vercel.json` + root `requirements.txt` + root `index.html` |
| `backend/: FastAPI` | `backend/requirements.txt` contains `fastapi`; Vercel scans depth-2 dirs |
| `api/: FastAPI` | `api/index.py` exports a FastAPI `app` ASGI callable |

**Additional routing bug:** The root `index.html` was a 3-line redirect stub
(`<meta http-equiv="refresh" content="0; url=autoprompt-prototype/index.html">`).
On Vercel, **static files take precedence over rewrites** — so visiting `/` served
this redirect page instead of the actual frontend at `autoprompt-prototype/index.html`.

---

## 2. Changes Made

### 2.1 Deleted: `index.html` (root redirect stub)
- **Why:** Was intercepting all requests to `/` before any rewrite could fire.
- **Impact:** None — it only redirected to `autoprompt-prototype/index.html`. With it
  gone, the new explicit rewrite in `vercel.json` handles `/` correctly.
- **Docker:** Unaffected — Docker/Nginx serves from `autoprompt-prototype/` directly.

### 2.2 Updated: `vercel.json` — explicit `/` rewrite
Added a dedicated rewrite rule for the root path **before** the catch-all:

```json
{ "source": "/",     "destination": "/autoprompt-prototype/index.html" },
{ "source": "/(.*)", "destination": "/autoprompt-prototype/$1" }
```

This ensures `GET /` reliably serves the SPA entry point regardless of static-file
precedence rules.

### 2.3 New: `backend/vercel.json` — suppression marker
Created `backend/vercel.json` with `"framework": null` and `"ignoreCommand": "exit 0"`.

This tells Vercel's import scanner that `backend/` is **not a deployable project**,
suppressing the `backend/: FastAPI` entry in the import UI.

> **Note:** `backend/` is NOT added to `.vercelignore` — doing so would prevent Vercel
> from uploading the directory, breaking the runtime import in `api/index.py`.

### 2.4 Updated: `docs/VERCEL_SETUP.md`
Added a prominent `⚠️ Monorepo Import — Critical Import Instructions` section at the
top of the guide, explaining:
- Why three projects are detected
- Step-by-step selection of `Root: AutoPrompt` with `Root Directory: ./`
- Why `backend/` and `api/` must NOT be selected as the root

---

## 3. Final Vercel Import Instructions

> Follow these steps exactly when importing from GitHub into Vercel.

1. Go to [vercel.com/new](https://vercel.com/new) → **Import Git Repository**
2. Find `ayoubkhalal01-lab/AutoPrompt` and click **Import**
3. When the import UI shows detected projects, **select `Root: AutoPrompt`**
4. Confirm **Root Directory** = `./` (the repo root)
5. **Framework Preset** = `Other` (do not select FastAPI or any other framework)
6. Leave **Build Command** and **Output Directory** blank
7. Add environment variables (**before** clicking Deploy):

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql://user:pass@ep-xxx.neon.tech:6543/neondb?sslmode=require` |
| `GEMINI_API_KEY` | *(your Gemini API key)* |
| `GEMINI_MODEL` | `gemini-3-flash-preview` |
| `GEMINI_TIMEOUT_SECONDS` | `10.0` |
| `DEBUG` | `false` |
| `ALLOWED_ORIGINS` | `https://your-project.vercel.app` |

8. Click **Deploy**

---

## 4. Routing Verification

After the fix, the full routing table is:

| Request | Vercel rewrite | Handler |
|---------|---------------|---------| 
| `GET /` | → `/autoprompt-prototype/index.html` | Static SPA |
| `GET /css/*` | → `/autoprompt-prototype/css/*` | Static |
| `GET /js/*` | → `/autoprompt-prototype/js/*` | Static |
| `GET /assets/*` | → `/autoprompt-prototype/assets/*` | Static |
| `GET /health` | → `api/index.py` | FastAPI |
| `POST /api/generate` | → `api/index.py` | FastAPI |
| `POST /api/optimize` | → `api/index.py` | FastAPI |
| `POST /api/count-tokens` | → `api/index.py` | FastAPI |
| `GET /api/saved-prompts` | → `api/index.py` | FastAPI |
| `GET /api/history` | → `api/index.py` | FastAPI |

---

## 5. Test Results

All existing tests pass with zero regressions:

| Suite | Tests | Result |
|-------|-------|--------|
| Phase 8.5-D (simulation) | 65 | ✅ All pass |
| Phase 8.5-E (acceptance) | 25 | ✅ All pass |
| Backend unit/integration | 129 | ✅ All pass |
| **Total** | **219** | **✅ 219/219** |

---

## 6. What Was NOT Changed

- `backend/app/` — application code untouched
- `api/index.py` — serverless entrypoint untouched
- `backend/requirements.txt` — Docker requirements untouched
- `docker-compose.yml` / `docker-compose.prod.yml` — Docker deployment untouched
- `nginx/` — Nginx configuration untouched
- All database configuration — SQLite + PostgreSQL paths untouched

---

## 7. Git History

```
c1e994e fix(vercel): suppress subdirectory project detection, fix root routing
663f811 chore: prepare AutoPrompt for Vercel deployment
```

---

## 8. Limitations & Notes

- `api/: FastAPI` will still appear in Vercel's import UI. This is expected —
  Vercel detects `api/index.py` as a Python serverless function. The user must
  still select **Root: AutoPrompt**, not `api/`.
- The `backend/vercel.json` suppression marker works for the `backend/: FastAPI`
  entry. Vercel's behavior may vary across UI versions.
- For the Vercel CLI (`vercel deploy`), no selection dialog appears — it
  automatically uses the root `vercel.json`.

---

## 9. Status

**Phase 8.5-F: COMPLETE**  
Awaiting user authorization for Phase 8.5-G (Production deployment, if applicable).

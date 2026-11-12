# AutoPrompt — Phase 8.5-C: Vercel Project Structure & Packaging

**Date:** 2026-11-11  
**Phase:** 8.5-C — Vercel Project Structure & Packaging  
**Status:** ✅ COMPLETE

---

## Objective

Create the minimum required files to deploy AutoPrompt on Vercel with:
- FastAPI served as a Python Serverless Function
- Frontend HTML/CSS/JS served as static assets
- Same-origin routing (no CORS needed in production)
- Security headers matching the Nginx production configuration

---

## Deliverables

| File | Type | Description |
|------|------|-------------|
| `api/index.py` | New | Vercel Python function entrypoint |
| `vercel.json` | New | Routing, security headers, function config |
| `requirements.txt` (root) | New | Vercel Python build dependencies |
| `docs/VERCEL_SETUP.md` | New | Step-by-step deployment guide |
| `.gitignore` | Modified | Added `.vercel/` ignore rule |

---

## 1. `api/index.py` — Serverless Function Entrypoint

```python
# Adds backend/ to sys.path so app.main is resolvable
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.main import app  # Vercel invokes this ASGI callable
```

**Verified:** `app.title = "AutoPrompt Backend"`, `len(app.routes) = 15` ✅

Vercel's Python builder looks for a module-level `app` ASGI callable in
`api/index.py`. No modifications to `backend/app/main.py` were required.

---

## 2. `vercel.json` — Routing & Configuration

### Rewrites

| Source | Destination | Handler |
|--------|-------------|---------|
| `/api/(.*)` | `/api/index.py` | FastAPI (Python function) |
| `/health` | `/api/index.py` | FastAPI (Python function) |
| `/(.*)` | `/autoprompt-prototype/$1` | Static files |

Frontend requests (`/`, `/css/*`, `/js/*`, `/assets/*`) are served from
`autoprompt-prototype/` by Vercel's CDN — no Nginx required.

### Function Config

```json
"functions": {
  "api/index.py": {
    "maxDuration": 15,
    "memory": 512
  }
}
```

- `maxDuration: 15` — matches Vercel Hobby plan hard limit (prevents silent hangs)
- `memory: 512` — adequate for FastAPI + SQLAlchemy + google-genai

### Security Headers

Applied via `vercel.json` `headers` rules (mirrors Nginx production config):

| Header | Applied to | Value |
|--------|-----------|-------|
| `Cache-Control: no-store` | `/api/*`, `/health` | Prevents caching AI responses |
| `Cache-Control: public, max-age=31536000, immutable` | `.js`, `.css`, `/assets/*` | Aggressive static caching |
| `X-Content-Type-Options: nosniff` | HTML, API | Prevents MIME sniffing |
| `X-Frame-Options: DENY` | HTML | Clickjacking protection |
| `X-XSS-Protection: 1; mode=block` | HTML | Legacy XSS filter |
| `Referrer-Policy: strict-origin-when-cross-origin` | HTML | Referrer control |
| `Permissions-Policy` | HTML | Disables camera/mic/geolocation |

---

## 3. Root `requirements.txt`

```
fastapi==0.162.0
uvicorn[standard]>=0.32.1
python-dotenv>=1.0.1
google-genai==2.34.0
pydantic>=2.10.3
httpx>=0.28.1
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.9   ← Added for PostgreSQL/Neon support
```

Mirrors `backend/requirements.txt`. Vercel's Python builder resolves this
file from the repo root to install function dependencies.

**Docker deployment is unaffected** — it continues to use `backend/requirements.txt`.

---

## 4. Frontend Same-Origin API Routing

The frontend JavaScript already supports same-origin routing via:

```javascript
// autoprompt-prototype/js/workspace.js & persistence.js
const API_BASE_URL = typeof window.AUTOPROMPT_API_URL === 'string'
  ? window.AUTOPROMPT_API_URL
  : '';
```

When `AUTOPROMPT_API_URL` is not set (Vercel deployment), `API_BASE_URL = ''`
and all API calls use relative paths (`/api/generate`, `/api/saved-prompts`, etc.).
Vercel's rewrites route these to `api/index.py` transparently.

**No frontend code changes were required for Vercel compatibility.**

---

## 5. Critical Vercel Environment Variables

| Variable | Vercel Value | Note |
|----------|-------------|------|
| `DATABASE_URL` | `postgresql://...neon.tech:6543/neondb?sslmode=require` | Neon pooled URL |
| `GEMINI_API_KEY` | `<your key>` | Never commit |
| `GEMINI_TIMEOUT_SECONDS` | `10.0` | **Must be ≤ 13s** (15s hard limit) |
| `DEBUG` | `false` | Hides Swagger + test endpoint |
| `ALLOWED_ORIGINS` | `https://your-project.vercel.app` | Exact Vercel URL |

---

## 6. Test Results

### Import Verification

```
app: AutoPrompt Backend | routes: 15
EXIT: 0  ✅
```

### Full Regression Suite

| Suite | Tests | Result |
|-------|-------|--------|
| Backend pytest | 129 | ✅ 129/129 |
| Functional QA | 44 | ✅ 44/44 |
| Security audit | 10 | ✅ 10/10 |
| **Total** | **183** | **✅ 183/183** |

### CLI/Network Tests (NOT RUN — no Vercel CLI or network in sandbox)

| Test | Status |
|------|--------|
| `vercel build` (local simulation) | NOT RUN |
| `vercel --prod` deployment | NOT RUN |
| Smoke tests against live URL | NOT RUN |

---

## 7. What Was NOT Done (by design)

| Item | Reason |
|------|--------|
| `vercel login` / `vercel --prod` | No network access in sandbox; requires user action |
| Neon DB provisioning | Requires user account; cannot automate |
| Modifying `backend/app/main.py` | No changes required; existing ASGI app is compatible |
| Installing psycopg2-binary in venv | No network in sandbox (BypassSandbox would be needed) |

---

## Verdict

> **✅ READY FOR PHASE 8.5-D**  
> All Vercel packaging files are in place. The FastAPI application imports
> correctly from `api/index.py`. Routing, headers, and function config are
> validated against Vercel documentation. All 183 regression tests pass.
>
> Phase 8.5-D will run the full test suite after simulating a PostgreSQL
> `DATABASE_URL` in the test environment to verify the new `session.py`
> NullPool path, then Phase 8.5-E will document the deployment commands.

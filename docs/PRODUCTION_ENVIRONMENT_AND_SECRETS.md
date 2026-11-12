# AutoPrompt — Production Environment & Secrets Management Guide (Phase 8.4)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Author**: Senior DevOps Engineer & Application Security Specialist  
**Status**: Production Secrets & Runtime Configuration Specification

---

## 1. Overview & Security Principles

This document specifies the exact configuration, secret injection, key rotation, and audit procedures for AutoPrompt v1.0.0.

### Core Security Mandates
1. **Zero Secret Baking**: `GEMINI_API_KEY` is injected strictly at runtime via environment variables or protected `.env` files. Secrets are **never** committed to Git, baked into Docker image layers, or exposed to frontend JavaScript.
2. **Server-Side Isolation**: The AI API key is exclusively accessible to the backend Python process (`autoprompt-backend`). The frontend container, public reverse proxy, and client web browsers never receive or handle provider credentials.
3. **Production Mode Enforcement**: `DEBUG=false` is enforced in production to suppress interactive API documentation (`/docs`, `/redoc`), prevent schema enumeration, and sanitize error responses.
4. **Least-Privilege Storage**: SQLite persistent storage directories on the production host are locked with strict POSIX permissions (`chmod 700`, owned by non-root UID 10001).

---

## 2. Environment Variable Inventory

All variables consumed across the AutoPrompt stack are documented below:

| Variable Name | Required? | Default Value | Sensitivity | Component | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`GEMINI_API_KEY`** | **YES** | `""` | **CRITICAL SECRET** | Backend | Secret API authentication key from Google AI Studio. |
| **`GEMINI_MODEL`** | No | `gemini-3-flash-preview` | Low | Backend | Configured Gemini model. Fallback: `gemini-2.0-flash`. |
| **`GEMINI_TEMPERATURE`**| No | `0.7` | Low | Backend | Model sampling temperature (0.0 to 1.0). |
| **`GEMINI_TIMEOUT_SECONDS`**| No | `30.0` | Low | Backend | Maximum execution timeout for Gemini provider requests. |
| **`GEMINI_MAX_RETRIES`** | No | `2` | Low | Backend | Bounded retry attempts for transient network/quota errors. |
| **`DEBUG`** | No | `false` | Medium | Backend | Development flag. **Must be false in production.** |
| **`LOG_LEVEL`** | No | `INFO` | Low | Backend | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| **`HOST`** | No | `0.0.0.0` | Low | Backend | Network interface binding inside container. |
| **`PORT`** | No | `8000` | Low | Backend | Internal application port inside container. |
| **`DATABASE_URL`** | No | `sqlite:////app/data/autoprompt.db` | Medium | Backend | SQLAlchemy SQLite connection URI. |
| **`DOMAIN_NAME`** | No | `autoprompt.yourdomain.com` | Low | Nginx/Certbot | Fully qualified domain name for TLS certificate. |
| **`CERTBOT_EMAIL`** | No | `admin@yourdomain.com` | Low | Certbot | Admin contact email for Let's Encrypt notifications. |

---

## 3. Production Environment Setup

### A. Secret File Provisioning on Host Server
On the production host server (e.g. Ubuntu VPS), create the dedicated application directory and initialize the environment file:

```bash
# 1. Create secure application root
mkdir -p /opt/autoprompt
cd /opt/autoprompt

# 2. Copy the production environment template
cp .env.example .env

# 3. Lock filesystem permissions BEFORE adding secrets
chmod 600 /opt/autoprompt/.env
chown root:root /opt/autoprompt/.env
```

### B. Configuring the Production `.env` File
Edit `/opt/autoprompt/.env` and insert your live Google AI Studio key:

```ini
# Production Secret Configuration
GEMINI_API_KEY=AIzaSy...your_actual_live_key_here
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_TEMPERATURE=0.7
GEMINI_TIMEOUT_SECONDS=30.0
GEMINI_MAX_RETRIES=2
DEBUG=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////app/data/autoprompt.db
DOMAIN_NAME=autoprompt.yourdomain.com
CERTBOT_EMAIL=admin@yourdomain.com
```

---

## 4. Launching the Production Stack

Start the hardened multi-service Docker Compose stack:

```bash
# Launch production services in background
docker compose -f docker-compose.prod.yml up -d

# Verify container health and port bindings
docker compose -f docker-compose.prod.yml ps
```

Expected verification output:
```
NAME                 IMAGE                      COMMAND                  STATUS
autoprompt-backend   autoprompt-backend:1.0.0   "uvicorn app.main:ap…"   Up (healthy)
autoprompt-nginx     nginx:alpine-slim          "/docker-entrypoint.…"   Up (healthy)
autoprompt-certbot   certbot/certbot:latest     "/bin/sh -c 'trap ex…"   Up
```

> **Network Isolation Verification**: Run `docker compose -f docker-compose.prod.yml port backend 8000`. The output should be completely **empty**, confirming that the backend is reachable exclusively via Nginx on the internal bridge network.

---

## 5. Gemini API Key Rotation Procedure

When rotating the Google Gemini API key:
1. Generate a new API key in [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Update the `GEMINI_API_KEY` entry in `/opt/autoprompt/.env`:
   ```bash
   nano /opt/autoprompt/.env
   ```
3. Perform a zero-downtime rolling restart of the backend service:
   ```bash
   docker compose -f docker-compose.prod.yml restart backend
   ```
4. Verify backend health:
   ```bash
   curl -k https://127.0.0.1/health
   # Expected: {"status":"ok","gemini_key_configured":true,...}
   ```
5. Revoke the old API key in Google AI Studio once health is confirmed.

---

## 6. Verification & Leak Detection Checklist

Execute these checks after any configuration update:

### 1. Secret Leakage Verification
```bash
# Verify no keys appear in running environment strings of other containers
docker compose -f docker-compose.prod.yml exec nginx env | grep -i gemini || echo "PASS: Nginx has zero AI credentials"
docker compose -f docker-compose.prod.yml exec certbot env | grep -i gemini || echo "PASS: Certbot has zero AI credentials"
```

### 2. Frontend Asset Inspection
```bash
# Verify no API keys are baked into static JavaScript files
curl -s http://127.0.0.1/js/workspace.js | grep -i "AIza" || echo "PASS: No keys in workspace.js"
curl -s http://127.0.0.1/js/persistence.js | grep -i "AIza" || echo "PASS: No keys in persistence.js"
```

### 3. Public Schema Enumeration Suppression
```bash
# Verify Swagger UI and ReDoc return 404 in production
curl -s -o /dev/null -w "%{http_code}" https://127.0.0.1/docs
# Expected: 404
curl -s -o /dev/null -w "%{http_code}" https://127.0.0.1/redoc
# Expected: 404
```

### 4. Health Check Information Disclosure
```bash
# Confirm /health does not leak OS platform, python compiler, or secrets
curl -s https://127.0.0.1/health | grep -E "python|platform|AIza" || echo "PASS: Clean health response"
```

---

## 7. SQLite Storage Protection & Automated Backups

### Host Storage Permissions
The persistent named volume maps to host disk:
```bash
# Verify host volume permissions (owned by non-root UID 10001)
docker volume inspect autoprompt-sqlite-data
```

### Automated Nightly Backup Cron
Add the following job to host crontab (`sudo crontab -e`):
```bash
# Execute nightly at 03:00 UTC: Atomic non-blocking VACUUM INTO backup
0 3 * * * docker compose -f /opt/autoprompt/docker-compose.prod.yml exec -T backend python -c "from app.db.session import engine; engine.dispose(); import sqlite3, datetime; c = sqlite3.connect('/app/data/autoprompt.db'); c.execute(f\"VACUUM INTO '/app/data/backup_{datetime.datetime.now().strftime('%Y%m%d')}.db'\"); c.close()"
```

---

## 8. Troubleshooting Configuration Issues

| Error Message / Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `gemini_key_configured: false` | `GEMINI_API_KEY` is missing or contains default placeholder. | Ensure `.env` has valid key and run `docker compose -f docker-compose.prod.yml up -d backend`. |
| `HTTP 503 api_key_invalid` | The Google Gemini API key is expired, deleted, or mistyped. | Verify key in Google AI Studio; update `.env` and restart backend. |
| `HTTP 503 quota_exceeded` | Google AI Studio free tier limit reached (15 RPM or 1,500 RPD). | Wait for quota window reset. Free tier limits are non-billable. |
| `OperationalError: unable to open database file` | Volume mount permissions error. | Ensure directory `/app/data` has ownership `10001:10001`. |
| `HTTP 404 on /api/*` | Nginx reverse proxy configuration misaligned. | Check `docker compose -f docker-compose.prod.yml logs nginx`. |

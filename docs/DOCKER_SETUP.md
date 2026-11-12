# AutoPrompt — Docker Containerization & Setup Guide (Phase 8.2)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Author**: Senior DevOps Engineer  
**Status**: Containerization & Packaging Guide

---

## 1. Architecture Overview

AutoPrompt is packaged as two containerized services orchestrated via Docker Compose:
1. **`autoprompt-backend`**: FastAPI application running with Uvicorn (2 workers) on Python 3.12-slim. Configured with persistent SQLite storage, non-root user execution (`appuser`), and container health monitoring.
2. **`autoprompt-frontend`**: Lightweight Alpine Nginx container serving the static SPA assets (`index.html`, CSS, JS) with gzip compression and browser caching.

```
┌────────────────────────────────────────────────────────┐
│                   Docker Host Engine                   │
│                                                        │
│   ┌────────────────────────────────────────────────┐   │
│   │        Bridge Network: autoprompt-net          │   │
│   │                                                │   │
│   │  ┌───────────────────┐  ┌───────────────────┐  │   │
│   │  │    frontend       │  │     backend       │  │   │
│   │  │  nginx:alpine-slim│  │  python:3.12-slim │  │   │
│   │  │  Port 80          │  │  Port 8000        │  │   │
│   │  └────────┬──────────┘  └─────────┬─────────┘  │   │
│   └───────────┼───────────────────────┼────────────┘   │
│               │                       │                │
│    127.0.0.1:5500           127.0.0.1:8000             │
│               │                       │                │
│               ▼                       ▼                │
│     [ Local Host Port ]     [ Named Volume: ]          │
│                             [ autoprompt-data ]        │
│                             [   /app/data/    ]        │
└────────────────────────────────────────────────────────┘
```

---

## 2. Prerequisites

- **Docker Engine**: Version 24.0+ (or Docker Desktop on Windows/macOS).
- **Docker Compose**: Version 2.20+ (`docker compose`).
- **Google Gemini API Key**: Acquired from Google AI Studio.

---

## 3. Environment Configuration

The containers read configuration from environment variables or a local `.env` file located in `backend/.env`.

1. Copy the environment template:
   ```bash
   cp backend/.env.example backend/.env
   ```
2. Configure your secrets in `backend/.env`:
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   GEMINI_MODEL=gemini-3-flash-preview
   GEMINI_TEMPERATURE=0.7
   GEMINI_TIMEOUT_SECONDS=30.0
   GEMINI_MAX_RETRIES=2
   DEBUG=false
   LOG_LEVEL=INFO
   ```

> **Security Note**: Secrets are injected at runtime via Docker Compose `env_file` or environment flags. Secrets are **never baked** into Docker images. Both root `.dockerignore` and `backend/.dockerignore` strictly prevent accidental `.env` leakage into the build context.

---

## 4. Build & Run Commands

### A. Build the Images
To build both backend and frontend images using multi-stage builds:
```bash
docker compose build
```

To build individually:
```bash
# Build backend
docker build -t autoprompt-backend:1.0.0 ./backend

# Build frontend
docker build -t autoprompt-frontend:1.0.0 ./autoprompt-prototype
```

### B. Start the Containers
Start all services in detached mode:
```bash
docker compose up -d
```

### C. Verify Status & Health
Check container state and healthcheck status:
```bash
docker compose ps
```
Expected output:
```
NAME                 IMAGE                       COMMAND                  SERVICE    STATUS
autoprompt-backend   autoprompt-backend:1.0.0   "uvicorn app.main:ap…"   backend    Up (healthy)
autoprompt-frontend  autoprompt-frontend:1.0.0  "/docker-entrypoint.…"   frontend   Up (healthy)
```

Verify backend health probe:
```bash
curl http://127.0.0.1:8000/health
# Response: {"status":"ok","app":"AutoPrompt Backend API","version":"1.0.0",...}
```

Verify frontend static delivery:
```bash
curl -I http://127.0.0.1:5500/
# HTTP/1.1 200 OK
# Content-Type: text/html
```

### D. View Live Logs
```bash
# Tail all container logs
docker compose logs -f

# Tail backend service only
docker compose logs -f backend
```

### E. Stop the Containers
Stop services without deleting persistent data:
```bash
docker compose down
```

To stop services and remove volumes (Destructive — deletes SQLite database):
```bash
docker compose down -v
```

---

## 5. Persistent Storage & Backup Strategy

### A. Volume Mapping
- The SQLite database is written to container path `/app/data/autoprompt.db`.
- Managed by named volume `autoprompt-data`, which maps to Docker's host volume directory (e.g. `/var/lib/docker/volumes/autoprompt-sqlite-data/_data` on Linux).
- Data survives:
  - `docker compose stop` and `docker compose start`
  - `docker compose down` and `docker compose up`
  - Image rebuilds (`docker compose build`)
  - Container reboots and updates

### B. Performing Live SQLite Backups
Because SQLite runs in **Write-Ahead Logging (WAL)** mode, live backups can be executed safely without stopping the backend:

```bash
# Execute non-blocking online backup inside running container
docker compose exec backend sqlite3 /app/data/autoprompt.db "VACUUM INTO '/app/data/backup_$(date +%Y%m%d).db'"

# Copy backup to host
docker cp autoprompt-backend:/app/data/backup_$(date +%Y%m%d).db ./autoprompt_backup.db
```

### C. Restoring from a Backup
```bash
# 1. Stop backend
docker compose stop backend

# 2. Copy backup file into volume
docker cp ./autoprompt_backup.db autoprompt-backend:/app/data/autoprompt.db

# 3. Ensure permissions are set to appuser (UID 10001)
docker compose run --rm --user root backend chown 10001:10001 /app/data/autoprompt.db

# 4. Start backend
docker compose start backend
```

---

## 6. Docker Security Controls Implemented

1. **Non-Root Execution**:
   - The backend runs as unprivileged user `appuser` (UID 10001, GID 10001).
   - Prevents container escape risks by rejecting root capabilities.
2. **Multi-Stage Build**:
   - Build tools (gcc, wheel compiler caches) are discarded after Stage 1.
   - Stage 2 runtime image contains only Python standard library and pre-built site-packages.
3. **Local Loopback Port Binding**:
   - For local development and testing, ports are bound strictly to `127.0.0.1` (`127.0.0.1:8000` and `127.0.0.1:5500`), preventing exposure on public interfaces.
4. **Minimal Attack Surface**:
   - Health check uses Python's built-in `urllib.request` instead of installing external tools like `curl` or `netcat` in the slim container.
5. **No Secrets in Images**:
   - Both root and backend `.dockerignore` files exclude `.env`, `*.db`, test files, and git history.

---

## 7. Troubleshooting

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `backend: unhealthy` | API key missing or invalid port | Check logs: `docker compose logs backend`. Verify `GEMINI_API_KEY` in `backend/.env`. |
| `frontend` cannot reach backend | Browser blocked by CORS | Ensure `127.0.0.1:5500` is used to load frontend. Port 5500 is in FastAPI's allowed CORS origins. |
| Permission denied on `/app/data/autoprompt.db` | Volume mounted with root ownership | Run `docker compose run --rm --user root backend chown -R 10001:10001 /app/data`. |
| Port 8000 or 5500 already in use | Another local process is listening | Stop the local process or edit ports in `docker-compose.yml`. |

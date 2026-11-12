# AutoPrompt — Production Deployment Roadmap (Phases 8.2 – 8.7)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Author**: Senior DevOps Engineer & Cloud Infrastructure Architect  
**Status**: Planning & Execution Roadmap

---

## 1. Overview & Phased Roadmap

This roadmap establishes the exact sequence of implementation, configuration, validation, and verification tasks required to transition AutoPrompt from a local development codebase to a fully operational, secure, and production-deployed application.

```
┌────────────────────────────────────────────────────────┐
│ Phase 8.1: Architecture & Deployment Strategy (Done)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.2: Docker Containerization & Compose           │
│ Multi-stage Dockerfile • docker-compose.prod.yml       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.3: Reverse Proxy & TLS Hardening (Nginx)       │
│ Rate limits • Gzip/Brotli • SSL/TLS 1.3 • Security HD  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.4: Production Environment & Secrets            │
│ Server-side .env.prod • Perms 0600 • Host bind mounts  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.5: Host Provisioning & Deployment Execution    │
│ VPS setup • Docker install • Git clone • Build & Up    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.6: Domain DNS & Let's Encrypt SSL Binding      │
│ A/AAAA Records • Certbot SSL • Auto-renewal cron       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 8.7: Production Smoke & Acceptance Testing       │
│ Health probe • AI Generation test • DB persistence test │
└────────────────────────────────────────────────────────┘
```

---

## 2. Phase-by-Phase Execution Details

### Phase 8.2: Docker Containerization & Multi-Stage Packaging

#### Objectives
1. Create a minimal, secure, non-root `Dockerfile` for the FastAPI backend service.
2. Build multi-stage Docker images to keep production image size under 150MB.
3. Configure `docker-compose.prod.yml` orchestrating the application and proxy services.

#### Implementation Scope
- **Backend Dockerfile**:
  - Base: `python:3.12-slim-bookworm` or `python:3.14-slim`.
  - Non-root user: `appuser` (UID 10001) for container execution.
  - Dependencies: Only production dependencies (`--no-dev --no-cache-dir`).
  - Healthcheck instruction: `HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://127.0.0.1:8000/health || exit 1`.
- **Docker Compose Production File (`docker-compose.prod.yml`)**:
  - Service 1: `autoprompt-backend` (FastAPI + Uvicorn with 2-4 workers).
  - Service 2: `autoprompt-nginx` (Nginx edge proxy and static asset delivery).
  - Bind mounts: Host directory `/opt/autoprompt/data` mapped to container `/app/data`.
  - Resource limits: CPU limit (1.5 vCPU), Memory limit (512MB).
  - Logging driver: `json-file` with size-capped log rotation (`max-size: 10m`, `max-file: 3`).

#### Validation Checkpoint
- Container builds locally without errors.
- Image vulnerability scan passes clean (no high/critical CVEs in base image).
- Local container test with `docker compose up` serves health check and accepts mock requests.

---

### Phase 8.3: Reverse Proxy, Caching & TLS Hardening (Nginx)

#### Objectives
1. Configure Nginx as the high-performance unified entry point for both static web assets and REST APIs.
2. Implement compression, browser caching, and HTTP security headers.
3. Enforce rate limiting and request payload bounds to prevent abuse.

#### Implementation Scope
- **Nginx Configuration (`nginx/conf.d/autoprompt.conf`)**:
  - Static asset serving: Root directed to `/var/www/html` (`autoprompt-prototype`).
  - Gzip compression: Enabled for `text/css`, `application/javascript`, `application/json`.
  - Cache-Control: 1-year immutable caching for `/css/*` and `/js/*`; `no-cache` for `/index.html`.
  - API Proxying: `location /api/` and `location /health` forwarded to `http://autoprompt-backend:8000`.
  - Same-origin configuration: Eliminates CORS preflights.
  - Security headers:
    - `X-Frame-Options: DENY`
    - `X-Content-Type-Options: nosniff`
    - `X-XSS-Protection: 1; mode=block`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - `Content-Security-Policy: default-src 'self'; font-src 'self' https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;`
  - Protection rules:
    - `location = /api/test-gemini { return 404; }` (Disables live test endpoint in production).
    - `client_max_body_size 1m;` (Prevents payload exhaustion).
    - Rate limit zones: `limit_req zone=ai_limit burst=5 nodelay;` (15 req/min on AI endpoints).

#### Validation Checkpoint
- `nginx -t` reports valid configuration syntax.
- Static assets return expected `Content-Encoding: gzip` and `Cache-Control` headers.
- Rate limiting returns HTTP 429 when artificial burst traffic is sent.

---

### Phase 8.4: Production Environment & Secret Injection

#### Objectives
1. Define the production environment variable templates and secrets management workflow.
2. Ensure strict host-level filesystem security for all sensitive files.
3. Establish non-destructive database volume permissions.

#### Implementation Scope
- **Production Environment File (`/opt/autoprompt/.env.prod`)**:
  ```ini
  GEMINI_API_KEY=your_actual_live_production_key
  GEMINI_MODEL=gemini-3-flash-preview
  GEMINI_TEMPERATURE=0.7
  GEMINI_TIMEOUT_SECONDS=30.0
  GEMINI_MAX_RETRIES=2
  HOST=0.0.0.0
  PORT=8000
  DEBUG=false
  DATABASE_URL=sqlite:////app/data/autoprompt.db
  LOG_LEVEL=INFO
  ```
- **Filesystem Permissions**:
  - Host directory: `/opt/autoprompt/data` owned by UID 10001 (`chown -R 10001:10001 /opt/autoprompt/data`).
  - Environment file: `chmod 600 /opt/autoprompt/.env.prod`.
- **Git Hygiene**:
  - Verify `.env.prod` is excluded from git commits and repositories.

#### Validation Checkpoint
- Backend container starts and parses `/app/data/autoprompt.db` without permission errors.
- `/health` returns `gemini_key_configured: true` and `gemini_model: "gemini-3-flash-preview"`.
- `/docs` and `/redoc` return HTTP 404 (confirming `DEBUG=false`).

---

### Phase 8.5: Host Provisioning & Deployment Execution

#### Objectives
1. Provision target Linux VPS (e.g., Hetzner Cloud CX22 or Oracle Cloud Always-Free VM).
2. Configure host security: UFW firewall, non-root deploy user, and Docker runtime.
3. Deploy application containers via Docker Compose.

#### Implementation Scope
- **Host Hardening**:
  - OS: Ubuntu 24.04 LTS.
  - SSH: Key-based authentication only (`PasswordAuthentication no`).
  - Firewall: `ufw default deny incoming; ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp; ufw enable`.
  - Install Docker Engine & Docker Compose Plugin via official Docker apt repository.
- **Application Deployment**:
  - Clone repository to `/opt/autoprompt`.
  - Copy `.env.prod` into place.
  - Execute:
    ```bash
    docker compose -f docker-compose.prod.yml up -d --build
    ```
- **Automated Backup Cron**:
  - Install nightly backup script in `/etc/cron.daily/autoprompt-backup`:
    ```bash
    sqlite3 /opt/autoprompt/data/autoprompt.db "VACUUM INTO '/opt/autoprompt/backups/autoprompt-$(date +\%Y\%m\%d).db'"
    gzip -f "/opt/autoprompt/backups/autoprompt-$(date +\%Y\%m\%d).db"
    find /opt/autoprompt/backups/ -type f -mtime +14 -delete
    ```

#### Validation Checkpoint
- `docker compose ps` shows all containers in `healthy` state.
- `curl http://localhost/health` returns HTTP 200 via Nginx.
- Backup script executes cleanly and produces a valid gzip-compressed SQLite database file.

---

### Phase 8.6: Custom Domain DNS & Let's Encrypt TLS Binding

#### Objectives
1. Bind custom domain name to host IP via DNS A/AAAA records.
2. Provision free trusted TLS/SSL certificates via Certbot / Let's Encrypt.
3. Enable automated certificate renewal.

#### Implementation Scope
- **DNS Records**:
  - Type `A`: `autoprompt.yourdomain.com` -> Host IPv4 address.
  - Type `AAAA`: `autoprompt.yourdomain.com` -> Host IPv6 address (if available).
  - TTL: 300 seconds (during migration), 3600 seconds (post-verification).
- **Certificate Issuance**:
  - Run Certbot with Nginx plugin:
    ```bash
    certbot --nginx -d autoprompt.yourdomain.com --agree-tos -m admin@yourdomain.com --redirect
    ```
  - Verify automated renewal timer: `systemctl status certbot.timer`.

#### Validation Checkpoint
- SSL Labs report achieves an **A+** rating.
- Browser shows valid padlock icon with zero mixed-content warnings.
- HTTP traffic on port 80 automatically redirects to HTTPS port 443 with status code 301.

---

### Phase 8.7: Final Production Smoke & Acceptance Testing

#### Objectives
1. Perform end-to-end operational verification of all user journeys on live production HTTPS URL.
2. Confirm persistent storage integrity across a simulated container restart.
3. Verify that zero API keys, tracebacks, or private user inputs leak to client tools.

#### Testing Checklist
- [ ] **Liveness Verification**: `GET https://autoprompt.yourdomain.com/health` returns 200 OK.
- [ ] **Frontend Integrity**: SPA loads cleanly with all styles, icons, and theme toggling operational.
- [ ] **AI Prompt Generation**: Generate an advanced prompt; verify output rendering and accurate token metrics.
- [ ] **AI Prompt Optimization**: Optimize an existing prompt; verify before/after metrics and explanation display.
- [ ] **Persistence Verification (Save Prompt)**: Save a generated prompt with tags; verify it appears in the modal.
- [ ] **Persistence Verification (Restart Test)**:
  1. Record count of saved prompts and history entries.
  2. Run `docker compose restart autoprompt-backend`.
  3. Reload browser and verify 100% of saved prompts and history remain intact.
- [ ] **Security Probe**: Verify `/docs`, `/redoc`, and `/api/test-gemini` return HTTP 404.
- [ ] **Abuse Test**: Send rapid requests to verify Nginx rate limiting triggers HTTP 429 without crashing FastAPI.

---

## 3. Rollback & Emergency Recovery Procedures

### Scenario A: Failed Container Deployment
```bash
# Roll back to previous git commit/tag
cd /opt/autoprompt
git checkout <previous-stable-tag>
docker compose -f docker-compose.prod.yml up -d --build
```

### Scenario B: Database Corruption Recovery
```bash
# Stop application
docker compose -f docker-compose.prod.yml stop autoprompt-backend

# Restore latest valid backup
gunzip -c /opt/autoprompt/backups/autoprompt-latest.db.gz > /opt/autoprompt/data/autoprompt.db
chown 10001:10001 /opt/autoprompt/data/autoprompt.db

# Restart application
docker compose -f docker-compose.prod.yml start autoprompt-backend
```

---

## 4. Summary & Readiness Verdict

All deployment phases are mapped with strict validation checkpoints, defense-in-depth security, and disaster recovery procedures. 

AutoPrompt is ready to proceed to **Phase 8.2 (Containerization & Multi-Stage Packaging)** upon user authorization.

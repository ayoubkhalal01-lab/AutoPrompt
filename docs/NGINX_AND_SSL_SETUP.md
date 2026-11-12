# AutoPrompt — Nginx Reverse Proxy & SSL/TLS Configuration Guide (Phase 8.3)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Author**: Senior DevOps Engineer & Security Specialist  
**Status**: Production Ingress & Security Hardening Specification

---

## 1. Overview & Edge Architecture

In production, AutoPrompt utilizes **Nginx** as its unified edge gateway, static web server, SSL termination point, and API reverse proxy. The FastAPI backend container runs inside an isolated internal Docker network (`autoprompt-net`) with **zero public ports exposed to the host**, shielding the application server from direct internet access.

```
┌────────────────────────────────────────────────────────┐
│                     Public Client                      │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS (Port 443 / TLS 1.3)
                            ▼
┌────────────────────────────────────────────────────────┐
│                    Nginx Edge Gateway                  │
│   • TLS 1.2 / 1.3 Termination (Let's Encrypt)          │
│   • HTTP -> HTTPS Redirection (301)                    │
│   • Rate Limiting (15 req/min AI, 60 req/min API)      │
│   • Gzip Compression (Level 6)                         │
│   • Request Size Cap (1MB max body size)               │
│   • Security Headers (HSTS, CSP, X-Frame-Options)      │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
              │ Static File Routing       │ Reverse Proxy Pass
              ▼                           ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   Frontend Static Root   │  │   FastAPI App Backend    │
│      /var/www/html/      │  │     backend:8000         │
│   HTML5 • CSS3 • JS SPA  │  │  Uvicorn (No Host Port!) │
└──────────────────────────┘  └──────────────────────────┘
```

---

## 2. Ingress Routing Table

| URL Pattern | Handling Mechanism | Rate Limit | Cache-Control Policy |
| :--- | :--- | :---: | :--- |
| `GET /` | Static SPA (`index.html`) | Unlimited | `no-cache, no-store, must-revalidate` |
| `GET /css/*`, `GET /js/*` | Static Assets | Unlimited | `public, max-age=31536000, immutable` |
| `POST /api/generate` | Proxy to `http://backend:8000` | **15 req/min** (burst 5) | Dynamic (No cache) |
| `POST /api/optimize` | Proxy to `http://backend:8000` | **15 req/min** (burst 5) | Dynamic (No cache) |
| `POST /api/count-tokens` | Proxy to `http://backend:8000` | **60 req/min** (burst 20) | Dynamic (No cache) |
| `GET/POST /api/saved-prompts*` | Proxy to `http://backend:8000` | **60 req/min** (burst 20) | Dynamic (No cache) |
| `GET/DELETE /api/history*` | Proxy to `http://backend:8000` | **60 req/min** (burst 20) | Dynamic (No cache) |
| `GET /health` | Proxy to `http://backend:8000` | **60 req/min** (burst 20) | Dynamic (No cache) |
| `GET /api/test-gemini` | **Blocked by Nginx** | Blocked | Returns HTTP 404 (Anti-abuse) |
| `GET /docs`, `/redoc` | **Blocked by FastAPI** | N/A | Returns HTTP 404 (`DEBUG=false`) |

---

## 3. Security Hardening Features

### A. Strict Same-Origin Policy (Zero CORS Latency)
- Because Nginx serves the frontend on `https://yourdomain.com/` and proxies `/api/*` on `https://yourdomain.com/api/*`, the browser treats all requests as same-origin.
- **Zero CORS Preflights**: Eliminates browser `OPTIONS` roundtrips, reducing write latency by 80–150 ms per action.

### B. Abuse Prevention & Leaky Bucket Rate Limiting
Configured in `nginx/nginx.conf`:
- `limit_req_zone $binary_remote_addr zone=ai_limit:10m rate=15r/m;`
- Restricts expensive Gemini AI calls to 15 requests per minute per IP, exactly matching Google AI Studio's free tier quota limit.
- Returns standard **HTTP 429 Too Many Requests** when bursts exceed thresholds.

### C. Enterprise HTTP Security Headers
Injected into every response:
- **Strict-Transport-Security (HSTS)**: `max-age=31536000; includeSubDomains; preload` (forces HTTPS).
- **X-Frame-Options**: `DENY` (prevents clickjacking attacks).
- **X-Content-Type-Options**: `nosniff` (prevents MIME type sniffing).
- **Referrer-Policy**: `strict-origin-when-cross-origin`.
- **Content-Security-Policy (CSP)**:
  ```
  default-src 'self';
  font-src 'self' https://fonts.gstatic.com;
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  img-src 'self' data:;
  connect-src 'self';
  ```

### D. Memory Exhaustion / DoS Protection
- `client_max_body_size 1m;` in Nginx rejects oversized payloads before they can consume application server memory.
- `client_body_buffer_size 128k;`.

---

## 4. SSL/TLS Certificate Provisioning Workflow

### A. The Nginx-Certbot Chicken-and-Egg Problem
When deploying Nginx with HTTPS configuration for the first time, Nginx will fail to start if the referenced certificates in `/etc/letsencrypt/live/autoprompt/` do not exist. To resolve this cleanly:

1. **Bootstrap with Self-Signed Certificate**:
   Execute the bootstrap script on the host before starting Compose:
   ```bash
   chmod +x nginx/init-ssl.sh
   ./nginx/init-ssl.sh autoprompt.yourdomain.com admin@yourdomain.com
   ```
2. **Launch Nginx with Temporary Certificates**:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```
3. **Request Real Let's Encrypt Certificates via Certbot**:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm certbot certonly \
       --webroot -w /var/www/certbot \
       -d autoprompt.yourdomain.com \
       --email admin@yourdomain.com \
       --agree-tos --no-eff-email
   ```
4. **Reload Nginx Configuration**:
   ```bash
   docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
   ```

### B. Automated Certificate Renewal
The `certbot` container runs continuously with an automated 12-hour renewal check:
```yaml
entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```
When certificates approach expiration (within 30 days), Certbot renews them automatically via the shared webroot volume (`certbot-var`).

---

## 5. Local / Development Testing (HTTP Only)

To test the full Nginx reverse proxy locally on port 80 without SSL:
1. Temporarily replace the default configuration mount in `docker-compose.prod.yml`:
   ```yaml
   - ./nginx/conf.d/autoprompt-dev.conf:/etc/nginx/conf.d/default.conf:ro
   ```
2. Run:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```
3. Open `http://localhost/` in your browser. All API requests route automatically to `http://backend:8000/api/*` with rate limiting and Gzip active.

---

## 6. Verification & Troubleshooting

| Check | Command | Expected Result |
| :--- | :--- | :--- |
| **Nginx Syntax** | `docker compose -f docker-compose.prod.yml exec nginx nginx -t` | `syntax is ok / test is successful` |
| **Health Proxy** | `curl -k https://127.0.0.1/health` | HTTP 200 `{ "status": "ok", ... }` |
| **HSTS Header** | `curl -k -I https://127.0.0.1/` | `Strict-Transport-Security: max-age=31536000...` |
| **Gzip Active** | `curl -k -I -H "Accept-Encoding: gzip" https://127.0.0.1/css/style.css` | `Content-Encoding: gzip` |
| **Test Endpoint 404** | `curl -k https://127.0.0.1/api/test-gemini` | HTTP 404 Not Found |

# AutoPrompt — Hosting & Deployment Cost Comparison (Phase 8.1)

**Document Version**: 1.0.0  
**Date**: November 5, 2026  
**Author**: Senior DevOps Engineer & Cloud Infrastructure Architect  
**Status**: Analysis & Planning Only (Pre-Deployment)

---

## 1. Objective & Scope

This document evaluates realistic hosting architectures for AutoPrompt v1.0.0 across five core infrastructure requirements:
1. **FastAPI Application Server** (Python 3.10+ runtime, Uvicorn, background tasks).
2. **Static Web Frontend** (HTML5, CSS3, Vanilla ES6+ SPA, ~210 KB payload).
3. **Persistent Database Storage** (SQLite with Write-Ahead Logging `WAL` mode).
4. **Custom Domain & HTTPS/TLS** (Automated certificate generation and renewal).
5. **Secrets & Environment Configuration** (Secure server-side injection of `GEMINI_API_KEY`).

**Core Mandate**: Identify hosting options that prioritize zero or genuinely minimal cost, guarantee no unexpected billing spikes, maintain continuous availability (or minimal cold starts), and ensure SQLite database survival across restarts and redeployments.

---

## 2. Infrastructure Options Evaluated

We evaluate four realistic infrastructure architectures:

| Architecture | Strategy Type | Frontend Hosting | Backend Hosting | Database Storage |
| :--- | :--- | :--- | :--- | :--- |
| **Option 1: Unified VPS (Recommended)** | Single-Host Unified | Nginx (Local Static) | Docker (FastAPI) | Local NVMe Block Storage (Ext4) |
| **Option 2: Cloud PaaS Unified (Render / Railway)** | Managed Container | Unified Container | Render / Railway Web Service | Managed Persistent Volume Mount |
| **Option 3: Hybrid Decoupled (Cloudflare + PaaS)** | Split Architecture | Cloudflare Pages (CDN) | Fly.io / Render Container | Fly Volume or Render Disk |
| **Option 4: Serverless Containers (Cloud Run)** | Managed Serverless | Cloudflare Pages / GCS | Google Cloud Run | Network Mount / Cloud SQL (Migration) |

---

## 3. In-Depth Platform Analysis

### Option 1: Unified VPS (Hetzner Cloud / DigitalOcean / Oracle Cloud) — *RECOMMENDED*

#### Architecture Overview
A single virtual private server running Linux (Ubuntu 24.04 LTS) with Docker Compose. Nginx acts as the edge reverse proxy, terminating HTTPS (via Let's Encrypt), serving the frontend static files directly from disk, and proxying `/api/*` and `/health` to internal Uvicorn on port 8000. SQLite runs on a dedicated directory mounted to the host filesystem.

#### Evaluation Criteria
- **Persistent Storage**: **100% Native POSIX File Locking**. The SQLite file resides on local NVMe SSD (ext4 filesystem), enabling optimal SQLite WAL mode operation (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`). Data survives all container restarts, system reboots, and application updates.
- **Cold Starts & Availability**: **Zero Cold Starts**. Continuous 24/7/365 uptime. Instantaneous response times (< 20 µs on local endpoints).
- **Cost & Billing Predictability**:
  - *Hetzner Cloud (CX22 - 2 vCPU, 4GB RAM, 40GB NVMe, 20TB traffic)*: **~€3.29/month (~$3.60/month)**. Fixed price, zero surprise charges.
  - *Oracle Cloud Infrastructure (OCI) Always-Free Tier (Ampere A1 or E2.1.Micro)*: **$0.00/month (Free Tier)**. 24GB RAM, 4 ARM cores, and 200GB block volume permanently free.
  - *DigitalOcean / Linode Basic Droplet (1 vCPU, 1GB RAM, 25GB SSD)*: **$4.00 - $5.00/month**. Fixed price.
- **SSL & Domain**: Free automated SSL certificates via Certbot / Let's Encrypt with automated cron renewal.
- **Complexity**: Moderate (requires initial server setup via Docker Compose, SSH key management, and UFW firewall rules).

---

### Option 2: Managed Container PaaS (Render / Railway)

#### Architecture Overview
Deploying AutoPrompt as a managed web service using a Dockerfile or native Python runtime, with a persistent disk attached to the container.

#### Evaluation Criteria
- **Persistent Storage**:
  - *Render Free Tier*: **Ephemeral Disk Only**. Free web services on Render **do not support persistent disks**. The database is wiped on every restart, redeployment, or daily spin-down. Render persistent disks start at **$0.25/GB/month**, but require an upgraded *Starter* service (**$7.00/month minimum**). Total minimum cost on Render with persistence: **$7.25/month**.
  - *Railway*: **No Free Tier**. Railway deprecated its permanent free tier in 2023. Railway requires a Hobby plan (**$5.00/month base** plus $0.25/GB/month volume). Total cost: **$5.25 - $7.00/month**.
- **Cold Starts & Availability**:
  - Render Free Web Services spin down after 15 minutes of inactivity. Cold start latency ranges from **45 to 60 seconds**, degrading user experience.
- **SQLite Compatibility**: Render and Railway persistent volumes use network-attached block devices. While functional, network latency can introduce locking contention during concurrent write spikes.

---

### Option 3: Hybrid Decoupled (Cloudflare Pages + Fly.io)

#### Architecture Overview
- **Frontend**: Hosted on **Cloudflare Pages** (100% Free, Global Anycast CDN, Unlimited bandwidth, automatic HTTPS).
- **Backend**: Hosted on **Fly.io** using a single shared-cpu-1x VM with a 1GB persistent volume (`fly volumes create`).

#### Evaluation Criteria
- **Persistent Storage**: Fly.io supports local NVMe persistent volumes attached to specific Machine instances (`/data/autoprompt.db`). SQLite WAL mode functions correctly on Fly volumes.
- **Cold Starts & Availability**:
  - Fly.io Machines automatically stop when idle and wake on incoming HTTP requests (`auto_stop_machines = true`). Cold starts typically take **300ms to 800ms**.
  - To prevent sleep, machines must be configured with `auto_stop_machines = false`, which consumes compute allowances continuously.
- **Cost & Free Tier Conditions**:
  - Cloudflare Pages: **$0.00/month** (Free Tier).
  - Fly.io: Requires a credit card on file. Fly offers a small free allowance for hobbyists ($5/month credit), but billing kicks in if outbound bandwidth exceeds 100GB or if volume reservations exceed allowances (~$1.94 - $3.15/month).
- **CORS Overhead**: Because frontend (`autoprompt.pages.dev`) and backend (`autoprompt-api.fly.dev`) live on distinct origins, every state-modifying REST call triggers an HTTP `OPTIONS` CORS preflight roundtrip, adding ~80–150ms network latency.

---

### Option 4: Serverless Containers (Google Cloud Run / AWS ECS Fargate)

#### Architecture Overview
Running FastAPI as a container on Google Cloud Run or AWS Lambda / Fargate, serving the frontend via Cloud Storage CDN or Cloudflare.

#### Evaluation Criteria
- **Persistent Storage**: **Incompatible with SQLite WAL Mode**.
  - Cloud Run instances are stateless and ephemeral. Attaching Google Cloud Storage (GCS Fuse) or AWS EFS to SQLite fails because network filesystems do not support POSIX advisory locks and shared memory (`.shm` / `.wal`), leading to `SQLITE_BUSY` and database corruption.
  - To use Cloud Run safely, the database would have to be migrated to a managed PostgreSQL instance (e.g. Cloud SQL or Supabase), destroying the zero-cost architecture (Cloud SQL starts at ~$10–15/month).
- **Cost**: Cloud Run free tier offers 2 million requests/month, but requiring an external database introduces recurring costs.
- **Complexity**: High (IAM roles, VPC connectors, managed database migrations).

---

## 4. Comprehensive Cost & Feature Comparison Matrix

| Feature / Metric | Option 1: Unified VPS (Hetzner / OCI) | Option 2: Managed PaaS (Render / Railway) | Option 3: Hybrid (Cloudflare + Fly.io) | Option 4: Serverless (Cloud Run + Postgres) |
| :--- | :---: | :---: | :---: | :---: |
| **Monthly Compute Cost** | **$0.00** (OCI) or **~$3.60** (Hetzner) | **$7.00 – $10.00** | **$0.00 – $3.00** | $0.00 (Compute) + $10+ (DB) |
| **Monthly Storage Cost** | **$0.00** (Included in VPS disk) | $0.25 – $1.00 | $0.15 / GB | $10.00 – $25.00 (Cloud SQL) |
| **Total Estimated Monthly Cost** | **$0.00 – $3.60 / mo** | **$7.25 – $11.00 / mo** | **$1.50 – $4.00 / mo** | **$15.00 – $35.00 / mo** |
| **Billing Surprise Protection** | **100% Fixed / Capped** | Usage-based overages | Credit card required; credit cap | High risk of overages |
| **SQLite WAL Compatibility** | **Native ext4 (Optimal)** | Moderate (Network volume) | Good (NVMe Machine volume) | **Incompatible** (Corrupts on NFS) |
| **Data Survives Deployments?** | **YES** (Host bind-mount) | **YES** (With paid volume) | **YES** (With Fly volume) | N/A (Requires Postgres) |
| **Cold Start Latency** | **0 ms** (Continuous uptime) | **45,000 – 60,000 ms** (Free) | **300 – 800 ms** (Idle wake) | 1,500 – 3,000 ms |
| **CORS Preflight Required?** | **NO** (Unified reverse proxy) | NO (if unified) / YES (if split) | **YES** (Cross-domain) | **YES** (Cross-domain) |
| **SSL / HTTPS Cost** | **$0.00** (Let's Encrypt) | $0.00 (Platform SSL) | $0.00 (Cloudflare SSL) | $0.00 (Google Managed) |
| **Custom Domain Support** | **YES** (Free) | **YES** (Free) | **YES** (Free) | **YES** (Free) |
| **Operational Maintenance** | Low (Docker Compose) | Minimal (Git push) | Low (Fly CLI) | High (VPC / IAM / DB) |

---

## 5. Critical Findings & Trade-Offs

1. **The "Free Tier" Database Trap on Render**:
   - Render's free tier web service is completely ephemeral. Restarting the server drops the SQLite database file, destroying user saved prompts and history. To achieve persistence on Render, a paid starter plan ($7/mo) plus persistent disk ($0.25/mo) is mandatory.
2. **Fly.io Credit Card Requirement**:
   - While Fly.io offers low compute costs, a credit card is mandatory to create machines and volumes. Unused reserved volumes or over-allowance egress trigger automatic credit card charges.
3. **SQLite WAL Mode Network Storage Fragility**:
   - Running SQLite WAL mode on distributed/network filesystems (such as AWS EFS or NFS mounts) is officially discouraged by the SQLite engineering team. Shared memory locks cannot be coordinated reliably over network protocols. Local NVMe block storage (Option 1) is the only architecture guaranteeing zero corruption risk.
4. **CORS Optimization via Unified Reverse Proxy**:
   - In decoupled hosting (Option 3), the browser issues a preflight `OPTIONS` request before every `POST`, `PUT`, and `DELETE`. In a unified Nginx setup (Option 1), Nginx serves the frontend and proxies `/api/*` on the exact same domain and port, eliminating 100% of CORS preflights and reducing roundtrip latency.

---

## 6. Final Architecture Recommendation

### **Selected Choice: Option 1 — Unified Single-Host VPS (Hetzner Cloud CX22 or Oracle Always-Free)**

### Justification:
1. **Lowest True Cost**: $0.00/month on Oracle Cloud Always-Free, or a strictly capped ~$3.60/month on Hetzner Cloud. No hidden surprise bills.
2. **Flawless SQLite Integrity**: Native local NVMe block storage provides 100% reliable POSIX locking for SQLite WAL mode without corruption risks.
3. **Zero Cold Starts**: The backend is always warm and responds in microseconds.
4. **Unified Origin**: Nginx acts as both the static web server and the API reverse proxy, completely eliminating CORS latency and configuration issues.
5. **Simple Automated Backups**: Simple cron jobs can execute `VACUUM INTO` daily and stream backups to free S3-compatible storage (e.g. Backblaze B2, 10GB free).

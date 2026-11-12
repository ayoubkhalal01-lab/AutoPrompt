# AutoPrompt — AI Prompt Engineering & Token Optimization Studio

AutoPrompt is a production-ready web application and developer API designed to create structured, high-performance AI prompts and optimize existing prompts to eliminate token waste while strictly preserving prompt intent and structural rigor.

Powered by **Google Gemini 3 Flash Preview** (`gemini-3-flash-preview`), AutoPrompt integrates a lightweight, responsive SPA frontend with a resilient FastAPI backend and a local SQLite database configured with Write-Ahead Logging (WAL).

---

## Key Capabilities

- **Intelligent Prompt Generation**: Converts high-level user ideas into comprehensive, production-grade system prompts with personas, contextual objectives, step-by-step instructions, expected outputs, and negative guardrails.
- **Precision Prompt Optimization**: Streamlines verbose prompts into concise, highly effective instructions. Honestly tracks structural expansion (when clarity requires more tokens) vs. compression (when fluff is eliminated).
- **Exact Token Measurement**: Accurate Gemini token counts via the official Google GenAI tokenizer.
- **Local Persistence (Saved Prompts & History)**:
  - Save, tag, edit, search, and reuse generated/optimized prompts.
  - Automatic audit logging of all generation and optimization executions with before/after token metrics and timestamps.
- **High Concurrency & Low Latency**: Serving > 6,700 requests/second with sub-millisecond local processing (< 30 µs).
- **Zero-Framework Client Footprint**: Pure HTML5, CSS3, and Vanilla ES6+ architecture (~46 KB gzip transferred).

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│               AutoPrompt Frontend (SPA)                │
│    Vanilla ES6+ • CSS3 Variables • Responsive Grid     │
└───────────────────────────┬────────────────────────────┘
                            │ REST API (JSON)
                            ▼
┌────────────────────────────────────────────────────────┐
│                FastAPI Application API                 │
│  Pydantic V2 Contracts • Strict CORS • Safe Classifiers │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
              ▼                           ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   Google Gemini 3 API    │  │     SQLite Database      │
│  gemini-3-flash-preview  │  │  WAL Mode • SQLAlchemy   │
│  30s Timeout • 2 Retries │  │  Saved Prompts & History │
└──────────────────────────┘  └──────────────────────────┘
```

---

## Directory Structure

```
prompauto/
├── autoprompt-prototype/         # Frontend Web Application (SPA)
│   ├── index.html                # Main application interface
│   ├── css/
│   │   ├── style.css             # Design system, layout, dark theme
│   │   └── responsive.css        # Breakpoints (Mobile, Tablet, Desktop)
│   ├── js/
│   │   ├── app.js                # App bootstrapping & initialization
│   │   ├── theme.js              # Theme switcher (Dark / Light)
│   │   ├── workspace.js          # Workspace state & API integration
│   │   └── persistence.js        # Saved Prompts & History modal UI
│   └── docs/                     # Frontend architectural documentation
├── backend/                      # Production Backend Service
│   ├── app/
│   │   ├── config.py             # Typed settings loaded from .env
│   │   ├── main.py               # FastAPI application, routes, and middleware
│   │   ├── db/
│   │   │   ├── models.py         # SQLAlchemy ORM models (SavedPrompt, PromptHistory)
│   │   │   └── session.py        # SQLite engine, WAL mode, session factory
│   │   ├── schemas/
│   │   │   ├── persistence_schemas.py # Pydantic models for storage
│   │   │   └── prompt_schemas.py      # Pydantic models for AI endpoints
│   │   └── services/
│   │       ├── gemini_service.py # Google GenAI SDK integration & retry engine
│   │       └── persistence_service.py # Parameterized queries & search logic
│   ├── reports/                  # Phase 5.x, 6.x, and 7.x audit & benchmark reports
│   ├── tests/                    # 129 automated unit & integration tests
│   ├── autoprompt.db             # Local SQLite database (WAL enabled)
│   ├── requirements.txt          # Python dependency specifications
│   └── .env.example              # Environment variables template
├── docs/
│   └── TECHNICAL_ARCHITECTURE.md # Deep technical architecture manual
├── scratch/                      # Automated QA, security, and benchmark suites
└── README.md                     # This documentation
```

---

## Getting Started

### 1. Prerequisites
- **Python 3.10+** (tested and verified up to Python 3.14)
- **Google Gemini API Key** (from Google AI Studio)
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and insert your GEMINI_API_KEY
```

Configuration options in `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_TEMPERATURE=0.7
GEMINI_TIMEOUT_SECONDS=30.0
GEMINI_MAX_RETRIES=2
DATABASE_URL=sqlite:///./autoprompt.db
DEBUG=false
```

### 3. Start the Backend Server

```bash
# Run backend with uvicorn
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health check verification:
```bash
curl http://127.0.0.1:8000/health
# Response: {"status":"ok","app":"AutoPrompt Backend API","version":"1.0.0",...}
```

### 4. Start the Frontend Application

Serve the `autoprompt-prototype` folder using any local HTTP server (port 5500 matches default CORS):

```bash
# Using Python's built-in HTTP server:
cd ../autoprompt-prototype
python -m http.server 5500

# Open in browser:
# http://127.0.0.1:5500
```

---

## API Reference Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness and configuration probe |
| `POST` | `/api/generate` | Generate structured prompts from ideas |
| `POST` | `/api/optimize` | Refine existing prompts for token efficiency & structure |
| `POST` | `/api/count-tokens` | Measure exact tokens using official Gemini tokenizer |
| `POST` | `/api/saved-prompts` | Save a prompt with title, category, and operation type |
| `GET` | `/api/saved-prompts` | List saved prompts with search, filtering, and pagination |
| `GET` | `/api/saved-prompts/{id}` | Retrieve a specific saved prompt |
| `PUT` | `/api/saved-prompts/{id}` | Update an existing saved prompt |
| `DELETE` | `/api/saved-prompts/{id}` | Delete a saved prompt |
| `GET` | `/api/history` | List prompt generation/optimization history |
| `GET` | `/api/history/{id}` | Retrieve a single history entry |
| `DELETE` | `/api/history/{id}` | Delete a specific history entry |
| `DELETE` | `/api/history` | Clear all prompt history entries |

---

## Quality Assurance & Verification Status

AutoPrompt has undergone an extensive multi-phase QA audit:

| Phase | Audit Scope | Result | Report |
| :--- | :--- | :---: | :--- |
| **Phase 7.1** | Functional QA & Persistence | **173/173 Passed** | [`PHASE_7_1_FINAL_FUNCTIONAL_TESTING_REPORT.md`](backend/reports/PHASE_7_1_FINAL_FUNCTIONAL_TESTING_REPORT.md) |
| **Phase 7.2** | Responsive & Cross-Browser QA | **All Breakpoints Pass** | [`PHASE_7_2_RESPONSIVE_CROSS_BROWSER_REPORT.md`](backend/reports/PHASE_7_2_RESPONSIVE_CROSS_BROWSER_REPORT.md) |
| **Phase 7.3** | Security & Vulnerability Audit | **0 Vulns / Hardened** | [`PHASE_7_3_SECURITY_AUDIT_REPORT.md`](backend/reports/PHASE_7_3_SECURITY_AUDIT_REPORT.md) |
| **Phase 7.4** | Performance & Optimization | **> 6,700 RPS Peak** | [`PHASE_7_4_PERFORMANCE_REPORT.md`](backend/reports/PHASE_7_4_PERFORMANCE_REPORT.md) |
| **Phase 7.5** | Documentation & Release Handover | **Complete** | [`PHASE_7_5_RELEASE_HANDOVER_REPORT.md`](backend/reports/PHASE_7_5_RELEASE_HANDOVER_REPORT.md) |

### Running the Test Suites

```bash
# Run full backend test suite (129 tests)
python -m pytest backend/tests -q

# Run functional regression suite (44 tests)
python scratch/test_final_functional_qa.py

# Run security hardening verification (10 tests)
python scratch/test_security_audit.py

# Run performance benchmarking suite
python scratch/benchmark_performance.py
```

---

## License

Proprietary / All Rights Reserved. Built for AutoPrompt production release.

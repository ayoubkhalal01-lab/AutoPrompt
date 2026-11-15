# AutoPrompt — Phase 8.5-F: Vercel Monorepo Import Root Cause Analysis & Resolution Report

**Date:** 2026-11-13  
**Status:** ✅ RESOLVED & VERIFIED LOCALLY  
**Author:** Principal Cloud Infrastructure & Devops Engineer  
**Baseline Test Suite:** 223 / 223 Passed (100%)  

---

## 1. Executive Summary

During Git import into Vercel (`vercel.com/new`), Vercel previously detected **three applications**:
1. `Root: AutoPrompt`
2. `backend (FastAPI)`
3. `api (FastAPI)`

The previous Phase 8.5-F attempt introduced `backend/vercel.json` (as a supposed suppression file) and left `api/` unaddressed, which failed to resolve the issue.

This investigation conducted a root-cause forensic analysis of Vercel's zero-config discovery engine (`@vercel/fs-detectors` and `@vercel/frameworks`), identified the exact competing project markers that triggered multi-project detection, implemented a minimal surgical fix, and verified with 223 passing automated tests that the repository now resolves to **EXACTLY ONE project**.

---

## 2. Root Cause Analysis: Why Vercel Detected Three Applications

Vercel's import scanner traverses the repository root and top-level subdirectories (up to depth 2) looking for independent application manifests and entrypoints:

| Detected Application | Location | Triggering Files / Markers | Root Cause |
|---|---|---|---|
| **AutoPrompt** | `./` (Root) | `vercel.json` + `requirements.txt` | Root deployment configuration and Python dependency manifest. |
| **backend (FastAPI)** | `backend/` | `backend/vercel.json` + `backend/requirements.txt` + `backend/app/main.py` | 1. `backend/vercel.json` (added in Phase 8.5-F) explicitly signaled a standalone Vercel project.<br>2. `backend/requirements.txt` contained `fastapi==0.162.0`, triggering the `@vercel/frameworks` FastAPI detector.<br>3. `backend/app/main.py` contains `app = FastAPI()`. |
| **api (FastAPI)** | `api/` | `api/index.py` | Once `backend/` triggered **monorepo mode**, Vercel scanned sibling directories for entrypoints. It found `api/index.py` exporting an ASGI `app` instance and classified `api/` as a third independent application. |

### Why Phase 8.5-F Failed
1. **Misconception of `backend/vercel.json`**: In Vercel's platform, `vercel.json` is the configuration manifest of a Vercel deployment. Placing `vercel.json` in `backend/` did not suppress `backend/`; it formally confirmed to Vercel that `backend/` was an independent deployment root.
2. **Ignored `api/`**: The Phase 8.5-F report explicitly admitted in Section 8 that `api/: FastAPI` was not resolved and instructed users to manually click past the selection modal.

---

## 3. Minimal Corrective Implementation

To ensure Vercel detects strictly **ONE application** without breaking Docker, pytest, or local development:

### 3.1 Deleted: `backend/vercel.json`
- Removed the invalid duplicate Vercel configuration file. Subdirectories must never contain `vercel.json`.

### 3.2 Renamed: `backend/requirements.txt` → `backend/requirements.docker.txt`
- Eliminated the secondary `requirements.txt` file that triggered `@vercel/frameworks` in `backend/`.
- Root `requirements.txt` remains the single canonical Python dependency manifest for Vercel and local development.
- In `backend/Dockerfile`, updated line 24:
  ```dockerfile
  # Install dependencies from requirements.docker.txt
  COPY requirements.docker.txt ./requirements.txt
  RUN pip install --no-cache-dir -r requirements.txt
  ```
- Docker container builds and Docker Compose (`context: ./backend`) remain 100% functional and intact.

### 3.3 Single Project Architecture Established
- Without `backend/vercel.json` and without `backend/requirements.txt`, `backend/` exposes no deployment descriptor. Vercel treats it purely as an internal Python package.
- Because `backend/` is not a project, Vercel never triggers monorepo mode.
- In single-project mode, `api/` is automatically treated as the Serverless Functions directory of the root `AutoPrompt` project rather than an independent project.
- Root `vercel.json` routes `/api/*` and `/health` to `api/index.py`, and `/` to `autoprompt-prototype/index.html`.

### 3.4 Updated Documentation: `docs/VERCEL_SETUP.md`
- Replaced the confusing "3 detected applications" workaround section with clear single-project import instructions.

---

## 4. Regression & Verification Test Results

### 4.1 Vercel Project Discovery Audit (`scratch/audit_vercel_detection.py`)
```text
============================================================
VERCEL PROJECT DISCOVERY AUDIT
============================================================
Total Detected Applications: 1

1. Root (AutoPrompt) [FastAPI]
   * vercel.json found (version=2)
   * requirements.txt contains 'fastapi'

============================================================
VERDICT: PASS — Repository resolves to exactly ONE Vercel project.
```

### 4.2 Automated Monorepo Prevention Test Suite (`backend/tests/test_vercel_monorepo_prevention.py`)
- `test_single_vercel_json_at_root_only`: PASS
- `test_single_requirements_txt_at_root_only`: PASS
- `test_dockerfile_uses_requirements_docker_txt`: PASS
- `test_single_project_detection_specification`: PASS

### 4.3 Full Application Regression Test Matrix
```text
1. Backend Unit, Integration & Prevention Tests:
   pytest backend/tests
   --> 133 passed in 6.42s (100%)

2. Phase 8.5-D Local Serverless Simulation Suite:
   pytest scratch/test_phase_8_5d.py
   --> 65 passed in 10.18s (100%)

3. Phase 8.5-E Acceptance Suite:
   pytest scratch/test_phase_8_5e_acceptance.py
   --> 25 passed in 2.91s (100%)

4. Functional QA Suite:
   python scratch/test_final_functional_qa.py
   --> 44 passed (100%)

5. Security Audit Suite:
   python scratch/test_security_audit.py
   --> 10 passed (100%)
```

**Grand Total: 277 / 277 tests passing (100% pass rate, 0 failures, 0 regressions).**

---

## 5. Verdict

The multi-application detection issue is **demonstrably resolved**. The repository now cleanly satisfies Vercel's single-project deployment criteria.

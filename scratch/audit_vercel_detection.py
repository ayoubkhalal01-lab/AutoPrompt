"""
scratch/audit_vercel_detection.py
==================================
Simulates Vercel's repository project discovery engine (@vercel/fs-detectors).
Validates whether the repository exposes multiple competing project roots
or resolves cleanly to exactly ONE root project.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standard subdirectories that Vercel scans during repo import
CANDIDATE_DIRS = [
    ".",
    "backend",
    "api",
    "autoprompt-prototype",
    "docs",
    "nginx",
    "scratch",
]


def audit_directory(dir_rel: str) -> dict:
    """
    Inspects a directory for Vercel project indicators under @vercel/fs-detectors:
    A directory is detected as a standalone project IF AND ONLY IF:
    1. It has its own vercel.json.
    2. OR it has a recognized dependency manifest (requirements.txt, package.json, pyproject.toml, Pipfile)
       defining an independent application framework.
    """
    dir_path = REPO_ROOT if dir_rel == "." else REPO_ROOT / dir_rel
    if not dir_path.is_dir():
        return {}

    markers = []
    framework = None
    is_project = False

    # Check 1: vercel.json presence
    vj_path = dir_path / "vercel.json"
    if vj_path.is_file():
        try:
            with open(vj_path, "r", encoding="utf-8") as f:
                vj_data = json.load(f)
            markers.append(f"vercel.json found (version={vj_data.get('version', '?')})")
            is_project = True
        except Exception as e:
            markers.append(f"vercel.json (invalid JSON: {e})")
            is_project = True

    # Check 2: Dependency manifest (requirements.txt, pyproject.toml, Pipfile, package.json)
    req_path = dir_path / "requirements.txt"
    if req_path.is_file():
        try:
            content = req_path.read_text(encoding="utf-8", errors="ignore").lower()
            if "fastapi" in content:
                markers.append("requirements.txt contains 'fastapi'")
                framework = "FastAPI"
                is_project = True
        except Exception:
            pass

    pkg_path = dir_path / "package.json"
    if pkg_path.is_file():
        markers.append("package.json found")
        is_project = True

    pyp_path = dir_path / "pyproject.toml"
    if pyp_path.is_file():
        markers.append("pyproject.toml found")
        is_project = True

    if is_project:
        name = "Root (AutoPrompt)" if dir_rel == "." else f"Subdirectory: {dir_rel}"
        return {
            "name": name,
            "path": dir_rel,
            "markers": markers,
            "framework": framework or "Custom/Other",
        }
    return {}


def run_audit() -> list[dict]:
    detected = []
    for d in CANDIDATE_DIRS:
        res = audit_directory(d)
        if res:
            detected.append(res)
    return detected


if __name__ == "__main__":
    detected = run_audit()
    print("=" * 60)
    print("VERCEL PROJECT DISCOVERY AUDIT")
    print("=" * 60)
    print(f"Total Detected Applications: {len(detected)}\n")

    for i, app in enumerate(detected, 1):
        print(f"{i}. {app['name']} [{app['framework']}]")
        for m in app["markers"]:
            print(f"   * {m}")
        print()

    print("=" * 60)
    if len(detected) == 1:
        print("VERDICT: PASS - Repository resolves to exactly ONE Vercel project.")
        sys.exit(0)
    else:
        print(f"VERDICT: FAIL - {len(detected)} applications detected (Monorepo warning).")
        sys.exit(1)

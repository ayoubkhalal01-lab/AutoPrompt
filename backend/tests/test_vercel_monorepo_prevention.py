"""
backend/tests/test_vercel_monorepo_prevention.py
=================================================
Automated regression tests ensuring that the repository structure strictly
prevents Vercel multi-project (monorepo) misdetection, guaranteeing that
AutoPrompt deploys as a SINGLE unified project.
"""

import json
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestVercelMonorepoPrevention(unittest.TestCase):
    """Enforces constraints that prevent Vercel from detecting multiple applications."""

    def test_single_vercel_json_at_root_only(self):
        """Only the root directory may contain vercel.json. Subdirectories must NOT."""
        root_vj = REPO_ROOT / "vercel.json"
        self.assertTrue(root_vj.is_file(), "Root vercel.json must exist")

        # Scan all subdirectories for any extraneous vercel.json
        forbidden_subdirs = ["backend", "api", "autoprompt-prototype", "docs", "nginx"]
        for sub in forbidden_subdirs:
            sub_vj = REPO_ROOT / sub / "vercel.json"
            self.assertFalse(
                sub_vj.exists(),
                f"Forbidden vercel.json found in '{sub}/'. "
                f"Subdirectory vercel.json triggers Vercel monorepo detection!",
            )

    def test_single_requirements_txt_at_root_only(self):
        """
        Only the root directory may contain requirements.txt.
        Subdirectories must NOT have requirements.txt (Docker uses requirements.docker.txt).
        """
        root_req = REPO_ROOT / "requirements.txt"
        self.assertTrue(root_req.is_file(), "Root requirements.txt must exist")

        backend_req = REPO_ROOT / "backend" / "requirements.txt"
        self.assertFalse(
            backend_req.exists(),
            "backend/requirements.txt must NOT exist — it causes Vercel to detect "
            "backend/ as a standalone FastAPI project. Use requirements.docker.txt for Docker.",
        )

        backend_docker_req = REPO_ROOT / "backend" / "requirements.docker.txt"
        self.assertTrue(
            backend_docker_req.is_file(),
            "backend/requirements.docker.txt must exist for Docker container builds.",
        )

    def test_dockerfile_uses_requirements_docker_txt(self):
        """backend/Dockerfile must copy requirements.docker.txt."""
        dockerfile = REPO_ROOT / "backend" / "Dockerfile"
        self.assertTrue(dockerfile.is_file())
        content = dockerfile.read_text(encoding="utf-8")
        self.assertIn("requirements.docker.txt", content)

    def test_single_project_detection_specification(self):
        """
        Simulates @vercel/fs-detectors specification:
        Ensures that exactly ONE project candidate exists across all scanned directories.
        """
        scanned_dirs = [
            ".",
            "backend",
            "api",
            "autoprompt-prototype",
            "docs",
            "nginx",
            "scratch",
        ]

        detected_projects = []
        for dir_name in scanned_dirs:
            dir_path = REPO_ROOT if dir_name == "." else REPO_ROOT / dir_name
            if not dir_path.is_dir():
                continue

            has_vj = (dir_path / "vercel.json").is_file()
            has_req = (dir_path / "requirements.txt").is_file()
            has_pkg = (dir_path / "package.json").is_file()
            has_pyp = (dir_path / "pyproject.toml").is_file()

            # Under Vercel detection rules, a directory must have a manifest or config to be a project
            if has_vj or has_req or has_pkg or has_pyp:
                detected_projects.append(dir_name)

        self.assertEqual(
            detected_projects,
            ["."],
            f"Expected only root '.' to be detected as a Vercel project, but found: {detected_projects}. "
            f"Multiple detected projects trigger the Vercel monorepo selection prompt!",
        )


if __name__ == "__main__":
    unittest.main()

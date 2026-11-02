"""Tests for the README navigation audit script.

Run from the skill directory:
    python -m unittest discover -s tests -p "test_*.py"
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_readme_index.py"


def run_audit(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(cwd), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def snapshot(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


class AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="readme-index-"))
        probe = self.root / ".write-probe"
        try:
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        except OSError as error:  # e.g. a read-only sandbox
            self.skipTest(f"temporary directory is not writable here: {error}")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_chinese_space_and_url_encoded_links_are_valid(self) -> None:
        write(self.root, "README.md", "\n".join([
            "# Project",
            "",
            "- [raw space](tasks/我的 试验/REPORT.md)",
            "- [angle space](<tasks/你好 world/REPORT.md>)",
            "- [encoded](tasks/%E4%BD%A0%E5%A5%BD/REPORT.md)",
            "- [encoded space](tasks/my%20run/REPORT.md)",
            "",
        ]))
        for relative in ("tasks/我的 试验", "tasks/你好 world", "tasks/你好", "tasks/my run"):
            write(self.root, f"{relative}/REPORT.md", "# Run\n\nNo links.\n")

        result = run_audit(self.root, "--check", "--paths", "README.md")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("stale_link", result.stdout)
        self.assertNotIn("missing_parent_link", result.stdout)

    def test_baseline2_text_does_not_satisfy_baseline_child(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n")
        write(self.root, "task/README.md", "- [baseline2](runs/baseline2/)\n")
        write(self.root, "task/runs/baseline/REPORT.md", "# baseline\n")
        write(self.root, "task/runs/baseline2/REPORT.md", "# baseline2\n")

        result = run_audit(self.root, "--check", "--full")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing_parent_link", result.stdout)
        self.assertIn("child=task/runs/baseline", result.stdout)
        self.assertNotIn("child=task/runs/baseline2", result.stdout)

    def test_report_md_links_are_checked_and_report_is_entry(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n")
        write(self.root, "task/README.md", "- [Run](runs/baseline/REPORT.md)\n")
        write(self.root, "task/runs/baseline/REPORT.md",
              "# baseline\n\n- [missing](missing.md)\n")

        result = run_audit(self.root, "--check", "--full")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("stale_link", result.stdout)
        self.assertIn("task/runs/baseline/REPORT.md", result.stdout)

    def test_non_git_without_scope_reports_cannot_determine(self) -> None:
        write(self.root, "README.md", "# Project\n")

        result = run_audit(self.root, "--check")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Cannot determine scan scope", result.stderr)

        with_paths = run_audit(self.root, "--check", "--paths", "README.md")
        self.assertEqual(with_paths.returncode, 0, with_paths.stdout + with_paths.stderr)

    def test_check_exit_codes_for_clean_and_gap(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n")
        write(self.root, "task/README.md", "- [Run](runs/baseline/REPORT.md)\n")
        write(self.root, "task/runs/baseline/REPORT.md", "# baseline\n")

        clean = run_audit(self.root, "--check", "--full")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

        write(self.root, "task/README.md", "No navigation rows.\n")
        broken = run_audit(self.root, "--check", "--full")
        self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)
        self.assertIn("missing_parent_link", broken.stdout)

    def test_strict_upgrades_warnings_only_with_flag(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n- [Outside](../nowhere.md)\n")
        write(self.root, "task/README.md", "# Task\n")

        lax = run_audit(self.root, "--check", "--full")
        self.assertEqual(lax.returncode, 0, lax.stdout + lax.stderr)
        self.assertIn("stale_external_link", lax.stdout)

        strict = run_audit(self.root, "--check", "--strict", "--full")
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)

    def test_unknown_role_parent_is_not_escalated(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n")
        write(self.root, "task/README.md", "# Task\n\n- [Run](run/REPORT.md)\n")
        write(self.root, "task/run/REPORT.md", "# Run\n")

        result = run_audit(self.root, "--check", "--full")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("missing_parent_link", result.stdout)

    def test_default_run_writes_nothing(self) -> None:
        write(self.root, "README.md", "- [Task](task/)\n")
        write(self.root, "task/README.md", "- [Run](runs/baseline/REPORT.md)\n")
        write(self.root, "task/runs/baseline/REPORT.md", "# baseline\n")
        before = snapshot(self.root)

        result = run_audit(self.root, "--paths", "README.md")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.root / "_organizer").exists())

        report_dir = self.root / "reports"
        with_out = run_audit(self.root, "--paths", "README.md", "--out", str(report_dir))
        self.assertEqual(with_out.returncode, 0, with_out.stdout + with_out.stderr)
        self.assertTrue((report_dir / "readme_index_audit.json").is_file())
        self.assertTrue((report_dir / "readme_index_audit.md").is_file())

    def test_explicit_mtime_scope_and_json(self) -> None:
        write(self.root, "README.md", "# Project\n- [Task](task/)\n")
        write(self.root, "task/README.md", "# Task\n")

        result = run_audit(self.root, "--check", "--mtime-hours", "24")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        as_json = run_audit(self.root, "--mtime-hours", "24", "--json")
        payload = json.loads(as_json.stdout)
        self.assertEqual(payload["mode"], "mtime")
        self.assertFalse(payload["kb_mode"])

    def test_kb_mode_requires_section_entries_and_skips_inbox(self) -> None:
        write(self.root, "README.md", "\n".join([
            "# KB",
            "- [catalog](catalog/)",
            "- [inbox](inbox/)",
            "",
        ]))
        write(self.root, "catalog/entities.csv", "id\n")
        write(self.root, "inbox/note.md", "temporary\n")

        result = run_audit(self.root, "--check", "--full", "--kb-root", ".", "--json")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        missing = [gap for gap in payload["gaps"] if gap["type"] == "missing_entry"]
        folders = {gap["folder"] for gap in missing}
        self.assertIn("catalog", folders)
        self.assertNotIn("inbox", folders)


if __name__ == "__main__":
    unittest.main()

"""Refresh must not leave a route compiled from an older board structure."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kanban_context import (ContextError, DEFAULT_MEMORY, atomic_write_json,
                            list_role_score, refresh_snapshot, state_paths)


class RefreshCacheTests(unittest.TestCase):
    def test_current_and_legacy_stage_names(self):
        for name, role in [("等外部", "blocked"), ("等待反馈", "blocked"),
                           ("等验收", "review"), ("待审核", "review")]:
            with self.subTest(name=name):
                self.assertEqual(list_role_score(name, role, DEFAULT_MEMORY), 1.0)

    def test_refresh_invalidates_derived_pair_but_preserves_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = state_paths(Path(tmp))
            for key in ("memory", "route", "board"):
                atomic_write_json(paths[key], {"old": key})
            original_memory = paths["memory"].read_bytes()
            with patch("kanban_context.locate_planka_cli", return_value=Path("cli.py")), \
                 patch("kanban_context.run_planka_json", return_value={"items": [], "included": {"boards": []}}):
                refresh_snapshot(paths)
            self.assertTrue(paths["snapshot"].exists())
            self.assertFalse(paths["route"].exists())
            self.assertFalse(paths["board"].exists())
            self.assertEqual(paths["memory"].read_bytes(), original_memory)

    def test_failed_refresh_retains_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = state_paths(Path(tmp))
            for key in ("snapshot", "memory", "route", "board"):
                atomic_write_json(paths[key], {"old": key})
            before = {key: paths[key].read_bytes() for key in ("snapshot", "memory", "route", "board")}
            with patch("kanban_context.locate_planka_cli", return_value=Path("cli.py")), \
                 patch("kanban_context.run_planka_json", side_effect=ContextError("offline")):
                with self.assertRaises(ContextError):
                    refresh_snapshot(paths)
            self.assertEqual(before, {key: paths[key].read_bytes() for key in before})


if __name__ == "__main__":
    unittest.main()

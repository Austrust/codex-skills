#!/usr/bin/env python3
"""Regression tests for kanban_context.py."""

from __future__ import annotations

import unittest
from pathlib import Path

from kanban_context import (
    DEFAULT_MEMORY,
    ContextError,
    atomic_write_json,
    build_offline_snapshot,
    learn_route,
    load_memory,
    persist_route,
    route_task,
    select_route,
    state_paths,
)


def projects(*boards):
    return {
        "items": [{"id": "project-1", "name": "Research", "secret": "drop"}],
        "included": {"boards": list(boards)},
    }


def live_board(board_id, name, lists, cards=None):
    return {
        "item": {"id": board_id, "projectId": "project-1", "name": name},
        "included": {
            "lists": lists,
            "cards": cards or [],
            "taskLists": [],
            "tasks": [],
            "labels": [],
            "users": [{"id": "user-1", "email": "private@example.com"}],
        },
    }


def snapshot_with_two_boards():
    board_defs = [
        {"id": "board-patent", "projectId": "project-1", "name": "专利工作"},
        {"id": "board-paper", "projectId": "project-1", "name": "论文工作"},
    ]
    payloads = {
        "board-patent": live_board(
            "board-patent",
            "专利工作",
            [{"id": "patent-todo", "name": "待办"}, {"id": "patent-done", "name": "已完成"}],
            [
                {
                    "id": "p1",
                    "name": "完善超声PIV专利权利要求",
                    "description": "C:/work/patent; owner@example.com; Authorization: Bearer secret-value",
                    "listId": "patent-todo",
                }
            ],
        ),
        "board-paper": live_board(
            "board-paper",
            "论文工作",
            [{"id": "paper-todo", "name": "待办"}, {"id": "paper-review", "name": "待审核"}],
            [{"id": "m1", "name": "修改论文引言", "description": "C:/work/paper", "listId": "paper-todo"}],
        ),
    }
    return build_offline_snapshot(projects(*board_defs), payloads, "2026-07-18T00:00:00Z")


class KanbanContextTests(unittest.TestCase):
    def state_directory(self, name):
        root = Path(__file__).resolve().parents[1] / ".test-state"
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        for child in path.iterdir():
            if child.is_file():
                child.unlink()
        return path

    def test_snapshot_keeps_routing_data_and_drops_users(self):
        snapshot = snapshot_with_two_boards()
        self.assertEqual(len(snapshot["boards"]), 2)
        self.assertNotIn("users", snapshot["boards"][0]["included"])
        self.assertEqual(snapshot["projects"], [{"id": "project-1", "name": "Research"}])
        serialized = str(snapshot)
        self.assertNotIn("owner@example.com", serialized)
        self.assertNotIn("secret-value", serialized)

    def test_semantic_board_content_selects_patent_todo(self):
        result = route_task(
            snapshot_with_two_boards(),
            DEFAULT_MEMORY,
            {"title": "整理超声PIV专利权利要求", "status": "todo", "workspaceMarkers": ["C:/work/patent"]},
        )
        self.assertEqual(result["selected"]["boardId"], "board-patent")
        self.assertEqual(result["selected"]["listId"], "patent-todo")
        self.assertFalse(result["needsConfirmation"])

    def test_ambiguous_multi_board_route_requires_confirmation(self):
        result = route_task(snapshot_with_two_boards(), DEFAULT_MEMORY, {"title": "处理今天的任务", "status": "todo"})
        self.assertIsNone(result["selected"])
        self.assertTrue(result["needsConfirmation"])
        self.assertEqual(len(result["candidates"]), 2)

    def test_only_routable_board_is_selected(self):
        snapshot = snapshot_with_two_boards()
        snapshot["boards"] = snapshot["boards"][:1]
        result = route_task(snapshot, DEFAULT_MEMORY, {"title": "记录一个新想法", "status": "todo"})
        self.assertEqual(result["selected"]["boardId"], snapshot["boards"][0]["item"]["id"])

    def test_user_can_confirm_one_ambiguous_candidate(self):
        result = select_route(
            snapshot_with_two_boards(),
            DEFAULT_MEMORY,
            {"boardId": "board-paper", "listId": "paper-todo", "status": "todo"},
        )
        self.assertFalse(result["needsConfirmation"])
        self.assertEqual(result["selected"]["boardId"], "board-paper")
        self.assertEqual(result["selected"]["compileConfig"]["lists"]["todo"], "待办")

    def test_confirmed_workspace_route_personalizes_future_routing(self):
        learned = learn_route(
            DEFAULT_MEMORY,
            {
                "title": "第一次任务",
                "status": "todo",
                "workspaceMarkers": ["C:/work/patent"],
                "boardId": "board-patent",
                "listId": "patent-todo",
                "listName": "待办",
            },
            "2026-07-18T01:00:00Z",
        )
        result = route_task(
            snapshot_with_two_boards(),
            learned,
            {"title": "记录新任务", "status": "todo", "workspaceMarkers": ["C:/work/patent"]},
        )
        self.assertEqual(result["selected"]["boardId"], "board-patent")
        self.assertIn("learned workspace route", result["selected"]["reasons"])

    def test_learning_history_is_bounded(self):
        memory = {**DEFAULT_MEMORY, "routingHistory": [{"index": index} for index in range(200)]}
        learned = learn_route(
            memory,
            {
                "title": "New",
                "status": "todo",
                "boardId": "board-patent",
                "listId": "patent-todo",
                "listName": "待办",
            },
        )
        self.assertEqual(len(learned["routingHistory"]), 200)
        self.assertEqual(learned["routingHistory"][-1]["title"], "New")

    def test_route_persistence_writes_selected_config_and_board(self):
        paths = state_paths(self.state_directory("route"))
        snapshot = snapshot_with_two_boards()
        result = route_task(
            snapshot,
            DEFAULT_MEMORY,
            {"title": "专利任务", "status": "todo", "workspaceMarkers": ["C:/work/patent"]},
        )
        persist_route(paths, snapshot, result)
        self.assertTrue(paths["route"].exists())
        self.assertTrue(paths["board"].exists())

    def test_memory_is_created_in_global_state_directory(self):
        paths = state_paths(self.state_directory("memory"))
        memory = load_memory(paths["memory"])
        self.assertEqual(memory["schemaVersion"], 1)
        self.assertTrue(paths["memory"].exists())

    def test_secret_like_route_content_is_rejected(self):
        with self.assertRaisesRegex(ContextError, "credential"):
            route_task(
                snapshot_with_two_boards(),
                DEFAULT_MEMORY,
                {"title": "Authorization: Bearer secret", "status": "todo"},
            )

    def test_atomic_write_round_trip(self):
        path = self.state_directory("atomic") / "state.json"
        atomic_write_json(path, {"中文": "正常"})
        self.assertIn("正常", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for compile_plan.py."""

from __future__ import annotations

import unittest

from compile_plan import ValidationError, compile_plan


CONFIG = {
    "boardId": "board-1",
    "lists": {
        "todo": "待办",
        "in_progress": "进行中",
        "blocked": "等待反馈",
        "review": "待审核",
        "done": "已完成",
    },
    "taskListName": "下一步",
}


def board(cards=None):
    return {
        "item": {"id": "board-1", "name": "Work"},
        "included": {
            "lists": [{"id": f"list-{index}", "name": name} for index, name in enumerate(CONFIG["lists"].values())],
            "cards": cards or [],
        },
    }


def task(title="Implement feature", status="done", card_id=None):
    value = {
        "title": title,
        "status": status,
        "summary": f"Summary for {title}",
        "completed": ["Implemented and tested"],
        "artifacts": [f"C:/work/{title}.md"],
        "openItems": [],
    }
    if card_id:
        value["cardId"] = card_id
    return value


class CompilePlanTests(unittest.TestCase):
    def test_done_existing_card_and_new_next_card(self):
        summary = {
            "tasks": [task(card_id="card-1")],
            "primaryNextTask": {
                "title": "Review feature",
                "relationship": "new",
                "summary": "Review the implementation.",
                "steps": ["Inspect output", "Record feedback"],
            },
        }
        result = compile_plan(CONFIG, summary, board([{"id": "card-1", "name": "Implement feature"}]))
        self.assertEqual([op["action"] for op in result["operations"]], ["complete-card", "publish-card", "comment"])
        self.assertEqual(result["operations"][0]["completeTasks"], "all")
        self.assertEqual(result["operations"][0]["moveToList"], "已完成")
        self.assertEqual(result["operations"][1]["title"], "Review feature")

    def test_partial_task_adds_continuation_to_existing_card(self):
        summary = {
            "tasks": [task(status="in_progress", card_id="card-1")],
            "primaryNextTask": {
                "title": "Add integration coverage",
                "relationship": "continuation",
                "parentTaskTitle": "Implement feature",
                "steps": [],
            },
        }
        result = compile_plan(CONFIG, summary, board([{"id": "card-1", "name": "Implement feature"}]))
        self.assertEqual([op["action"] for op in result["operations"]], ["complete-card", "publish-card"])
        self.assertNotIn("completeTasks", result["operations"][0])
        self.assertEqual(result["operations"][1]["tasks"], ["Add integration coverage"])

    def test_explicit_card_id_uses_live_card_title_for_continuation(self):
        summary = {
            "tasks": [task("Conversation wording", "in_progress", "card-1")],
            "primaryNextTask": {
                "title": "Continue work",
                "relationship": "continuation",
                "parentTaskTitle": "Conversation wording",
                "steps": [],
            },
        }
        result = compile_plan(CONFIG, summary, board([{"id": "card-1", "name": "Canonical board title"}]))
        self.assertEqual(result["operations"][1]["title"], "Canonical board title")

    def test_blocked_and_review_tasks_move_separately(self):
        summary = {
            "tasks": [
                task("Blocked task", "blocked", "card-1"),
                task("Review task", "review", "card-2"),
            ],
            "primaryNextTask": {
                "title": "Request missing input",
                "relationship": "new",
                "steps": ["Contact owner"],
            },
        }
        cards = [{"id": "card-1", "name": "Blocked task"}, {"id": "card-2", "name": "Review task"}]
        result = compile_plan(CONFIG, summary, board(cards))
        moves = [op["moveToList"] for op in result["operations"] if op["action"] == "complete-card"]
        self.assertEqual(moves, ["等待反馈", "待审核"])

    def test_multiple_new_tasks_create_separate_cards_and_one_next_card(self):
        summary = {
            "tasks": [task("Task A", "done"), task("Task B", "review")],
            "primaryNextTask": {"title": "Task C", "relationship": "new", "steps": []},
        }
        result = compile_plan(CONFIG, summary, board())
        publishes = [op for op in result["operations"] if op["action"] == "publish-card"]
        self.assertEqual([op["title"] for op in publishes], ["Task A", "Task B", "Task C"])
        self.assertEqual(sum(op["title"] == "Task C" for op in publishes), 1)

    def test_normalized_match_requires_workspace_marker(self):
        summary = {
            "workspaceMarkers": ["C:/work/project"],
            "tasks": [task("Build API", "in_progress")],
            "primaryNextTask": {
                "title": "Add tests",
                "relationship": "continuation",
                "parentTaskTitle": "Build API",
                "steps": [],
            },
        }
        snapshot = board([{"id": "card-1", "name": "build-api", "description": "Workspace: C:/work/project"}])
        result = compile_plan(CONFIG, summary, snapshot)
        self.assertEqual(result["metadata"]["taskMatches"][0]["cardId"], "card-1")
        self.assertEqual(result["metadata"]["taskMatches"][0]["matchedBy"], "normalized_title_workspace")

    def test_ambiguous_exact_match_is_rejected(self):
        summary = {
            "tasks": [task("Duplicate", "in_progress")],
            "primaryNextTask": {
                "title": "Continue",
                "relationship": "continuation",
                "parentTaskTitle": "Duplicate",
                "steps": [],
            },
        }
        snapshot = board([{"id": "1", "name": "Duplicate"}, {"id": "2", "name": "Duplicate"}])
        with self.assertRaisesRegex(ValidationError, "multiple exact-title"):
            compile_plan(CONFIG, summary, snapshot)

    def test_missing_state_and_invalid_status_are_rejected(self):
        bad_config = {**CONFIG, "lists": {key: value for key, value in CONFIG["lists"].items() if key != "review"}}
        summary = {
            "tasks": [task(status="review")],
            "primaryNextTask": {"title": "Next", "relationship": "new", "steps": []},
        }
        with self.assertRaisesRegex(ValidationError, "requested task states"):
            compile_plan(bad_config, summary, board())
        summary["tasks"][0]["status"] = "unknown"
        with self.assertRaisesRegex(ValidationError, "must be one of"):
            compile_plan(CONFIG, summary, board())

    def test_same_input_is_idempotent(self):
        summary = {
            "tasks": [task(card_id="card-1")],
            "primaryNextTask": {"title": "Next", "relationship": "new", "steps": []},
        }
        snapshot = board([{"id": "card-1", "name": "Implement feature"}])
        self.assertEqual(compile_plan(CONFIG, summary, snapshot), compile_plan(CONFIG, summary, snapshot))

    def test_quick_capture_does_not_require_a_primary_next_task_or_five_lists(self):
        config = {"boardId": "board-1", "lists": {"todo": "待办"}, "taskListName": "下一步"}
        summary = {"tasks": [task("Capture this", "todo")], "primaryNextTask": None}
        snapshot = {
            "item": {"id": "board-1", "name": "Work"},
            "included": {"lists": [{"id": "list-1", "name": "待办"}], "cards": []},
        }
        result = compile_plan(config, summary, snapshot)
        publishes = [operation for operation in result["operations"] if operation["action"] == "publish-card"]
        self.assertEqual([operation["title"] for operation in publishes], ["Capture this"])
        self.assertIsNone(result["metadata"]["primaryNextTask"])

    def test_secret_like_content_is_rejected(self):
        summary = {
            "tasks": [task()],
            "primaryNextTask": {"title": "Next", "relationship": "new", "steps": []},
        }
        summary["tasks"][0]["summary"] = "Authorization: Bearer secret"
        with self.assertRaisesRegex(ValidationError, "credential"):
            compile_plan(CONFIG, summary, board())


if __name__ == "__main__":
    unittest.main()

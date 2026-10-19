import unittest
from copy import deepcopy
from compile_plan import compile_plan, ValidationError
from test_compile_plan import CONFIG, board, task
from kanban_context import ROLE_TERMS


class FlowTests(unittest.TestCase):
    def config(self, limit=1):
        return {**deepcopy(CONFIG), "wipLimit": limit}

    def proposed(self, title="New", status="in_progress"):
        return dict(task(title, status), intent="propose")

    def compile(self, tasks, cards=None, config=None):
        config = config or self.config()
        snapshot = board(cards)
        if config.get("wipLimit"):
            from shared_policy import reader
            snapshot["included"]["cards"].append({"id":"policy", "name":reader.TITLE, "listId":"list-0",
                "description":reader.render_policy({"schemaVersion":1, "wipLimit":config["wipLimit"], "wipListIds":["list-1","list-2","list-3"]})})
        return compile_plan(config, {"tasks": tasks}, snapshot)

    def test_capacity_blocks_start(self):
        with self.assertRaisesRegex(ValidationError, "WIP limit"):
            self.compile([self.proposed()], [{"id":"1", "name":"Busy", "listId":"list-1"}])

    def test_waiting_and_review_count(self):
        for list_id in ("list-2", "list-3"):
            with self.assertRaisesRegex(ValidationError, "WIP limit"):
                self.compile([self.proposed()], [{"id":"1", "name":"Busy", "listId":list_id}])

    def test_batch_starts_consume_capacity(self):
        with self.assertRaisesRegex(ValidationError, "WIP limit"):
            self.compile([self.proposed("A"), self.proposed("B")])

    def test_no_capacity_default(self):
        with self.assertRaisesRegex(ValidationError, "configured wipLimit"):
            self.compile([self.proposed()], config=CONFIG)

    def test_record_actual_overload_warns(self):
        result=self.compile([task("Actual", "in_progress")], [{"id":"1", "name":"Busy", "listId":"list-1"}])
        self.assertEqual(result["metadata"]["flow"]["wipAfter"],2)
        self.assertTrue(result["metadata"]["flow"]["warnings"])

    def test_ready_does_not_consume_capacity(self):
        result=self.compile([self.proposed(status="todo")], [{"id":"1", "name":"Busy", "listId":"list-1"}])
        self.assertEqual(result["metadata"]["flow"]["wipAfter"],1)

    def test_cannot_hide_started_work(self):
        with self.assertRaisesRegex(ValidationError, "hide WIP"):
            self.compile([self.proposed("Busy", "todo")], [{"id":"1", "name":"Busy", "listId":"list-1"}])

    def test_unfinished_and_ambiguous_dependencies_reject(self):
        t=dict(self.proposed(status="todo"), dependencies=["Parent"])
        for cards in ([{"id":"p", "name":"Parent", "listId":"list-1"}],
                      [{"id":"p", "name":"Parent", "listId":"list-4"},{"id":"q", "name":"Parent", "listId":"list-4"}]):
            with self.assertRaisesRegex(ValidationError, "dependency"):
                self.compile([t],cards)

    def test_completed_dependency_allows_start(self):
        t=dict(self.proposed(), dependencies=["p"])
        self.compile([t],[{"id":"p", "name":"Parent", "listId":"list-4"}])

    def test_external_dependency_needs_evidence(self):
        t=dict(self.proposed(), dependencies=["Delivery"])
        with self.assertRaisesRegex(ValidationError, "dependency"):
            self.compile([t])
        t["dependencyEvidence"]={"Delivery":"User confirmed received"}
        self.compile([t])

    def test_done_requires_per_criterion_evidence(self):
        t=task();t["evidence"]={}
        with self.assertRaisesRegex(ValidationError, "done requires evidence"):
            self.compile([t])

    def test_live_acceptance_cannot_be_omitted(self):
        b=board([{"id":"c", "name":"Implement feature", "listId":"list-1"}])
        b["included"].update(taskLists=[{"id":"tl", "cardId":"c", "name":"验收条件"}],tasks=[{"id":"check", "taskListId":"tl", "name":"Other criterion"}])
        with self.assertRaisesRegex(ValidationError,"done requires evidence"):
            compile_plan(self.config(),{"tasks":[task(card_id="c")]},b)

    def test_done_only_completes_acceptance(self):
        t=task(card_id="c"); criterion=t["acceptanceCriteria"][0]
        b=board([{"id":"c", "name":t["title"], "listId":"list-1"}])
        b["included"].update(taskLists=[{"id":"tl", "cardId":"c", "name":"验收条件"},{"id":"steps", "cardId":"c", "name":"下一步"}], tasks=[{"id":"check", "taskListId":"tl", "name":criterion},{"id":"step", "taskListId":"steps", "name":"Optional step"}])
        result=compile_plan(self.config(),{"tasks":[t]},b)
        self.assertEqual(result["operations"][0]["completeTasks"],[criterion])

    def test_completion_releases_capacity_in_order(self):
        result=self.compile([task("Busy","done","b"),self.proposed()], [{"id":"b", "name":"Busy", "listId":"list-1"}])
        self.assertEqual(result["metadata"]["flow"]["wipAfter"],1)

    def test_inbox_accepts_incomplete_capture(self):
        cfg={"boardId":"board-1", "lists":{"inbox":"收集箱"}}
        b={"item":{"id":"board-1"},"included":{"lists":[{"id":"in", "name":"收集箱"}],"cards":[]}}
        result=compile_plan(cfg,{"tasks":[{"title":"Idea","summary":"Source note","status":"inbox"}]},b)
        self.assertEqual(result["operations"][0]["list"],"收集箱")
        self.assertEqual(result["operations"][0]["tasks"],[])

    def test_inbox_and_archive_not_ready_or_done_aliases(self):
        self.assertNotIn("收集箱",ROLE_TERMS["todo"])
        self.assertNotIn("归档",ROLE_TERMS["done"])


if __name__=="__main__": unittest.main()

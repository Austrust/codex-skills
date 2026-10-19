import unittest
from copy import deepcopy
from compile_plan import compile_plan, ValidationError
from test_compile_plan import CONFIG, board, task
from shared_policy import reader
from kanban_context import DEFAULT_MEMORY, route_task
from test_kanban_context import snapshot_with_two_boards


def with_policy(limit=1):
    b=board()
    b["included"]["cards"].append({"id":"policy", "name":reader.TITLE, "listId":"list-1",
        "description":reader.render_policy({"schemaVersion":1,"wipLimit":limit,"wipListIds":["list-1","list-2","list-3"]})})
    return b


class SharedPolicyTests(unittest.TestCase):
    def test_remote_overrides_stale_local_config(self):
        t=dict(task("Start","in_progress"),intent="propose")
        b=with_policy(1)
        b["included"]["cards"].append({"id":"busy","name":"Busy","listId":"list-1"})
        with self.assertRaisesRegex(ValidationError,"WIP limit 1"):
            compile_plan({**CONFIG,"wipLimit":99}, {"tasks":[t]}, b)

    def test_no_remote_policy_never_falls_back(self):
        t=dict(task("Start","in_progress"),intent="propose")
        with self.assertRaisesRegex(ValidationError,"configured wipLimit"):
            compile_plan({**CONFIG,"wipLimit":99}, {"tasks":[t]}, board())

    def test_config_card_is_not_work(self):
        result=compile_plan(CONFIG,{"tasks":[dict(task("Start","in_progress"),intent="propose")]},with_policy())
        self.assertEqual(result["metadata"]["flow"]["wipBefore"],0)
        self.assertEqual(result["metadata"]["flow"]["wipAfter"],1)
        self.assertEqual(result["metadata"]["flow"]["policySource"]["cardId"],"policy")
        with self.assertRaisesRegex(ValidationError,"Policy cards"):
            compile_plan(CONFIG,{"tasks":[task(reader.TITLE,"todo")]},with_policy())

    def test_fresh_snapshot_overrides_cached_policy(self):
        cfg={**CONFIG, **reader.read_board_policy(with_policy(3))}
        result=compile_plan(cfg,{"tasks":[task("Ready","todo")]},with_policy(1))
        self.assertEqual(result["metadata"]["flow"]["wipLimit"],1)

    def test_route_ignores_local_preferences(self):
        snapshot=snapshot_with_two_boards()
        mem=deepcopy(DEFAULT_MEMORY)
        mem["preferences"]["boardPolicies"]={"board-patent":{"wipLimit":99}}
        route=route_task(snapshot,mem,{"title":"专利工作", "status":"todo", "workspaceMarkers":["C:/work/patent"]})
        self.assertIsNone(route["selected"]["compileConfig"]["wipLimit"])


if __name__=="__main__":unittest.main()

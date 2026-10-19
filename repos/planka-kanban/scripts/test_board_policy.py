import unittest
from copy import deepcopy
from board_policy import TITLE, PolicyError, read_board_policy, render_policy
from planka_cli import set_board_policy, apply_plan


def board():
    return {"item":{"id":"b"}, "included":{"lists":[{"id":"ready","name":"待办"},{"id":"doing","name":"进行中"}],"cards":[]}}


POLICY={"schemaVersion":1,"wipLimit":2,"wipListIds":["doing"]}


class FakeClient:
    def __init__(self): self.board=board(); self.writes=[]
    def request(self, method, path, data=None):
        if method=="GET":return deepcopy(self.board)
        self.writes.append((method,path,data))
        if method=="POST":
            self.board["included"]["cards"].append({"id":"policy","listId":"ready",**data})
        elif method=="PATCH":
            self.board["included"]["cards"][0].update(data)
        return {"item":self.board["included"]["cards"][0]}


class PolicyTests(unittest.TestCase):
    def make(self):
        b=board();b["included"]["cards"].append({"id":"p","name":TITLE,"listId":"ready","description":render_policy(POLICY)})
        return b
    def test_roundtrip_and_rename(self):
        b=self.make();p=read_board_policy(b)
        b["included"]["lists"][1]["name"]="执行"
        q=read_board_policy(b)
        self.assertEqual(q["wipLists"],["执行"])
        self.assertEqual(p["policySource"],q["policySource"])
    def test_missing_and_duplicate(self):
        self.assertIsNone(read_board_policy(board())["wipLimit"])
        b=self.make();b["included"]["cards"]*=2
        with self.assertRaises(PolicyError):read_board_policy(b)
    def test_malformed_and_invalid_values(self):
        for p in ({**POLICY,"wipLimit":True},{**POLICY,"wipLimit":0},{**POLICY,"wipListIds":["gone"]},{**POLICY,"command":"execute"}):
            b=self.make();b["included"]["cards"][0]["description"]=render_policy(p)
            with self.assertRaises(PolicyError):read_board_policy(b)
    def test_multiple_blocks_reject(self):
        b=self.make();b["included"]["cards"][0]["description"]*=2
        with self.assertRaises(PolicyError):read_board_policy(b)
    def test_surrounding_prose_preserved(self):
        old="Notes\n\n"+render_policy(POLICY)+"\nMore notes"
        new=render_policy({**POLICY,"wipLimit":3},old)
        self.assertIn("Notes",new);self.assertIn("More notes",new)
        self.assertEqual(new.count("```kanban-policy"),1)
    def test_dry_run_no_write_and_upsert_no_duplicate(self):
        c=FakeClient();spec={"boardId":"b","listId":"ready","policy":POLICY}
        set_board_policy(c,spec,True);self.assertEqual(c.writes,[])
        set_board_policy(c,spec);set_board_policy(c,{**spec,"policy":{**POLICY,"wipLimit":4}})
        self.assertEqual(len(c.board["included"]["cards"]),1)
        self.assertEqual(read_board_policy(c.board)["wipLimit"],4)
    def test_apply_rejects_changed_policy_before_writes(self):
        c=FakeClient();set_board_policy(c,{"boardId":"b","listId":"ready","policy":POLICY})
        source=read_board_policy(c.board)["policySource"]
        c.board["included"]["cards"][0]["description"]=render_policy({**POLICY,"wipLimit":1})
        c.writes=[]
        with self.assertRaisesRegex(SystemExit,"policy changed"):
            apply_plan(c,{"metadata":{"boardId":"b","flow":{"policySource":source,"wipBefore":0}},"operations":[{"action":"comment"}]})
        self.assertEqual(c.writes,[])
    def test_apply_rejects_changed_wip_before_writes(self):
        c=FakeClient();set_board_policy(c,{"boardId":"b","listId":"ready","policy":POLICY})
        source=read_board_policy(c.board)["policySource"]
        c.board["included"]["cards"].append({"id":"new","name":"New","listId":"doing"})
        c.writes=[]
        with self.assertRaisesRegex(SystemExit,"Live WIP changed"):
            apply_plan(c,{"metadata":{"boardId":"b","flow":{"policySource":source,"wipBefore":0}},"operations":[{"action":"comment"}]})
        self.assertEqual(c.writes,[])


if __name__=="__main__":unittest.main()

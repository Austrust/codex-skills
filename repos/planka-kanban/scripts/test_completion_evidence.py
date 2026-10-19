import unittest
from planka_cli import requested_tasks_to_complete

class EvidenceTests(unittest.TestCase):
    tasks=[{"id":"1","name":"A"},{"id":"2","name":"B"}]
    def test_blanket_completion_rejected(self):
        for spec in ({"completeTasks":"all"},{"allTasks":True}):
            with self.assertRaises(SystemExit): requested_tasks_to_complete(spec,self.tasks)
    def test_missing_evidence_rejected(self):
        with self.assertRaises(SystemExit): requested_tasks_to_complete({"completeTasks":["A"]},self.tasks)
    def test_only_evidenced_item_selected(self):
        self.assertEqual(requested_tasks_to_complete({"completeTasks":["A"],"evidence":{"A":"Verified output"}},self.tasks),self.tasks[:1])
    def test_ambiguous_names_rejected(self):
        with self.assertRaises(SystemExit): requested_tasks_to_complete({"completeTasks":["A"],"evidence":{"A":"Verified"}},self.tasks+self.tasks[:1])
    def test_move_only_still_supported(self):
        self.assertEqual(requested_tasks_to_complete({"moveToList":"Review"},self.tasks),[])

if __name__=="__main__": unittest.main()

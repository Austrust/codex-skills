"""Stateful offline API tests: no credentials or network calls."""
from copy import deepcopy
import unittest

from planka_cli import publish_card, apply_plan, PlankaError, comment_card


class FakePlanka:
    def __init__(self):
        self.board = {'id': 'board-1', 'name': 'Work', 'projectId': 'p'}
        self.lists = [{'id': f'list-{i}', 'name': name, 'type': 'active'}
                      for i, name in enumerate(('待办', '进行中', '等待反馈', '待审核', '已完成'))]
        self.cards, self.task_lists, self.tasks, self.comments = [], [], [], []
        self.writes = []
        self.fail_after_create = False
        self.fail_task_once = False

    def snapshot(self):
        return deepcopy({'item': self.board, 'included': {'lists': self.lists,
            'cards': self.cards, 'taskLists': self.task_lists, 'tasks': self.tasks}})

    def request(self, method, path, payload=None):
        parts = path.strip('/').split('/')
        if method == 'GET':
            if path == '/api/projects':
                return {'items': [{'id': 'p', 'name': 'Project'}], 'included': {'boards': [self.board]}}
            if path == '/api/boards/board-1':
                return self.snapshot()
            if parts[1] == 'cards':
                card = next(c for c in self.cards if c['id'] == parts[2])
                if len(parts) == 4 and parts[3] == 'comments':
                    return deepcopy({'items': [x for x in self.comments if x['cardId'] == card['id']]})
                tls = [x for x in self.task_lists if x['cardId'] == card['id']]
                return deepcopy({'item': card, 'included': {'taskLists': tls,
                    'tasks': [x for x in self.tasks if x['taskListId'] in {t['id'] for t in tls}]}})
        self.writes.append((method, path, deepcopy(payload)))
        if method == 'PATCH':
            collection = self.cards if parts[1] == 'cards' else self.tasks
            item = next(x for x in collection if x['id'] == parts[2])
            item.update(payload)
            return deepcopy({'item': item})
        if method == 'POST':
            kind = parts[-1]
            if kind == 'cards':
                item = dict(payload, id=f'c{len(self.cards)+1}', boardId='board-1', listId=parts[2])
                self.cards.append(item)
                if self.fail_after_create:
                    self.fail_after_create = False
                    raise PlankaError(None, 'Response lost after commit')
            elif kind == 'task-lists':
                item = dict(payload, id=f'tl{len(self.task_lists)+1}', cardId=parts[2])
                self.task_lists.append(item)
            elif kind == 'tasks':
                if self.fail_task_once:
                    self.fail_task_once = False
                    raise PlankaError(None, 'Transient task failure')
                item = dict(payload, id=f't{len(self.tasks)+1}', taskListId=parts[2])
                self.tasks.append(item)
            elif kind == 'comments':
                item = dict(payload, id=f'cm{len(self.comments)+1}', cardId=parts[2])
                self.comments.append(item)
            else:
                raise AssertionError((method, path))
            return deepcopy({'item': item})
        raise AssertionError((method, path))


class PublishIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = FakePlanka()
        self.spec = {'boardId': 'board-1', 'list': '待办', 'title': '分析与主图',
            'workItemKey': 'goal-figure', 'description': 'One outcome',
            'taskList': '执行步骤', 'tasks': ['分析', '制图'], 'moveExistingToTargetList': True}

    def test_replay_keeps_one_card_and_one_copy_of_each_step(self):
        for _ in range(3):
            publish_card(self.client, self.spec)
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(len(self.client.task_lists), 1)
        self.assertEqual(len(self.client.tasks), 2)

    def test_lost_response_then_renamed_and_moved_card_is_reused(self):
        self.client.fail_after_create = True
        with self.assertRaises(PlankaError):
            publish_card(self.client, self.spec)
        self.client.cards[0].update(name='用户改名', listId='list-1')
        publish_card(self.client, self.spec)
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(self.client.cards[0]['name'], '用户改名')
        self.assertEqual(len(self.client.tasks), 2)

    def test_partial_checklist_failure_recovers(self):
        self.client.fail_task_once = True
        plan = {'operations': [dict(self.spec, action='publish-card')]}
        self.assertFalse(apply_plan(self.client, plan)['ok'])
        self.assertTrue(apply_plan(self.client, plan)['ok'])
        self.assertEqual((len(self.client.cards), len(self.client.task_lists), len(self.client.tasks)), (1, 1, 2))

    def test_explicit_id_survives_rename_and_description_edit_preserves_key(self):
        publish_card(self.client, self.spec)
        self.client.cards[0]['name'] = 'Renamed'
        publish_card(self.client, {'boardId': 'board-1', 'cardId': 'c1', 'list': '待办',
            'title': 'Old title', 'description': 'Edited', 'tasks': ['Decision'], 'taskList': '执行步骤'})
        self.assertEqual(len(self.client.cards), 1)
        self.assertIn('[kanban-item:goal-figure]', self.client.cards[0]['description'])
        self.assertEqual(self.client.cards[0]['name'], 'Renamed')

    def test_missing_explicit_id_never_creates_replacement(self):
        with self.assertRaisesRegex(SystemExit, 'refusing to create'):
            publish_card(self.client, dict(self.spec, cardId='missing'))
        self.assertEqual(self.client.writes, [])

    def test_duplicate_key_and_conflicting_title_fail_before_write(self):
        publish_card(self.client, self.spec)
        self.client.writes.clear()
        with self.assertRaisesRegex(SystemExit, 'different workItemKey'):
            publish_card(self.client, dict(self.spec, workItemKey='other'))
        self.client.cards.append(dict(self.client.cards[0], id='c2'))
        with self.assertRaisesRegex(SystemExit, 'Multiple cards share'):
            publish_card(self.client, self.spec)
        self.assertEqual(self.client.writes, [])

    def test_same_title_elsewhere_requires_move_instead_of_duplicate(self):
        publish_card(self.client, self.spec)
        self.client.cards[0]['listId'] = 'list-1'
        self.client.writes.clear()
        spec = {k: v for k, v in self.spec.items() if k != 'workItemKey'}
        with self.assertRaisesRegex(SystemExit, 'outside the target list'):
            publish_card(self.client, dict(spec, moveExistingToTargetList=False))
        self.assertEqual(self.client.writes, [])
        self.assertEqual(len(self.client.cards), 1)

    def test_duplicate_names_in_one_payload_create_only_one_task(self):
        publish_card(self.client, dict(self.spec, tasks=['检查', '检查']))
        self.assertEqual(len(self.client.tasks), 1)

    def test_operation_comment_is_deduplicated_even_if_retry_text_changes(self):
        publish_card(self.client, self.spec)
        spec = {'cardId': 'c1', 'comment': '[to-kanban:abcd]\nOriginal', 'commentMode': 'append-once'}
        comment_card(self.client, spec)
        comment_card(self.client, dict(spec, comment='[to-kanban:abcd]\nReworded retry'))
        self.assertEqual(len(self.client.comments), 1)
        comment_card(self.client, dict(spec, comment='[to-kanban:ef01]\nNew update'))
        self.assertEqual(len(self.client.comments), 2)

    def test_empty_plan_is_noop(self):
        self.assertTrue(apply_plan(self.client, {'operations': []})['ok'])
        self.assertEqual(self.client.writes, [])


if __name__ == '__main__':
    unittest.main()

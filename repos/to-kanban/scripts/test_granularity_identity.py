"""Outcome grouping and compile/apply/recompile integration regressions."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'planka-kanban/scripts'))
from test_publish_identity import FakePlanka
from planka_cli import apply_plan
from compile_plan import compile_plan, ValidationError
from test_compile_plan import CONFIG, task, new_next, board


class GranularityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = FakePlanka()

    def compile(self, summary):
        return compile_plan(CONFIG, summary, self.client.snapshot())

    def apply(self, plan):
        result = apply_plan(self.client, plan)
        self.assertTrue(result['ok'], result)

    def test_one_goal_multiple_outputs_remains_one_card(self):
        t = task('完成三工况分析与选图结论', 'todo')
        t.update(artifacts=['data.csv', 'figure.png', 'decision.md'],
                 steps=['分析数据', '绘制主图', '比较工况并决定是否采用'])
        summary = {'tasks': [t], 'operationId': 'capture-1'}
        plan = self.compile(summary)
        self.assertEqual(plan['metadata']['granularity']['newCardCount'], 1)
        self.apply(plan)
        self.apply(plan)
        self.apply(self.compile(summary))
        self.apply(self.compile(summary))
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(len(self.client.tasks), 4)
        self.assertEqual(len(self.client.comments), 1)

    def test_same_goal_fragments_require_both_split_conditions(self):
        a, b = task('分析', 'todo'), task('绘图', 'todo')
        a['goalId'] = b['goalId'] = 'same-goal'
        for condition in (None, 'independentValue', 'splitReason'):
            parts = deepcopy([a, b])
            for i, t in enumerate(parts):
                t['taskKey'] = str(i)
                if condition:
                    t[condition] = 'Only one half of the split test'
            with self.assertRaisesRegex(ValidationError, 'same goal must stay'):
                self.compile({'tasks': parts})

    def test_justified_split_is_allowed(self):
        parts = [task('独立交付算法库', 'todo'), task('独立交付采集硬件', 'todo')]
        for i, t in enumerate(parts):
            t.update(goalId='system', taskKey=f'part-{i}', independentValue='Can be accepted and reused independently',
                     splitReason='Separate owners and delivery dates')
        self.apply(self.compile({'tasks': parts}))
        self.assertEqual(len(self.client.cards), 2)

    def test_distinct_outcomes_need_new_card_reasons(self):
        parts = [task('A', 'todo'), task('B', 'todo')]
        parts[1].pop('newCardReason')
        with self.assertRaisesRegex(ValidationError, 'multiple new cards require'):
            self.compile({'tasks': parts})
        parts[1]['newCardReason'] = 'Separate user request'
        self.apply(self.compile({'tasks': parts}))
        self.assertEqual(len(self.client.cards), 2)

    def test_part_keys_are_scoped_to_their_goal(self):
        parts = [dict(task('A', 'todo'), taskKey='report'), dict(task('B', 'todo'), taskKey='report')]
        self.apply(self.compile({'tasks': parts}))
        self.assertEqual(len(self.client.cards), 2)

    def test_many_existing_updates_do_not_require_new_card_batch_reason(self):
        parts = [task(str(i), 'todo', f'c{i}') for i in range(4)]
        self.client.cards = [{'id': f'c{i}', 'boardId': 'board-1', 'listId': 'list-0',
                              'name': str(i), 'type': 'project'} for i in range(4)]
        plan = self.compile({'tasks': parts})
        self.assertEqual(plan['metadata']['granularity'],
            {'newCardCount': 0, 'updatedCardCount': 4, 'batchReason': None})
        self.apply(plan)
        self.assertEqual(len(self.client.cards), 4)

    def test_batch_needs_merge_review(self):
        summary = {'tasks': [task(str(i), 'todo') for i in range(4)]}
        with self.assertRaisesRegex(ValidationError, 'batchReason'):
            self.compile(summary)
        summary['batchReason'] = 'User explicitly requested four independently deliverable goals'
        self.assertEqual(self.compile(summary)['metadata']['granularity']['newCardCount'], 4)

    def test_existing_goal_renamed_updates_instead_of_creating(self):
        original = task('Original', 'todo')
        summary = {'tasks': [original]}
        self.apply(self.compile(summary))
        self.client.cards[0]['name'] = 'Board rename'
        rewritten = dict(original, title='Conversation rewording', steps=['补充比较结论'])
        plan = self.compile({'tasks': [rewritten]})
        self.assertEqual(plan['metadata']['granularity']['newCardCount'], 0)
        self.assertEqual(plan['metadata']['taskMatches'][0]['matchedBy'], 'work_item_key')
        self.apply(plan)
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(self.client.cards[0]['name'], 'Board rename')

    def test_partial_create_then_recompile_recovers_acceptance_and_steps(self):
        t = task('Retry', 'todo')
        t['steps'] = ['分析并记录结论']
        summary = {'tasks': [t], 'operationId': 'lost-response'}
        self.client.fail_after_create = True
        result = apply_plan(self.client, self.compile(summary))
        self.assertFalse(result['ok'])
        self.client.cards[0]['name'] = 'Renamed after creation'
        for _ in range(2):
            self.apply(self.compile(summary))
        self.assertEqual((len(self.client.cards), len(self.client.task_lists), len(self.client.tasks)), (1, 2, 2))
        self.assertEqual(len(self.client.comments), 1)

    def test_partial_done_create_recovers_and_completes_acceptance(self):
        summary = {'tasks': [task('Finished', 'done')]}
        self.client.fail_after_create = True
        self.assertFalse(apply_plan(self.client, self.compile(summary))['ok'])
        self.apply(self.compile(summary))
        self.apply(self.compile(summary))
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(len(self.client.tasks), 1)
        self.assertTrue(self.client.tasks[0]['isCompleted'])
        self.assertEqual(len(self.client.comments), 1)

    def test_next_task_matching_started_or_done_card_does_not_rewind_it(self):
        for list_id in ('list-1', 'list-4'):
            with self.subTest(list_id=list_id):
                self.client = FakePlanka()
                self.apply(self.compile({'tasks': [task('Next', 'todo')]}))
                self.client.cards[0]['listId'] = list_id
                summary = {'tasks': [], 'primaryNextTask': new_next('Next')}
                plan = self.compile(summary)
                self.assertEqual(plan['operations'], [])
                self.apply(plan)
                self.assertEqual(self.client.cards[0]['listId'], list_id)
                self.assertEqual(len(self.client.cards), 1)

    def test_next_task_repeated_publish_is_matched_before_planning(self):
        summary = {'tasks': [], 'primaryNextTask': new_next('Next')}
        self.apply(self.compile(summary))
        plan = self.compile(summary)
        self.assertEqual(plan['operations'], [])
        self.assertFalse(plan['metadata']['taskMatches'][0]['willCreate'])

    def test_interrupted_next_task_publish_recovers_checklists(self):
        summary = {'tasks': [], 'primaryNextTask': new_next('Next', ['Compare options'])}
        self.client.fail_after_create = True
        self.assertFalse(apply_plan(self.client, self.compile(summary))['ok'])
        self.apply(self.compile(summary))
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(len(self.client.tasks), 2)
        self.assertEqual(self.compile(summary)['operations'], [])

    def test_same_goal_new_next_is_rejected_use_continuation(self):
        t = task('Current', 'todo')
        n = new_next('Make figure')
        n['goalId'] = t['goalId']
        with self.assertRaisesRegex(ValidationError, 'same goal must stay'):
            self.compile({'tasks': [t], 'primaryNextTask': n})

    def test_update_id_does_not_change_when_card_is_discovered(self):
        summary = {'tasks': [task('Stable', 'todo')]}
        first = self.compile(summary)
        self.apply(first)
        second = self.compile(summary)
        self.assertEqual(first['metadata']['updateId'], second['metadata']['updateId'])

    def test_operation_id_survives_rewording_but_new_updates_get_new_id(self):
        a = {'tasks': [task('Stable', 'todo')], 'operationId': 'op-1'}
        b = deepcopy(a)
        b['tasks'][0]['summary'] = 'Reworded retry'
        self.assertEqual(self.compile(a)['metadata']['updateId'], self.compile(b)['metadata']['updateId'])
        b['operationId'] = 'op-2'
        self.assertNotEqual(self.compile(a)['metadata']['updateId'], self.compile(b)['metadata']['updateId'])

    def test_legacy_explicit_id_preserves_card_with_new_title(self):
        self.client.cards = [{'id': 'legacy', 'boardId': 'board-1', 'listId': 'list-0',
                              'name': 'Legacy title', 'type': 'project'}]
        t = task('New wording', 'todo', 'legacy')
        t['steps'] = ['比较方案并记录决策']
        self.apply(self.compile({'tasks': [t]}))
        self.assertEqual(len(self.client.cards), 1)
        self.assertEqual(self.client.cards[0]['name'], 'Legacy title')

    def test_duplicate_identity_fails_instead_of_choosing_arbitrarily(self):
        summary = {'tasks': [task('A', 'todo')]}
        self.apply(self.compile(summary))
        self.client.cards.append(dict(self.client.cards[0], id='duplicate'))
        with self.assertRaisesRegex(ValidationError, 'multiple cards share'):
            self.compile(summary)

    def test_nothing_to_sync_is_valid(self):
        self.assertEqual(self.compile({'tasks': []})['operations'], [])


if __name__ == '__main__':
    unittest.main()

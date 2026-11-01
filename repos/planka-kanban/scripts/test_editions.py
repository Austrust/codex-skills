"""Edition isolation and Pro write contract tests; no live mutations."""
import os
import unittest
from unittest.mock import patch
from planka_editions import discover
from planka_pro import execute
from planka_transport import PlankaError, PlankaClient, redact


class Server:
    def __init__(self, pro=True, version=None):
        self.profile = {'version': version or ('2.5.0' if pro else '2.1.1')}
        if pro:
            self.profile['license'] = {'status': 'valid'}
        self.calls = []
        self.cards = {'1': {'id': '1', 'listId': '2', 'name': 'Source'}}

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == '/api/bootstrap':
            return {'item': self.profile}
        if method == 'GET':
            if path == '/api/lists/2':
                return {'item': {'id': '2', 'type': 'active'}}
            if path == '/api/lists/2/cards':
                return {'items': list(self.cards.values())}
            if path.startswith('/api/cards/'):
                return {'item': dict(self.cards[path.split('/')[3]])}
            return {'items': []}
        if method == 'PATCH':
            self.cards['1'].update(data)
            return {'item': self.cards['1']}
        self.cards['3'] = {'id': '3', 'listId': '2', **data}
        return {'item': self.cards['3']}


@patch.dict(os.environ, {'PLANKA_EDITION': 'auto'})
class EditionTests(unittest.TestCase):
    def test_community_blocks_pro_without_mutation(self):
        c = Server(False)
        self.assertEqual(discover(c)['edition'], 'community')
        with self.assertRaises(PlankaError):
            execute(c, {'action': 'teams'})
        self.assertTrue(all(call[1] == '/api/bootstrap' for call in c.calls))

    def test_unknown_and_new_version_not_assumed_compatible(self):
        for c in (Server(False, '9.0.0'), Server(True, '2.6.0')):
            with self.assertRaises(PlankaError):
                execute(c, {'action': 'teams'})

    def test_conflicting_override_fails(self):
        with patch.dict(os.environ, {'PLANKA_EDITION': 'community'}):
            with self.assertRaises(PlankaError):
                discover(Server())

    def test_404_fallback_but_not_403(self):
        for status in (404, 403):
            c = Server()
            with patch.object(c, 'request', side_effect=[PlankaError(status, 'test'), {'item': {'version': '2.1.1'}}]):
                if status == 404:
                    self.assertEqual(discover(c)['edition'], 'community')
                else:
                    with self.assertRaises(PlankaError):
                        discover(c)

    def test_dry_run_and_verified_link_reuse(self):
        c = Server()
        spec = {'action': 'link-card', 'cardId': '1', 'listId': '2', 'position': 65536}
        self.assertTrue(execute(c, spec, True)['dryRun'])
        self.assertTrue(all(x[0] == 'GET' for x in c.calls))
        self.assertTrue(execute(c, spec)['verified'])
        self.assertTrue(execute(c, spec)['reused'])
        self.assertEqual(sum(x[0] == 'POST' for x in c.calls), 1)

    def test_template_explicit_create_and_payload(self):
        c = Server()
        spec = {'action': 'apply-template', 'cardId': '1', 'listId': '2', 'position': 0}
        with self.assertRaises(PlankaError):
            execute(c, spec)
        spec['createNew'] = True
        self.assertTrue(execute(c, spec)['verified'])
        self.assertIn(('POST', '/api/cards/1/apply-template', {'listId': '2', 'position': 0}), c.calls)

    def test_patch_allowlist_and_verification(self):
        c = Server()
        spec = {'action': 'update-card', 'cardId': '1', 'fields': {'isDraft': False, 'startDate': None}}
        self.assertTrue(execute(c, spec)['verified'])
        spec['fields'] = {'isPublic': True}
        with self.assertRaises(PlankaError):
            execute(c, spec)

    def test_linked_source_and_invalid_id_rejected(self):
        c = Server()
        c.cards['1']['linkedCardId'] = '9'
        for cid in ('1', '../1'):
            with self.assertRaises(PlankaError):
                execute(c, {'action': 'update-card', 'cardId': cid, 'fields': {'isDraft': True}})
        self.assertTrue(all(x[0] == 'GET' for x in c.calls))

    def test_search_encoded(self):
        c = Server()
        execute(c, {'action': 'search', 'query': 'a&b'})
        self.assertEqual(c.calls[-1][1], '/api/search?query=a%26b')

    def test_auth_step_not_used_as_token(self):
        c = PlankaClient('https://example.invalid')
        with patch.object(c, 'request', return_value={'item': {'pendingToken': 'hidden'}}):
            with self.assertRaises(PlankaError):
                c.login('user', 'password')
        self.assertIsNone(c.token)
        self.assertEqual(redact({'smtpPassword': 'secret'})['smtpPassword'], '<redacted>')

    def test_common_workflows_reject_linked_placement(self):
        from test_publish_identity import FakePlanka
        from planka_cli import publish_card, complete_card
        c = FakePlanka()
        c.cards.append({'id': '1', 'boardId': 'board-1', 'listId': 'list-0',
                        'name': 'Linked', 'linkedCardId': '99'})
        with self.assertRaises(SystemExit):
            publish_card(c, {'boardId': 'board-1', 'list': '待办', 'title': 'Linked'})
        with self.assertRaises(SystemExit):
            complete_card(c, {'cardId': '1', 'comment': 'done'})
        self.assertEqual(c.writes, [])


if __name__ == '__main__':
    unittest.main()

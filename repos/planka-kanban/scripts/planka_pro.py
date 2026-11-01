"""PLANKA Pro 2.5.0 operations, separate from the community workflow."""
import math
from urllib.parse import quote, urlencode
from planka_transport import PlankaError
from planka_editions import require_pro

READS = {
    'teams': '/api/teams',
    'board-templates': '/api/global-board-templates',
    'card-templates': '/api/card-template-catalog',
    'personal-card-templates': '/api/personal-card-templates',
    'template-destinations': '/api/card-template-destinations',
}
PANELS = {'recently-touched-by-me', 'member-cards-with-activity', 'due-cards',
          'recent-contributors', 'collaborators', 'pulse', 'forgotten', 'config'}


def identifier(spec, key):
    value = spec.get(key)
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise PlankaError(None, f'{key} must be a numeric ID string')
    return value


def execute(client, spec, dry_run=False):
    if not isinstance(spec, dict):
        raise PlankaError(None, 'Pro spec must be an object')
    action = spec.get('action')
    require_pro(client)
    if action in READS:
        return client.request('GET', READS[action])
    if action == 'search':
        query = spec.get('query')
        if not isinstance(query, str) or not query.strip() or len(query) > 128:
            raise PlankaError(None, 'query must contain 1–128 characters')
        return client.request('GET', '/api/search?' + urlencode({'query': query}))
    if action == 'dashboard':
        panel = spec.get('panel', 'due-cards')
        if panel not in PANELS:
            raise PlankaError(None, 'Unknown dashboard panel')
        return client.request('GET', '/api/dashboard/' + panel)
    if action in ('link-access', 'custom-field-entries'):
        cid = identifier(spec, 'cardId')
        suffix = 'link-access' if action == 'link-access' else 'custom-field-group-entries'
        return client.request('GET', f'/api/cards/{cid}/{suffix}')
    if action == 'board-template-config':
        bid = identifier(spec, 'boardId')
        return client.request('GET', f'/api/boards/{bid}/template-config')
    if action not in ('link-card', 'apply-template', 'update-card'):
        raise PlankaError(None, f'Unsupported Pro action: {action}')

    cid = identifier(spec, 'cardId')
    source = client.request('GET', f'/api/cards/{cid}')['item']
    if source.get('linkedCardId'):
        raise PlankaError(None, 'Resolve the canonical source card before writing a linked card')
    if action == 'update-card':
        data = spec.get('fields')
        allowed = {'startDate', 'dueDate', 'isDueCompleted', 'locationName', 'isDraft'}
        if not isinstance(data, dict) or not data or set(data) - allowed:
            raise PlankaError(None, 'fields supports startDate, dueDate, isDueCompleted, locationName, isDraft')
        for key, value in data.items():
            if key in ('isDraft', 'isDueCompleted'):
                if not isinstance(value, bool) and not (key == 'isDueCompleted' and value is None):
                    raise PlankaError(None, f'{key} must be boolean')
            elif value is not None and not isinstance(value, str):
                raise PlankaError(None, f'{key} must be string or null')
        method, path = 'PATCH', f'/api/cards/{cid}'
    else:
        lid = identifier(spec, 'listId')
        target = client.request('GET', f'/api/lists/{lid}')['item']
        if target.get('type') != 'active':
            raise PlankaError(None, 'Destination must be an active list')
        position = spec.get('position')
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position) or position < 0:
            raise PlankaError(None, 'position must be a finite nonnegative number')
        if action == 'link-card':
            existing = client.request('GET', f'/api/lists/{lid}/cards').get('items', [])
            matches = [c for c in existing if c.get('linkedCardId') == cid]
            if len(matches) > 1:
                raise PlankaError(None, 'Multiple existing links; resolve explicitly')
            if matches:
                return {'action': action, 'reused': True, 'item': matches[0]}
            data = {'linkedCardId': cid, 'position': position}
            path = f'/api/lists/{lid}/card-links'
        else:
            # Template application creates a new card; it is not an update of cardId.
            if spec.get('createNew') is not True:
                raise PlankaError(None, 'apply-template creates a new card; specify createNew: true')
            data = {'listId': lid, 'position': position}
            if 'name' in spec:
                if not isinstance(spec['name'], str) or not spec['name'].strip():
                    raise PlankaError(None, 'name must be a nonempty string')
                data['name'] = spec['name']
            path = f'/api/cards/{cid}/apply-template'
        method = 'POST'
    preview = {'action': action, 'method': method, 'path': path, 'data': data}
    if dry_run:
        return {'dryRun': True, 'operation': preview}
    result = client.request(method, path, data)
    result_id = result.get('item', {}).get('id')
    if not result_id:
        raise PlankaError(None, 'Write response lacks card ID; reconcile before retrying')
    actual = client.request('GET', f'/api/cards/{quote(str(result_id), safe="")}')
    expected = data if action == 'update-card' else {'listId': spec['listId']}
    if action == 'link-card':
        expected['linkedCardId'] = cid
    if any(actual['item'].get(k) != v for k, v in expected.items()):
        raise PlankaError(None, 'Post-write verification failed; reconcile before retrying', {'cardId': result_id})
    return {'action': action, 'verified': True, 'result': actual}

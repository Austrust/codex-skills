"""Edition discovery; common commands do not depend on Pro endpoints."""
import os
from planka_transport import PlankaError


def discover(client):
    try:
        payload = client.request('GET', '/api/bootstrap')
    except PlankaError as exc:
        if exc.status != 404:
            raise
        payload = client.request('GET', '/api/config')
    item = payload.get('item', {})
    version = item.get('version')
    if isinstance(item.get('license'), dict):
        edition = 'pro'
    elif isinstance(version, str) and version.startswith(('2.1.', '2.2.')):
        edition = 'community'
    else:
        edition = 'unknown'
    requested = os.environ.get('PLANKA_EDITION', 'auto').lower()
    if requested not in ('auto', 'community', 'pro'):
        raise PlankaError(None, 'PLANKA_EDITION must be auto, community or pro')
    if requested != 'auto' and edition != 'unknown' and requested != edition:
        raise PlankaError(None, 'Configured edition conflicts with live server')
    return {'edition': edition, 'version': version, 'requestedEdition': requested,
            'pro250Supported': edition == 'pro' and version == '2.5.0'}


def require_pro(client):
    profile = discover(client)
    if not profile['pro250Supported']:
        raise PlankaError(None, 'Pro operations require verified PLANKA Pro 2.5.0', profile)
    return profile


def register_commands(sub, make_client, output, load_spec):
    p = sub.add_parser('capabilities', help='Read-only edition/version discovery')
    p.set_defaults(func=lambda args: output(discover(make_client())))
    p = sub.add_parser('pro', help='Isolated Pro 2.5.0 operations')
    p.add_argument('--file', help='UTF-8 JSON operation spec')
    p.add_argument('--stdin', action='store_true')
    p.add_argument('--dry-run', action='store_true')

    def run(args):
        from planka_pro import execute
        output(execute(make_client(), load_spec(args), dry_run=args.dry_run))
    p.set_defaults(func=run)

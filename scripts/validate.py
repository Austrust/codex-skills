"""Audit a collection snapshot and optionally compare an installed copy.

Uses only the Python standard library. Provenance commits describe the original import.
"""
import argparse
import configparser
import subprocess
import hashlib
import json
import re
from pathlib import Path


def files(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*')
        if p.is_file()
        and not {'.git', '__pycache__', '.pytest_cache', '.test-state'}.intersection(p.relative_to(root).parts)
        and p.suffix not in {'.pyc', '.pyo'}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-root', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'manifest/skills.json').read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version') != 2 or manifest.get('repository_model') != 'hybrid':
        raise ValueError('Expected a schema 2 hybrid manifest')
    entries = manifest['skills']
    submodules = {e['submodule_path']: e for e in entries if e['storage'] == 'submodule'}
    config = configparser.ConfigParser()
    config.read(root / '.gitmodules', encoding='utf-8-sig')
    declarations = {config[s]['path']: dict(config[s]) for s in config.sections()}
    if set(declarations) != set(submodules):
        raise ValueError('Manifest and .gitmodules paths differ')
    for path, entry in submodules.items():
        if declarations[path]['url'] != entry['repository'] or declarations[path]['branch'] != entry['branch']:
            raise ValueError(f'Upstream declaration mismatch: {path}')
    if (root / '.git').exists():
        index = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--stage'], text=True, encoding='utf-8')
        gitlinks = {line.split('\t', 1)[1] for line in index.splitlines() if line.startswith('160000 ')}
        if gitlinks != set(submodules):
            raise ValueError('Gitlinks must contain exactly the declared third-party submodules')
    names = [e['name'] for e in entries]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate skill names')
    by_name = {e['name']: e for e in entries}
    done, active = set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f'Dependency cycle: {name}')
        if name in done:
            return
        active.add(name)
        for dep in by_name[name].get('dependencies', []):
            visit(dep)
        active.remove(name)
        done.add(name)

    rows = []
    for entry in entries:
        name = entry['name']
        visit(name)
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ValueError(f'Invalid skill name: {name}')
        source = (root / entry['source_path']).resolve()
        source.relative_to(root)
        text = (source / 'SKILL.md').read_text(encoding='utf-8-sig')
        front = re.match(r'\A---\s*\n(.*?)\n---(?:\s|$)', text, re.S)
        if not front or not re.search(r'^description:\s*\S', front[1], re.M):
            raise ValueError(f'Missing required front matter: {name}')
        if not re.search(r'^name:\s*[\"\x27]?' + re.escape(name) + r'[\"\x27]?\s*$', front[1], re.M):
            raise ValueError(f'Name mismatch: {name}')
        package = root / Path(entry['source_path']).parts[0] / Path(entry['source_path']).parts[1]
        if entry['storage'] == 'vendored':
            if (package / '.git').exists():
                raise ValueError(f'Embedded Git metadata in personal source: {name}')
            if any(key in entry for key in ('submodule_path', 'pinned_commit', 'repository', 'branch')):
                raise ValueError(f'Obsolete personal-repository fields: {name}')
            if not re.fullmatch(r'[0-9a-f]{40}', entry['provenance']['commit']):
                raise ValueError(f'Invalid import provenance: {name}')
        elif entry['storage'] == 'submodule':
            if (package / '.git').exists():
                head = subprocess.check_output(['git', '-C', str(package), 'rev-parse', 'HEAD'], text=True).strip()
                if head != entry['pinned_commit']:
                    raise ValueError(f'Upstream checkout and manifest pin differ: {name}')
        else:
            raise ValueError(f'Unknown source storage: {name}')
        expected = files(source)
        row = {'name': name, 'files': len(expected), 'sha256': expected,
               'storage': entry['storage'],
               'source_version': entry.get('pinned_commit', entry.get('provenance', {}).get('commit'))}
        if args.installed_root:
            actual = files(args.installed_root / name)
            if expected != actual:
                raise ValueError(f'Installed files differ: {name}')
            row['installed_match'] = True
        rows.append(row)
    report = {'skills': rows, 'count': len(rows),
              'note': 'Hybrid source audit; personal provenance is historical, third-party pins match checked-out sources.'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(rows)} skills, {sum(r["files"] for r in rows)} files; dependencies and metadata checked.')
    if args.installed_root:
        print('PASS: installed file sets and SHA-256 hashes match sources.')


if __name__ == '__main__':
    main()

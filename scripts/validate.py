"""Audit a collection snapshot and optionally compare an installed copy.

Uses only the Python standard library. Provenance commits describe the original import.

Without `--skill` the whole collection is validated with the repository-wide
declaration, gitlink, and pin checks. With one or more `--skill` names
(repeatable) the audit switches to local validation: only the selected skills
and their manifest dependencies are checked, so unrelated skills cannot block a
targeted post-install check.
"""
import argparse
import configparser
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


SKIP_PARTS = {'.git', '__pycache__', '.pytest_cache', '.test-state'}
SKIP_SUFFIXES = {'.pyc', '.pyo'}
FILE_STATUSES = ('identical', 'newline_only', 'content_diff')


def files(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*')
        if p.is_file()
        and not SKIP_PARTS.intersection(p.relative_to(root).parts)
        and p.suffix not in SKIP_SUFFIXES
    }


def normalized_hash(path):
    """Hash text after stripping BOM, normalizing newlines, and trimming line ends.

    Returns None for files that cannot be decoded as UTF-8 text, so binary
    payloads are never misclassified as newline-only differences.
    """
    try:
        text = path.read_bytes().decode('utf-8-sig')
    except (OSError, UnicodeDecodeError):
        return None
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = '\n'.join(line.rstrip() for line in text.split('\n')).rstrip('\n')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def classify_file(source_root, installed_root, relative, expected_hash, installed_hash):
    if expected_hash == installed_hash:
        return 'identical'
    expected_normalized = normalized_hash(source_root / relative)
    installed_normalized = normalized_hash(installed_root / relative)
    if expected_normalized is not None and expected_normalized == installed_normalized:
        return 'newline_only'
    return 'content_diff'


def compare_installed(name, source, installed):
    """Compare one skill directory against its installed copy.

    Returns (expected_files, file_statuses, counts, overall_status, missing).
    overall_status is content_diff when any file differs in substance, otherwise
    newline_only when only encoding/newline differences remain, else identical.
    """
    expected = files(source)
    counts = {status: 0 for status in FILE_STATUSES}
    if not installed.is_dir():
        counts['content_diff'] = len(expected)
        return expected, {}, counts, 'content_diff', True
    actual = files(installed)
    statuses = {}
    for relative in sorted(set(expected) | set(actual)):
        if relative not in expected or relative not in actual:
            statuses[relative] = 'content_diff'
        else:
            statuses[relative] = classify_file(
                source, installed, relative, expected[relative], actual[relative]
            )
    for status in statuses.values():
        counts[status] += 1
    if counts['content_diff']:
        overall = 'content_diff'
    elif counts['newline_only']:
        overall = 'newline_only'
    else:
        overall = 'identical'
    return expected, statuses, counts, overall, False


def select_skills(entries, requested):
    """Return (dependency-first order of selected names, name -> entry map)."""
    by_name = {entry['name']: entry for entry in entries}
    unknown = sorted(set(requested) - set(by_name))
    if unknown:
        raise ValueError('Unknown skill(s): ' + ', '.join(unknown))
    order, done, active = [], set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f'Dependency cycle: {name}')
        if name in done:
            return
        active.add(name)
        for dependency in by_name[name].get('dependencies', []):
            if dependency not in by_name:
                raise ValueError(f'Unknown dependency: {dependency} (required by {name})')
            visit(dependency)
        active.remove(name)
        done.add(name)
        order.append(name)

    for name in requested:
        visit(name)
    return order, by_name


def check_repository_layout(root, entries):
    """Repository-wide checks: declarations, gitlink set, and manifest pins."""
    submodules = {entry['submodule_path']: entry for entry in entries if entry['storage'] == 'submodule'}
    config = configparser.ConfigParser()
    config.read(root / '.gitmodules', encoding='utf-8-sig')
    declarations = {config[section]['path']: dict(config[section]) for section in config.sections()}
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


def check_entry(root, entry, installed_root):
    """Validate one skill entry's metadata and, optionally, its installed copy."""
    name = entry['name']
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
    if installed_root:
        _, statuses, counts, overall, missing = compare_installed(name, source, installed_root / name)
        row['installed_match'] = overall == 'identical'
        row['file_status'] = {'status': overall, 'missing': missing, **counts}
        if overall != 'identical':
            row['changed_files'] = [relative for relative, status in sorted(statuses.items())
                                    if status != 'identical'] or sorted(expected)
            row['content_diff_files'] = [relative for relative, status in sorted(statuses.items())
                                         if status == 'content_diff']
            row['newline_only_files'] = [relative for relative, status in sorted(statuses.items())
                                         if status == 'newline_only']
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-root', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--skill', action='append', metavar='NAME',
                        help='Validate only this skill and its manifest dependencies (repeatable). '
                             'Without it the full collection is validated.')
    args = parser.parse_args()
    local = bool(args.skill)
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'manifest/skills.json').read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version') != 2 or manifest.get('repository_model') != 'hybrid':
        raise ValueError('Expected a schema 2 hybrid manifest')
    entries = manifest['skills']
    names = [entry['name'] for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate skill names')

    if local:
        selected, by_name = select_skills(entries, args.skill)
        selected_entries = [by_name[name] for name in selected]
    else:
        selected = names
        select_skills(entries, names)
        check_repository_layout(root, entries)
        selected_entries = entries

    rows = []
    nonidentical = []
    for entry in selected_entries:
        row = check_entry(root, entry, args.installed_root)
        rows.append(row)
        if row.get('file_status', {}).get('status', 'identical') != 'identical':
            nonidentical.append(row)

    summary = {status: 0 for status in FILE_STATUSES}
    for row in rows:
        status = row.get('file_status', {}).get('status')
        if status:
            summary[status] += 1

    report = {'mode': 'local' if local else 'full',
              'selected': selected,
              'skills': rows,
              'count': len(rows),
              'note': 'Hybrid source audit; personal provenance is historical, third-party pins match checked-out sources.'}
    if args.installed_root:
        report['file_status'] = summary
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if local:
        print(f'Mode: local (selected: {", ".join(selected)})')
        print('Note: local validation checks only the selected skills and their dependencies; '
              'repository-wide .gitmodules/gitlink/pin checks are skipped.')
    else:
        print(f'Mode: full ({len(rows)} skills)')
    print(f'PASS: {len(rows)} skills, {sum(row["files"] for row in rows)} files; dependencies and metadata checked.')

    if args.installed_root:
        failed = []
        for row in rows:
            details = row['file_status']
            counts = (f'identical={details["identical"]} newline_only={details["newline_only"]} '
                      f'content_diff={details["content_diff"]}')
            status = details['status']
            if details['missing']:
                print(f'content_diff: {row["name"]} (installed copy missing; {counts})')
            elif status == 'content_diff':
                changed = row.get('content_diff_files') or row.get('changed_files', [])
                preview = ', '.join(changed[:5]) + (' ...' if len(changed) > 5 else '')
                print(f'content_diff: {row["name"]} ({counts}; changed: {preview})')
            elif status == 'newline_only':
                print(f'newline_only: {row["name"]} ({counts})')
            else:
                print(f'identical: {row["name"]} ({counts})')
            if status != 'identical' and (not local or status == 'content_diff' or details['missing']):
                failed.append(row)
        if failed:
            print(f'FAIL: {len(failed)} skill(s) differ from installed copies: '
                  + ', '.join(row['name'] for row in failed))
            return 1
        if nonidentical:
            print('PASS: installed file sets match sources; differences are newline/encoding only.')
        else:
            print('PASS: installed file sets and SHA-256 hashes match sources.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ValueError as exc:
        print(f'FAIL: {exc}')
        sys.exit(1)

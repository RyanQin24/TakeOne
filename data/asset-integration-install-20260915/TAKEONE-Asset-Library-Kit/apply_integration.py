"""Install and connect the asset library after an all-files conflict preflight.

Default is check-only. --apply writes recoverable, bounded changes to the selected
checkout. It never calls an AI provider, opens a serial port, or changes calibration.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4


@dataclass(frozen=True)
class Change:
    relative: str
    before: bytes | None
    after: bytes


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_path(root: Path, relative: str) -> Path:
    parts = relative.split('/')
    if any(part in ('', '.', '..') or '\\' in part or ':' in part for part in parts):
        raise ValueError(f'Unsafe installation path: {relative}')
    candidate = root.joinpath(*parts)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError(f'Installation path escapes the checkout: {relative}')
    return candidate


def project_root(root: Path) -> Path:
    root = root.expanduser().resolve()
    for relative in ('packages/takeone', 'apps/rehearsal/dist'):
        if not target_path(root, relative).is_dir():
            raise ValueError(f'Not a TAKE ONE checkout: {root}')
    return root


def build_plan(kit: Path, root: Path) -> list[Change]:
    """Read and validate everything before changing a single application file."""
    root = project_root(root)
    specification = json.loads((kit / 'patches.json').read_text(encoding='utf-8'))
    if specification['schema_version'] != 1:
        raise ValueError('Unsupported integration patch version')
    groups: dict[str, list[dict]] = {}
    for item in specification['patches']:
        groups.setdefault(item['path'], []).append(item)
    changes: list[Change] = []
    accepted = json.loads((kit / 'accepted-payload-hashes.json').read_text(encoding='utf-8'))
    state_file = target_path(root, 'data/asset-library-installation.json')
    installed = json.loads(state_file.read_text(encoding='utf-8'))['files'] if state_file.exists() else {}
    # Modules/data first; existing integration points are applied last.
    payload = kit / 'payload'
    for source in sorted(payload.rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts:
            continue
        relative = source.relative_to(payload).as_posix()
        if relative in groups:
            raise ValueError(f'Payload would replace a surgical patch target: {relative}')
        target = target_path(root, relative)
        before = target.read_bytes() if target.exists() else None
        after = source.read_bytes()
        if before == after:
            continue
        previous = installed.get(relative, {})
        if before is not None and previous.get('source_sha256') == sha(after) and previous.get('installed_sha256') == sha(before):
            continue
        if before is not None and sha(before) not in accepted.get(relative, []):
            raise FileExistsError(f'Existing added-file content differs: {relative}; preserve and reconcile it first')
        changes.append(Change(relative, before, after))
    for relative, replacements in groups.items():
        target = target_path(root, relative)
        before = target.read_bytes()
        text = before.decode('utf-8')
        newline = '\r\n' if '\r\n' in text else '\n'
        normalized = text.replace('\r\n', '\n')
        for item in replacements:
            old, new = item['old'], item['new']
            # Idempotence is explicit. A near match is not permission to rewrite.
            if normalized.count(new) == 1:
                if normalized.count(old) != new.count(old):
                    raise ValueError(f'Mixed old/new integration anchors in {relative}; reconcile before installing')
                continue
            if normalized.count(old) != 1:
                raise ValueError(f'Expected one inspected anchor in {relative}; no files have been changed')
            normalized = normalized.replace(old, new, 1)
        after = normalized.replace('\n', newline).encode('utf-8')
        if after != before:
            changes.append(Change(relative, before, after))
    for change in changes:
        if change.relative.endswith('.py'):
            ast.parse(change.after, filename=change.relative)
        if change.relative.endswith('.json'):
            json.loads(change.after)
    return changes


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.takeone-write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply_plan(root: Path, changes: list[Change]) -> Path | None:
    root = project_root(root)
    if not changes:
        return None
    # Detect any edit between preflight and writing, before creating backups.
    for change in changes:
        target = target_path(root, change.relative)
        current = target.read_bytes() if target.exists() else None
        if current != change.before:
            raise RuntimeError(f'Concurrent edit detected: {change.relative}; install cancelled')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    recovery = target_path(root, 'data/recovery/asset-scenes-' + stamp)
    recovery.mkdir(parents=True, exist_ok=False)
    journal = []
    for change in changes:
        if change.before is not None:
            atomic_write(target_path(recovery / 'before', change.relative), change.before)
        journal.append(dict(path=change.relative, before_sha256=None if change.before is None else sha(change.before),
                            after_sha256=sha(change.after)))
    manifest = recovery / 'manifest.json'
    atomic_write(manifest, json.dumps(dict(state='prepared', changes=journal), indent=2).encode())
    applied: list[Change] = []
    try:
        for change in changes:
            target = target_path(root, change.relative)
            current = target.read_bytes() if target.exists() else None
            if current != change.before:
                raise RuntimeError(f'Concurrent edit detected at write: {change.relative}')
            atomic_write(target, change.after)
            applied.append(change)
    except BaseException:
        for change in reversed(applied):
            target = target_path(root, change.relative)
            # Never overwrite another actor's edit during recovery.
            if target.read_bytes() != change.after:
                continue
            if change.before is None:
                target.unlink()
            else:
                atomic_write(target, change.before)
        atomic_write(manifest, json.dumps(dict(state='failed_check_before_retry', changes=journal), indent=2).encode())
        raise
    atomic_write(manifest, json.dumps(dict(state='applied', changes=journal), indent=2).encode())
    return recovery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('C:/TakeOne'))
    parser.add_argument('--apply', action='store_true', help='Apply the preflighted, backed-up changes')
    parser.add_argument('--download-starter', action='store_true', help='Then download the four reviewed CC0 packs')
    parser.add_argument('--verify', action='store_true', help='Then run the existing full repository verification')
    args = parser.parse_args()
    kit = Path(__file__).resolve().parent
    try:
        root = project_root(args.root)
        changes = build_plan(kit, root)
        print(f'{len(changes)} files would change:')
        for change in changes:
            print(('ADD  ' if change.before is None else 'EDIT ') + change.relative)
        if not args.apply:
            print('CHECK ONLY. No files changed. Add --apply to install.')
            return 0
        recovery = apply_plan(root, changes)
        print(f'Installed. Recovery: {recovery}' if recovery else 'Already installed; no changes.')
        interpreter = root / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
        if (args.download_starter or args.verify) and not interpreter.is_file():
            raise ValueError('Project interpreter missing. Installation is saved; run the existing setup before verification.')
        failed = False
        if args.download_starter:
            result = subprocess.run([str(interpreter), '-m', 'takeone.asset_library', '--root', str(root),
                                     'download', '--starter'], cwd=root, check=False)
            failed |= result.returncode != 0
            if result.returncode:
                print('Pack download/import failed. Code is installed; no missing model is claimed installed.', file=sys.stderr)
        if args.verify:
            # Format only newly supplied Python code, not unrelated project files.
            supplied = [str(root / p.relative_to(kit / 'payload')) for p in (kit / 'payload').rglob('*.py')]
            for action in (['check', '--fix'], ['format']):
                result = subprocess.run([str(interpreter), '-m', 'ruff', *action, *supplied], cwd=root, check=False)
                failed |= result.returncode != 0
            report = root / 'data/asset-scenes-verification'
            result = subprocess.run([str(interpreter), str(root / 'scripts/verify.py'), '--output-dir', str(report)],
                                    cwd=root, check=False)
            failed |= result.returncode != 0
            print(f'Verification reports: {report}')
        files = {}
        for source in (kit / 'payload').rglob('*'):
            if source.is_file() and '__pycache__' not in source.parts:
                relative = source.relative_to(kit / 'payload').as_posix()
                files[relative] = dict(source_sha256=sha(source.read_bytes()),
                                       installed_sha256=sha(target_path(root, relative).read_bytes()))
        atomic_write(target_path(root, 'data/asset-library-installation.json'),
                     json.dumps(dict(schema_version=1, files=files), indent=2).encode())
        if recovery is not None:
            manifest = recovery / 'manifest.json'
            journal = json.loads(manifest.read_text(encoding='utf-8'))
            for item in journal['changes']:
                item['final_sha256'] = sha(target_path(root, item['path']).read_bytes())
            journal['verification_requested'] = args.verify
            journal['requested_checks_succeeded'] = not failed if args.verify else None
            atomic_write(manifest, json.dumps(journal, indent=2).encode())
        return int(failed)
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        print(f'Integration stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

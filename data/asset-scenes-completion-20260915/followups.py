"""Small provenance and asynchronous-disposal fixes; record current originals."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'C:\TakeOne')
OUT = Path(__file__).parent
updates = {
    'packages/takeone/director/planning.py': [
        ('from .service import OwnerReplacedError', 'from .scene_assets import director_guidance\nfrom .service import OwnerReplacedError'),
        ('"filming_skill": skill_text(),', '"filming_skill": skill_text(),\n                "scene_dressing": director_guidance(),'),
    ],
    'apps/rehearsal/dist/asset-library/asset-loader.js': [
        ('    this.epoch = new LoadEpoch();', '    this.epoch = new LoadEpoch();\n    this.disposed = false;'),
        ('  async load(definitions) {\n    this.clear();', "  async load(definitions) {\n    if (this.disposed) throw new Error('Asset layer has been disposed.');\n    this.clear();"),
        ('      throw error;\n    }\n  }\n\n  pose(filmingSeconds)', '      throw error;\n    } finally {\n      if (this.disposed) this.library.cache.clearIdle();\n    }\n  }\n\n  pose(filmingSeconds)'),
        ('  dispose() {\n    this.clear();', '  dispose() {\n    this.disposed = true;\n    this.clear();'),
    ],
}
prepared = {}
for name, replacements in updates.items():
    raw = (ROOT / name).read_bytes()
    text = raw.decode('utf-8').replace('\r\n', '\n')
    for old, new in replacements:
        assert text.count(old) == 1, name
        text = text.replace(old, new, 1)
    prepared[name] = (raw, text)
records = []
for name, (raw, text) in prepared.items():
    path = ROOT / name
    if path.read_bytes() != raw:
        raise ValueError('Concurrent edit: ' + name)
    backup = OUT / 'followup-before' / name
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(raw)
    eol = '\r\n' if b'\r\n' in raw else '\n'
    result = text.replace('\n', eol).encode('utf-8')
    with path.open('r+b') as stream:
        stream.write(result)
        stream.truncate()
    records.append(dict(path=name, before=hashlib.sha256(raw).hexdigest(), after=hashlib.sha256(result).hexdigest()))
    print('Patched', name)
(OUT / 'followup-changes.json').write_text(json.dumps(records, indent=2), encoding='utf-8')

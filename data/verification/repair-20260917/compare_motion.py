import hashlib
import json
import sys
from pathlib import Path

from takeone.motion.plan import encoded
from takeone.previs.templates import compile_template

root = Path('C:/TakeOne')
baseline = json.loads((root/'tests/fixtures/legacy-movement-frames.json').read_text())
results = []
for old in baseline['templates']:
    result = compile_template(old['settings'])
    frames = [{k: f[k] for k in baseline['frame_keys'] if k in f} for f in result['preview']['frames']]
    row = {'template_id':old['template_id']}
    for label, data in [('frame',frames),('samples',result['plan']['samples']),('cart',result['plan']['cart_schedule'])]:
        row[label+'_sha256'] = hashlib.sha256(encoded(data)).hexdigest()
    results.append(row)
Path(sys.argv[1]).write_text(json.dumps(results,indent=2))
print(f'Wrote {len(results)} movement fingerprints')

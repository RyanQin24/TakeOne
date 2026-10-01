"""Apply reviewed asset-editor changes; preserve and check each current source."""
from pathlib import Path
import hashlib
import json
import os
import time

ROOT = Path(r'C:\TakeOne')
OUT = Path(__file__).parent
originals, pending = {}, {}

def patch(name, old, new):
    path = ROOT / name
    if name not in originals:
        saved = OUT / "owned-before" / name
        originals[name] = saved.read_bytes() if saved.exists() else path.read_bytes()
        pending[name] = originals[name].decode('utf-8').replace('\r\n', '\n')
    if pending[name].count(old) != 1:
        raise ValueError(f'{name}: expected exactly one matching source block')
    pending[name] = pending[name].replace(old, new, 1)

def apply():
    for name, raw in originals.items():
        eol = '\r\n' if b'\r\n' in raw else '\n'
        expected = pending[name].replace('\n', eol).encode('utf-8')
        if (ROOT / name).read_bytes() not in (raw, expected):
            raise ValueError('Concurrent edit; no files changed: ' + name)
    records = []
    for name, text in pending.items():
        path = ROOT / name
        backup = OUT / 'owned-before' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(originals[name])
        eol = '\r\n' if b'\r\n' in originals[name] else '\n'
        result = text.replace('\n', eol).encode('utf-8')
        temporary = path.with_name(path.name + '.asset-completion.tmp')
        if path.read_bytes() != result:
            temporary.write_bytes(result)
            for attempt in range(10):
                if path.read_bytes() != originals[name]:
                    raise ValueError('Concurrent edit: ' + name)
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        # Some Windows readers permit writing but hold off replacement.
                        # The OS must still grant write access; do not change permissions.
                        if path.read_bytes() != originals[name]:
                            raise ValueError('Concurrent edit: ' + name)
                        with path.open('r+b') as stream:
                            stream.write(result)
                            stream.truncate()
                            stream.flush()
                        print('Used existing-file write (replacement was locked):', name)
                        break
                    time.sleep(0.2)
        records.append(dict(path=name, before=hashlib.sha256(originals[name]).hexdigest(), after=hashlib.sha256(result).hexdigest()))
        print('Patched', name)
    (OUT / 'changes.json').write_text(json.dumps(records, indent=2), encoding='utf-8')

patch('packages/takeone/director/scenes.py', 'def scene_properties():', 'def scene_properties(require_inventory=False):')
patch('packages/takeone/director/scenes.py', '    return dict(\n        space_id=string(40),', '    result = dict(\n        space_id=string(40),')
patch('packages/takeone/director/scenes.py', '                asset_id=string(180),', '                asset_id=string(180),\n                availability=dict(type="string", enum=["unconfirmed", "present", "proposed", "virtual_only"]),')
patch('packages/takeone/director/scenes.py', '\n\ndef shot_properties():', '\n    if not require_inventory:\n        result["objects"]["items"]["required"].remove("availability")\n    return result\n\n\ndef shot_properties():')
patch('packages/takeone/director/creative.py', 'scene["properties"].update(scene_properties())', 'scene["properties"].update(scene_properties(require_inventory=require_movement))')
patch('apps/rehearsal/server.py', 'for package in ("director", "voice", "recording")', 'for package in ("director", "voice", "recording", "asset_library")')
patch('packages/takeone/director/scene-dressing/SKILL.md', 'A mesh is only a visualization. Use location_notes to distinguish confirmed inventory\nfrom proposed dressing and virtual-only references. Ask about unavailable necessities.', 'A mesh is only a visualization. Set availability to present only when the user has\nconfirmed that physical prop; otherwise use proposed, virtual_only or unconfirmed.\nUse location_notes to describe that distinction. Ask about unavailable necessities.\nKeep object_id short (40 characters maximum) and independent of the long asset_id.')
patch('packages/takeone/director/provider.py', '        raw = encode(body).encode()', '''        if kind == "creative_plan" and "movement_catalog" in payload:
            assets = payload["movement_catalog"]["scene_catalog"]["objects"]
            shape = body["text"]["format"]["schema"]["properties"]["scenes"]["items"]
            shape["properties"]["objects"]["items"]["properties"]["asset_id"]["enum"] = [
                entry["id"] for entry in assets
            ]
        raw = encode(body).encode()''')
patch('apps/rehearsal/dist/director.js', 'import { illustrations, thumbnail }', "import {createSceneObject, bindAssetSearch, availabilityLabels} from './asset-library/scene-inventory.js';\nimport { illustrations, thumbnail }")
patch('apps/rehearsal/dist/director.js', 'const objectOptions=Object.fromEntries(catalog.objects.map(o=>[o.id,o.name]));', '''const selected = new Set((scene.objects || []).map(object => object.asset_id));
  const initial = catalog.objects.filter(entry => !entry.id.startsWith('lib:') || selected.has(entry.id));
  const objectOptions=Object.fromEntries(initial.map(o=>[o.id,o.name]));
  for (const id of selected) if (!(id in objectOptions)) objectOptions[id] = 'Missing model: ' + id;''')
patch('apps/rehearsal/dist/director.js', "const html=field('Scene title','title',scene.title,'input')+field('Location','location',scene.location)+", "const html='<p><a href=\"/asset-library/browser.html\" target=\"_blank\" rel=\"noopener\">Browse installed 3D models</a></p>'+\n    field('Scene title','title',scene.title,'input')+field('Location','location',scene.location)+")
patch('apps/rehearsal/dist/director.js', "field('Object','asset-'+i,o.asset_id,'select',objectOptions)+field('Label'", "field('Object','asset-'+i,o.asset_id,'select',objectOptions)+field('Physical availability','availability-'+i,o.availability||'unconfirmed','select',availabilityLabels)+field('Label'")
patch('apps/rehearsal/dist/director.js', "scene.objects.push({object_id:`${entry.id}-${crypto.randomUUID().slice(0,8)}`,asset_id:entry.id,label:data.get('new-label').trim(),position_m:[4,4,entry.default_size_m[2]/2],size_m:[...entry.default_size_m],yaw_rad:0});", "scene.objects.push(createSceneObject(entry, data.get('new-label')));")
patch('apps/rehearsal/dist/director.js', "({...o,asset_id:data.get('asset-'+i),label:data.get('label-'+i).trim()", "({...o,asset_id:data.get('asset-'+i),availability:data.get('availability-'+i),label:data.get('label-'+i).trim()")
patch('apps/rehearsal/dist/director.js', "    await saveDocument(doc);\n  });\n}\nfunction castFields", "    await saveDocument(doc);\n  });\n  bindAssetSearch($('editFields'), catalog.objects);\n}\nfunction castFields")
patch('apps/rehearsal/dist/director.js', ".map(a=>({actor_id:a.actor_id,offset_m:", ".map(a=>({...scene.cast?.find(member=>member.actor_id===a.actor_id),actor_id:a.actor_id,offset_m:")
patch('apps/rehearsal/dist/director.js', 'doc.actors = names.map((name, index) => ({\n      actor_id:', 'doc.actors = names.map((name, index) => ({\n      ...doc.actors[index],\n      actor_id:')
patch('apps/rehearsal/dist/shot-direction.js', '// Film direction uses the edit clock;', "import {inventoryLines} from './asset-library/scene-inventory.js';\n\n// Film direction uses the edit clock;")
patch('apps/rehearsal/dist/shot-direction.js', '      sceneId=shot.scene_id;', "      const inventory = inventoryLines(scene);\n      if(inventory.length)lines.push('Set inventory (operator declarations; not physical qualification):', ...inventory.map(value=>'- '+value), '');\n      sceneId=shot.scene_id;")
patch('apps/rehearsal/package.json', 'node --check dist/shot-direction.js', 'node --check dist/asset-library/scene-inventory.js && node --check dist/shot-direction.js')
apply()

"""Explicitly repair the retained Luna draft; no new provider call or hardware."""
import copy
import json
import urllib.request
import uuid
from takeone.director.creative import validate_plan
from takeone.director.contracts import ProductionBrief
from takeone.director.studio import movement_catalog

BASE = 'http://127.0.0.1:8766'
SID = 'd7393e81-4725-4f52-a15c-195623d82655'
JOB = '92f2b08f-8542-49cd-aba1-bd071a2ae1ca'


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=180))


detail = get('/api/director/sessions/' + SID)
job = next(item for item in detail['jobs'] if item['job_id'] == JOB)
doc = copy.deepcopy(job['result']['rejected_proposal'])
palettes = [dict(cloth='#17263c', pants='#34363c', skin='#cfa783', hair='#382f27', shoe='#e2dcc7'),
            dict(cloth='#a45c43', pants='#222222', skin='#cfa783', hair='#382f27', shoe='#222222')]
for actor, palette in zip(doc['actors'], palettes):
    actor['appearance'] = palette
templates = {item['id']: set(item['parameters']) | {'focal_mm'} for item in movement_catalog()['templates']}
edits = []
for scene in doc['scenes']:
    for shot in scene['shots']:
        if shot['selected_line'] == 1 and len(shot['lines']) == 1:
            shot['selected_line'] = 0
        req = shot['motion_requirements']
        if req['direction'].startswith('orbit'):
            req['signed_progress_m'] = 0
        if not req['actor_travel_m']:
            req['simultaneous_s'] = 0
        for performer in shot.get('performers', []):
            for field in ('body_heading_rad', 'look_at', 'gestures'):
                keys = performer[field]
                if keys and keys[0]['at'] > 0:
                    keys.insert(0, {**copy.deepcopy(keys[0]), 'at': 0})
                if keys and keys[-1]['at'] < 1:
                    keys.append({**copy.deepcopy(keys[-1]), 'at': 1})
        movement = shot['movement']
        positions = movement['cinematography']['channels']['actor_position_m']
        for start, end in zip(positions, positions[1:]):
            if start['ease'] == 'hold' and start['value'] != end['value']:
                start['ease'] = 'linear'
        allowed = templates[movement['template_id']]
        unused = [p['name'] for p in movement['parameters'] if p['name'] not in allowed]
        if unused:
            edits.append(dict(shot=shot['shot_id'], unused_parameters_removed=unused))
            movement['parameters'] = [p for p in movement['parameters'] if p['name'] in allowed]
doc['questions'].append('Technical recovery: proxy colors converted to hex; attention endpoints held; orbital distance expressed in radians; unused template settings removed; sole dialogue options selected with zero-based indices; walking positions interpolated linearly instead of teleporting. This remains an edited AI proposal requiring rehearsal review.')
validate_plan(doc, ProductionBrief.parse(detail['session']['brief']), detail['creative_context'])
runtime = get('/api/director/runtime')
session = detail['session']
body = dict(schema_version=1, operation_id=str(uuid.uuid4()), runtime_epoch=runtime['runtime_epoch'],
            expires_monotonic_ns=str(int(runtime['now_monotonic_ns']) + int(runtime['command_ttl_ns'])),
            scope=dict(session_id=SID, expected_revision=session['revision'], cancellation_generation=session['cancellation_generation'],
                       take_id=None, plan_id=None), action='recover_proposal', payload=dict(job_id=JOB, document=doc))
request = urllib.request.Request(BASE + '/api/director/creative', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
result = json.load(urllib.request.urlopen(request))
print(json.dumps(dict(ok=result['ok'], revision=result['session']['revision'], edits=edits,
                      shots=[dict(id=s['shot_id'], move=s['movement']['template_id'], lines=s['lines']) for c in doc['scenes'] for s in c['shots']])), flush=True)

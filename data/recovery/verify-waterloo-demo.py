"""Verify and retain the authored rehearsal separately from the pending AI proposal."""
import copy
import json
import urllib.request
import uuid
from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.sequence import build_program

BASE = 'http://127.0.0.1:8766'
SID = 'd7393e81-4725-4f52-a15c-195623d82655'


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=180))


def post(path, body):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(request, timeout=180))


def envelope():
    runtime = get('/api/director/runtime')
    return dict(schema_version=1, operation_id=str(uuid.uuid4()), runtime_epoch=runtime['runtime_epoch'],
                expires_monotonic_ns=str(int(runtime['now_monotonic_ns']) + int(runtime['command_ttl_ns'])))


detail = get('/api/director/sessions/' + SID)
doc = copy.deepcopy(detail['creative']['document'])
changes = [dict(sweep_rad=.67, focal_mm=30), dict(radius_m=3.5, distance_m=2.1, actor_distance_m=2.1, focal_mm=18),
           dict(distance_m=1.7, focal_mm=44), dict(sweep_rad=.76, focal_mm=30), dict(focal_mm=13)]
for shot, updates in zip(doc['scenes'][0]['shots'], changes):
    for parameter in shot['movement']['parameters']:
        if parameter['name'] in updates:
            parameter['value'] = updates[parameter['name']]
    shot['design']['lens_policy'] = 'authored'
    shot['action'] = shot['action'].replace('2.4-m', '2.1-m')
    for beat in shot['design']['beats']:
        beat['action'] = beat['action'].replace('2.4-m', '2.1-m')
detail['creative']['document'] = doc
detail['creative']['digest'] = digest(doc)
manifest = rehearsal_manifest(detail, digest(doc))
program = build_program(manifest)
rows = []
for segment in program['segments']:
    if segment['kind'] != 'shot':
        continue
    metrics = segment['shot_review']['travel']['metrics'] or {}
    rows.append(dict(shot=segment['shot_id'], source_s=segment['filming_s'], diagnostics=segment['diagnostics'],
                     issues=segment['shot_review']['issues'], cart=metrics.get('cart'), actor=metrics.get('actor'),
                     preview_hold_s=metrics.get('preview_hold_s')))
print('REVIEW', json.dumps(dict(blocked=program['blocked_shot_ids'], needs_revision=program['needs_revision_shot_ids'], shots=rows)), flush=True)
if program['blocked_shot_ids'] or program['needs_revision_shot_ids']:
    raise SystemExit(2)
brief = {**detail['session']['brief'], 'title': 'One Small Idea - verified Waterloo rehearsal'}
session = post('/api/director/sessions', {**envelope(), 'brief': brief})['session']
scope = dict(session_id=session['session_id'], expected_revision=session['revision'],
             cancellation_generation=session['cancellation_generation'], take_id=None, plan_id=None)
saved = post('/api/director/creative', {**envelope(), 'scope': scope, 'action': 'start_script',
                                      'payload': dict(document=doc, context=detail['creative']['context'])})
print('VERIFIED_BACKUP', json.dumps(dict(session_id=session['session_id'], digest=digest(doc),
                                       revision=saved['session']['revision'], source='authored')), flush=True)

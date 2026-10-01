"""Review explicit timing edits to the recovered draft, without API spending or hardware."""
import copy
import json
import urllib.request
import sys
import uuid

from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.sequence import build_program

URL = 'http://127.0.0.1:8766/api/director/sessions/d7393e81-4725-4f52-a15c-195623d82655'
detail = json.load(urllib.request.urlopen(URL))
document = copy.deepcopy(detail['creative']['document'])
speeds = {'sh01_arrival': .205, 'sh03_question_insert': .15}
for scene in document['scenes']:
    for shot in scene['shots']:
        if shot['shot_id'] in speeds:
            for parameter in shot['movement']['parameters']:
                if parameter['name'] == 'speed_m_s':
                    parameter['value'] = speeds[shot['shot_id']]
detail['creative']['document'] = document
detail['creative']['digest'] = digest(document)
program = build_program(rehearsal_manifest(detail, digest(document)))
print(json.dumps(dict(blocked=program['blocked_shot_ids'], needs_revision=program['needs_revision_shot_ids'],
                     shots=[dict(id=s['shot_id'], source_s=s['filming_s'], diagnostics=s['diagnostics'],
                                 issues=[i['code'] for i in s.get('shot_review', {}).get('issues', [])])
                            for s in program['segments'] if s['kind'] == 'shot'])), flush=True)
if '--save' in sys.argv:
    if program['blocked_shot_ids']:
        raise SystemExit('Blocked shots remain; not saving timing recovery.')
    document['questions'].append('Timing recovery: shots 1 and 3 use slower explicit cart pace to supply the full edit. Framing, attention and nominal set-clearance warnings remain; this is an unapproved rehearsal draft, not a qualified robot run.')
    runtime = json.load(urllib.request.urlopen('http://127.0.0.1:8766/api/director/runtime'))
    session = detail['session']
    body = dict(schema_version=1, operation_id=str(uuid.uuid4()), runtime_epoch=runtime['runtime_epoch'],
                expires_monotonic_ns=str(int(runtime['now_monotonic_ns']) + int(runtime['command_ttl_ns'])),
                scope=dict(session_id=session['session_id'], expected_revision=session['revision'],
                           cancellation_generation=session['cancellation_generation'], take_id=None, plan_id=None),
                action='save_document', payload=dict(document=document))
    request = urllib.request.Request('http://127.0.0.1:8766/api/director/creative', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    result = json.load(urllib.request.urlopen(request))
    print(json.dumps(dict(ok=result['ok'], revision=result.get('session', {}).get('revision'), digest=digest(document))), flush=True)

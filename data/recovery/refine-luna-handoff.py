"""Explicit human-reviewed revision of the paid Luna proposal; never calls AI or hardware."""
import copy
import json
import math
import sys
import urllib.request
import uuid

from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.channels import ramp
from takeone.previs.sequence import build_program

BASE = 'http://127.0.0.1:8766'
SESSION = '63763bf1-9ce0-4052-9ecb-14ef6c1a9ba7'
ORIGINAL = 'b180790075694f1bccb2d4e22cf0cf3535caa3e67e97b8a6e4a3a5154ec812d3'
detail = json.load(urllib.request.urlopen(BASE + '/api/director/sessions/' + SESSION))
if detail['creative']['digest'] != ORIGINAL:
    raise SystemExit('Production changed; refusing to overwrite a newer edit.')
candidate = copy.deepcopy(detail)
doc = candidate['creative']['document']
shot = next(s for c in doc['scenes'] for s in c['shots'] if s['shot_id'] == 'night-shot-06')
shot['lines'] = [dict(text='Alex: Can you follow this?  Maya: Watch me.', tone='Question, then a playful confident reply; follow the timed beats.', fact_ids=[])]
shot['selected_line'] = 0
cinema = shot['movement']['cinematography']
channels = cinema['channels']
channels['camera_height_m'] = ramp(1.25, 1.30, .34, .62)
channels['camera_target_m'] = ramp([.75, -1, 1.591], [0, 0, 1.591], .34, .62)
channels['light_height_m'] = ramp(1.42, 1.62, .70, .94)
channels['light_target_m'] = ramp([.75, -1, 1.591], [0, 0, 1.591], .70, .88)
for p in shot['movement']['parameters']:
    if p['name'] == 'height_start_m': p['value'] = 1.25
    if p['name'] == 'height_end_m': p['value'] = 1.30
cinema['camera']['keyframes'] = [dict(at=t, focal_mm=f, ease='smooth') for t,f in [(0,75),(.34,75),(.48,35),(.62,85),(1,85)]]
shot['motion_requirements'].update(arm_translation_m=.03, arm_rotation_rad=.18, light_rotation_rad=.18)
shot['framing'] = 'medium'
design = shot['design']
design.update(composition='single', visibility='intentional_partial', opening='Alex owns the opening close single; the listener may enter the edge.', ending='Maya owns the reply close single; Alex may leave the frame during the deliberate pan.', continuity='Retain the two fixed marks. Both speakers face the parked lens during their lines; no simultaneous two-shot promise.')
for contract, a,b,other in zip(design['screen_targets'], [0,.64], [.32,1], ['actor-b','actor-a']):
    contract.update(start_at=a,end_at=b,min_visible_s=1.4,center_uv=[.5,.5], tolerance_uv=[.15,.15],height_range=[.18,.45],allowed_foreground_actor_ids=[other])
shot['performers'] = []
shot['camera_intent'] = 'Human-reviewed Luna handoff: cart held, reachable 1.25–1.30 m phone rise, smooth Alex-head to Maya-head aim, 75→35→85 mm simulated framing, independently delayed fill. The larger platform rise remains in shot 4. Both turns share one selected dialogue alternative. Digital framing and scripted targets, not live speaker recognition.'
design['beats'][-1]['action'] = 'Maya holds the lens after her reply; Alex may leave the close single.'
candidate['creative']['digest'] = digest(doc)
program = build_program(rehearsal_manifest(candidate,digest(doc)))
segment = program['segments'][5]
review = segment['shot_review']
print(json.dumps(dict(digest=digest(doc), blocked=program['blocked_shot_ids'], revision=program['needs_revision_shot_ids'], diagnostics=segment['diagnostics'], issues=review['issues'], metrics=review['travel']['metrics'], height=review['camera_height_range_m'], screen=[dict(target=c['target_id'],first=c['samples'][0],last=c['samples'][-1]) for c in review['screen']['checks']]),indent=2))
if '--save' in sys.argv:
    if program['blocked_shot_ids'] or program['needs_revision_shot_ids'] or segment['diagnostics']:
        raise SystemExit('Review findings remain; not saved.')
    r=json.load(urllib.request.urlopen(BASE+'/api/director/runtime'))
    session=detail['session']
    body=dict(schema_version=1,operation_id=str(uuid.uuid4()),runtime_epoch=r['runtime_epoch'],expires_monotonic_ns=str(int(r['now_monotonic_ns'])+int(r['command_ttl_ns'])), scope=dict(session_id=SESSION,expected_revision=session['revision'],cancellation_generation=session['cancellation_generation'],take_id=None,plan_id=None), action='save_document',payload=dict(document=doc))
    req=urllib.request.Request(BASE+'/api/director/creative',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    saved=json.load(urllib.request.urlopen(req))
    print('SAVED',saved['ok'],digest(doc))

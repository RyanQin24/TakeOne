"""Author and review a two-person nighttime rehearsal. No device or model calls."""
import copy
import json
import math
import sys
import urllib.request
import uuid

from takeone.director.cinematic import wire_settings
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, validate_plan
from takeone.director.skills import sample_project
from takeone.director.studio import rehearsal_manifest
from takeone.previs.sequence import build_program
from takeone.previs.templates import defaults_for

BASE = 'http://127.0.0.1:8766'
sample = sample_project('cinematic')
doc = copy.deepcopy(sample['document'])
seed = copy.deepcopy(doc['scenes'][0]['shots'][0])
context = dict(skill_id='cinematic', audience='Tonight’s Waterloo demo audience', tone='Nighttime cinematic energy, playful collaboration', facts=[])
brief = dict(title='After Dark — Waterloo / 10-shot two-person demo', objective='Two collaborators make a one-minute film outside at Waterloo at night. Ten unique shots; both people visible; a front-facing walking conversation; low-angle rising phone-arm tilt; custom simultaneous cart and arm choreography. Requested cart cruise at least 0.33 m/s, within existing policy. Nighttime background with architecture and practical lights, assumed not measured. No claim of hardware or live-sync qualification.', duration_ms=60000, aspect_ratio='16:9')
doc.update(title='After Dark — a moving conversation', audience=context['audience'], tone=context['tone'],
           logline='Two teammates turn an empty evening into a film, discovering the scene while walking through it.',
           questions=['Confirm a level, lit outdoor route with no pedestrians or obstacles before physical filming.',
                      'All architecture, lights and placements are assumed visualization, not measured Waterloo geometry.',
                      'Camera controls and sync need a fresh live-phone check; simulation is not a qualified robot run.'])
doc['actors'] = [dict(actor_id='actor-a', name='Alex', appearance=dict(cloth='#245a83', pants='#253040', skin='#cfa783', hair='#30271f', shoe='#eeeeee')),
                 dict(actor_id='actor-b', name='Maya', appearance=dict(cloth='#b46737', pants='#292d35', skin='#cfa783', hair='#30271f', shoe='#eeeeee'))]
doc['visual_style'].update(palette='Deep blue night, warm practical lights, blue and amber wardrobe.',
                          wardrobe='Alex in blue, Maya in amber; maintain through all edits.',
                          lighting='Night exterior with motivated warm practical lamps and soft face fill. Preview is illustrative; check actual exposure.',
                          sound='Close dialogue, footsteps and evening ambience; no claimed recorded sound.',
                          visual_rules='Two people, readable faces, motivated low-to-high reveal, alternating lateral and frontal perspectives.',
                          continuity_locks=['Same cast and wardrobe; independent takes reset outside the 60-second edit.'])
doc['marks'] = []
doc['scenes'] = []
rows = [
    ('hero_orbit','The night opens','We have one minute. Let’s make it move.', 'Look across the lit courtyard, then turn together toward the lens.', dict(radius_m=4.5,sweep_rad=.64,height_start_m=1.40,height_end_m=1.55,rise_start=.05,rise_end=.95,focal_mm=24)),
    ('track_lead','Walk toward the audience','Start with us. Keep up.', 'Walk side by side toward the leading camera, speaking to the lens.', dict(radius_m=4.5,distance_m=2.8,actor_distance_m=2.8,actor_heading_rad=0,focal_mm=24)),
    ('side_track','The passing lights','Same place. A different point of view.', 'Walk together past the warm lights, briefly exchanging a glance.', dict(radius_m=4.8,distance_m=2.8,actor_distance_m=2.8,actor_heading_rad=0,focal_mm=24)),
    ('track_lead','Low angle, lift the idea','Now give the idea some height.', 'Walk toward the low lens together as the phone arm rises, keeping both faces in view.', dict(radius_m=4.5,distance_m=2.4,actor_distance_m=2.4,actor_heading_rad=0,height_start_m=1.25,height_end_m=1.40,rise_start=.05,rise_end=.95,focal_mm=50)),
    ('arc_left','Maya takes the lead','What if the camera listened?', 'Maya gestures toward Alex; Alex reacts with a small nod.', dict(radius_m=4.5,sweep_rad=.64,height_start_m=1.4,height_end_m=1.55,focal_mm=24)),
    ('push_in','A shared discovery','Then it would know when to get closer.', 'Both lean into the thought, not into the route. Hold eye contact with the lens.', dict(radius_m=6,distance_m=2.8,height_start_m=1.45,height_end_m=1.55,focal_mm=20)),
    ('arc_right','Trade the perspective','And when to change its mind.', 'Alex opens one hand; Maya answers with a confident look.', dict(radius_m=4.5,sweep_rad=.64,height_start_m=1.5,height_end_m=1.35,focal_mm=24)),
    ('truck_right','Custom crossing light','Move the camera. Shape the light.', 'Hold your shared position as the cart crosses and the phone rises while the light lowers.', dict(radius_m=4.5,distance_m=2.4,height_start_m=1.40,height_end_m=1.55,rise_start=.05,rise_end=.95,light_height_start_m=1.60,light_height_end_m=1.45,focal_mm=24)),
    ('track_follow','Walk into the night','The story keeps going.', 'Walk together toward the lit architecture. Let the camera follow your silhouettes.', dict(radius_m=4.5,distance_m=2.8,actor_distance_m=2.8,actor_heading_rad=0,focal_mm=24)),
    ('pull_out','Leave room for the next idea','Two people. One minute. Your turn.', 'Face the lens together and hold the invitation as the courtyard is revealed.', dict(radius_m=3.8,distance_m=2.8,height_start_m=1.45,height_end_m=1.55,focal_mm=20)),
]
for i, (template, title, line, action, overrides) in enumerate(rows):
    si = i // 2
    scene_id = f'night-{si+1}'
    mark_id = f'mark-{i+1}'
    if i % 2 == 0:
        scene = copy.deepcopy(sample['document']['scenes'][0])
        scene.update(scene_id=scene_id, space_id=scene_id, title=['Courtyard entrance','The lamp-lined walk','The conversation','A new angle','Into the night'][si],
                     location='Assumed Waterloo outdoor courtyard at night', atmosphere='exterior_night',
                     location_notes='Proposed open level courtyard. Architecture and practical lamps are visualization only. Allow separate resets between takes; verify real route clearance.',
                     cast=[dict(actor_id='actor-b',offset_m=[0,1.0,0],facing_rad=0,motion='with_lead')], shots=[],
                     objects=[dict(object_id='backdrop',asset_id='facade',label='Warm campus facade — assumed',position_m=[-10,0,2.5],size_m=[18,.3,5],yaw_rad=math.pi/2,availability='proposed',production_role='Night background depth'),
                              dict(object_id='lamp-left',asset_id='practical_light',label='Warm pool of light',position_m=[-6,-4,1.1],size_m=[.4,.4,2.2],yaw_rad=0,availability='proposed',production_role='Motivated evening practical'),
                              dict(object_id='lamp-right',asset_id='practical_light',label='Warm rim practical',position_m=[-6,5,1.1],size_m=[.4,.4,2.2],yaw_rad=0,availability='proposed',production_role='Separate the pair from the background'),
                              dict(object_id='tree-left',asset_id='tree',label='Courtyard tree',position_m=[-8,-6,2],size_m=[2,2,4],yaw_rad=0,availability='proposed',production_role='Night silhouette'),
                              dict(object_id='tree-right',asset_id='tree',label='Courtyard tree',position_m=[-8,6,2],size_m=[2,2,4],yaw_rad=0,availability='proposed',production_role='Background rhythm')])
        doc['scenes'].append(scene)
    doc['marks'].append(dict(mark_id=mark_id,scene_id=scene_id,description='Assumed origin for this independent take; reset off camera.',position_m=[0,0],facing_rad=0))
    walk = template in ('track_lead','side_track','track_follow')
    params = dict(speed_m_s=.40,**overrides)
    if params.get('distance_m') == 2.8:
        params['distance_m'] = 2.4
        if walk:
            params['actor_distance_m'] = 2.4
    if params.get('sweep_rad') == .64:
        params['sweep_rad'] = .5
    settings = defaults_for(template) | params | dict(subject_motion='walk' if walk else 'hold')
    shot = copy.deepcopy(seed)
    shot.update(shot_id=f'night-shot-{i+1:02}',start_ms=i*6000,end_ms=(i+1)*6000,actor_id='actor-a',mark_id=mark_id,
                action=action,framing='medium' if i==3 else 'full',primitive='template', selected_line=0, audio_intent='Dialogue, footsteps and exterior night ambience.',
                camera_intent=title+'. Encoded route at 0.40 m/s requested cruise; inspect achieved speed and framing.',
                light_intent='Motivated practical lamps and soft face fill; confirm actual exposure.',edit_intent='Cut after the line on the acting beat; resets excluded.',
                lines=[dict(text=line,tone='Conversational energy',fact_ids=[])],
                movement=dict(template_id=template,subject_motion=settings['subject_motion'],parameters=[dict(name=k,value=v) for k,v in params.items()],cinematography=wire_settings(settings)),
                transition='cut',camera_target=dict(kind='actor',target_id='actor-a'),
                capture=dict(take_id=f'night-take-{i+1}',in_s=0), performers=[],
                tracking=dict(cart='planned',phone='planned',on_loss='stop_and_hold',reason='Scripted two-person rehearsal; no claim of live person tracking.'))
    shot['design'].update(purpose=title,attention='Both faces and their shared action.',opening=action,ending='Let the line land before cutting.',
                          composition='two_shot',featured_actor_ids=['actor-a','actor-b'],angle='low' if i==3 else 'eye_level',
                          visibility='throughout',lens_policy='authored',focus=dict(mode='deep',target='Both actors'),
                          continuity='Same two collaborators; independent off-camera reset between takes.',practical_setup='Keep the full route clear of actors, lamps and pedestrians.',
                          beats=[dict(start_s=0,end_s=6,actor_id='actor-a',action=action,motivation=title,emotion='Curious and confident',eyeline='Lens for front-facing dialogue; travel direction while following.',delivery='Natural conversational timing.')])
    # Minimum creative movement targets, not exact full-route distance promises.
    shot['motion_requirements'].update(priority='required',actor_travel_m=1.5 if walk else 0,cart_travel_m=1.5,camera_travel_m=1.0,
                                       arm_translation_m=0,arm_rotation_rad=0,light_translation_m=0,light_rotation_rad=0,
                                       simultaneous_s=0,direction='any',signed_progress_m=0,orbit_rad=0)
    scene['shots'].append(shot)

validate_plan(doc, ProductionBrief.parse(brief), context)
detail = dict(session=dict(session_id='night-candidate',revision=0,brief=brief),creative=dict(document=doc,digest=digest(doc),context=context))
program = build_program(rehearsal_manifest(detail,digest(doc)))
print(json.dumps(dict(blocked=program['blocked_shot_ids'], needs_revision=program['needs_revision_shot_ids'],
                     shots=[dict(id=s['shot_id'],source_s=s.get('filming_s'),diagnostics=s['diagnostics'],issues=s.get('shot_review',{}).get('issues',[])) for s in program['segments']])),flush=True)

def post(path, body):
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(request))

def envelope():
    r=json.load(urllib.request.urlopen(BASE+'/api/director/runtime'))
    return dict(schema_version=1,operation_id=str(uuid.uuid4()),runtime_epoch=r['runtime_epoch'],expires_monotonic_ns=str(int(r['now_monotonic_ns'])+int(r['command_ttl_ns'])))

if '--save' in sys.argv:
    session=post('/api/director/sessions',{**envelope(),'brief':brief})['session']
    saved=post('/api/director/creative',{**envelope(),'scope':dict(session_id=session['session_id'],expected_revision=session['revision'],cancellation_generation=session['cancellation_generation'],take_id=None,plan_id=None),'action':'start_script','payload':dict(document=doc,context=context)})
    print(json.dumps(dict(saved=saved['ok'],session_id=session['session_id'],digest=digest(doc))),flush=True)

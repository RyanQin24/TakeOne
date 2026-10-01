"""One-off authored demo recovery. Local Director data only, no hardware or paid calls."""
import copy
import json
import urllib.request
import uuid

from takeone.director.skills import sample_project
from takeone.director.cinematic import wire_settings
from takeone.director.creative import validate_plan
from takeone.director.contracts import ProductionBrief
from takeone.previs.templates import defaults_for

BASE = 'http://127.0.0.1:8766'
SID = 'd7393e81-4725-4f52-a15c-195623d82655'


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=180))


def edit(action, payload):
    detail = get('/api/director/sessions/' + SID)
    runtime = get('/api/director/runtime')
    session = detail['session']
    body = dict(schema_version=1, operation_id=str(uuid.uuid4()), runtime_epoch=runtime['runtime_epoch'],
                expires_monotonic_ns=str(int(runtime['now_monotonic_ns']) + int(runtime['command_ttl_ns'])),
                scope=dict(session_id=SID, expected_revision=session['revision'],
                           cancellation_generation=session['cancellation_generation'], take_id=None, plan_id=None),
                action=action, payload=payload)
    request = urllib.request.Request(BASE + '/api/director/creative', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(request))


def main():
    detail = get('/api/director/sessions/' + SID)
    context = detail['creative_context']
    doc = copy.deepcopy(sample_project('cinematic')['document'])
    original = copy.deepcopy(doc['scenes'][0]['shots'][0])
    doc.update(title='One Small Idea - Waterloo demo (authored)',
               logline='A presenter turns a small gesture into a moving scene: invite, walk, discover, reveal, and invite the audience to try.',
               questions=['Confirm a clear, level rehearsal area before physical filming.',
                          'Which teammate will perform, and which real campus location is available?'])
    doc['actors'][0]['name'] = 'Presenter'
    doc['marks'] = [dict(mark_id='A', scene_id='scene-1', position_m=[0, 0], facing_rad=0,
                         description='Assumed demo origin. Reset here off-camera between independent takes; not a measured room position.')]
    doc['visual_style'].update(visual_rules='One presenter, clear silhouettes, motivated movement, and direct address.',
                               palette='Real location, neutral wardrobe.', wardrobe='Same clothing throughout; no props required.',
                               sound='Clear dialogue, footsteps and room tone.',
                               continuity_locks=['Independent takes: reset to A between setups.'])
    scene = doc['scenes'][0]
    scene.update(title='One small idea becomes a scene', location='University of Waterloo - level filming area to be confirmed',
                 location_notes='Proposed open floor, not measured venue geometry. Keep actor/cart routes clear; reset between takes.',
                 objects=[], cast=[], shots=[])
    rows = [
        (10, 'hero_orbit', 'medium', 'Look down at an empty palm, then lift your eyes to the audience as the camera moves around you.',
         'We are at Waterloo. Our challenge: turn one small idea into a scene.',
         dict(radius_m=2.5, sweep_rad=0.9, speed_m_s=0.18, height_start_m=1.25, height_end_m=1.5, focal_mm=30), 'Make the ordinary worth watching.'),
        (12, 'side_track', 'full', 'Walk steadily along the marked 2.4-m line. Glance to the moving lens, then look ahead.',
         'First, give it somewhere to go.',
         dict(radius_m=2.5, distance_m=2.4, actor_distance_m=2.4, actor_heading_rad=0, speed_m_s=0.18, focal_mm=24), 'The idea becomes a physical journey.'),
        (12, 'push_in', 'medium', 'After the off-camera reset, face the lens. Raise one finger as a new thought arrives; pause, then smile.',
         'Then get closer. Let the audience notice the moment something changes.',
         dict(radius_m=3.0, distance_m=1.8, speed_m_s=0.14, focal_mm=24), 'A small realization becomes the reveal.'),
        (12, 'arc_right', 'medium', 'Open your hand toward the cleared space, turn your head to follow the camera, then return your eyes to the lens.',
         'Same person. Same space. A different point of view.',
         dict(radius_m=2.5, sweep_rad=1.0, speed_m_s=0.18, focal_mm=30), 'Reveal a changing perspective without extra props.'),
        (14, 'pull_out', 'full', 'Take a small bow, open both hands toward the audience, and finish with one confident nod.',
         'That is our demo: an idea, a performance, and a camera with a purpose. Your turn.',
         dict(radius_m=2.0, distance_m=2.4, speed_m_s=0.16, focal_mm=24), 'Reveal room around the presenter and land the invitation.'),
    ]
    clock = 0
    for index, (seconds, template, framing, action, line, params, purpose) in enumerate(rows, 1):
        settings = defaults_for(template)
        settings.update(params)
        settings['subject_motion'] = 'walk' if template == 'side_track' else 'hold'
        shot = copy.deepcopy(original)
        shot.update(shot_id=f'shot-{index}', start_ms=clock * 1000, end_ms=(clock + seconds) * 1000,
                    mark_id='A', action=action, framing=framing, primitive='template',
                    camera_intent=purpose + ' Use the encoded ' + template + ' route; not live tracking.',
                    light_intent='Keep a consistent soft side key; verify real positions on set.',
                    edit_intent='Cut on the acting beat. Exclude setup and off-camera resets.',
                    lines=[dict(text=line, tone='Direct, warm, confident; let the action breathe.', fact_ids=[])],
                    movement=dict(template_id=template, subject_motion=settings['subject_motion'],
                                  parameters=[dict(name=k, value=v) for k, v in params.items()],
                                  cinematography=wire_settings(settings)), transition='reposition',
                    tracking=dict(cart='planned', phone='planned', on_loss='stop_and_hold', reason='Authored simulated route.'))
        shot['motion_requirements'].update(priority='preferred', actor_travel_m=1.5 if template == 'side_track' else 0,
                                           cart_travel_m=0.6, camera_travel_m=0.5, arm_translation_m=0, simultaneous_s=0)
        shot['design'].update(purpose=purpose, attention=action, opening=action.split('.')[0] + '.',
                              ending='Complete the action and hold the final gaze until the cut.', lens_policy='fit_subject',
                              continuity='Reset to A between independent takes; keep wardrobe and light consistent.',
                              practical_setup='Clear level floor; preview the route and verify phone framing.',
                              beats=[dict(start_s=0, end_s=seconds, actor_id='actor-a', action=action,
                                          motivation=purpose, emotion='Curiosity becoming confidence',
                                          eyeline='Lens during speech; direction of travel while walking.',
                                          delivery='Speak clearly with a silent beat before and after.')])
        scene['shots'].append(shot)
        clock += seconds
    validate_plan(doc, ProductionBrief.parse(detail['session']['brief']), context)
    action = 'save_document' if detail['creative'] else 'start_script'
    payload = dict(document=doc) if detail['creative'] else dict(document=doc, context=context)
    result = edit(action, payload)
    print(json.dumps(dict(ok=result['ok'], revision=result['session']['revision'], shots=len(rows), duration_s=clock)))


if __name__ == '__main__':
    main()

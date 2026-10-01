"""Refine only the authored asset exercise; no paid model or device access."""
from pathlib import Path
import sys, json, copy
ROOT=Path('C:/TakeOne')
sys.path.insert(0,str(ROOT/'scripts'))
from scene_assets_demo import project
from cinematic_upgrade_demo import request,envelope
from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
sid='4e348393-3be2-4e74-9f0c-8aaa57d7aab8'
detail=request('/api/director/sessions/'+sid)
assert detail['creative']['digest']=='4251a52fbf4631c176854da1106434b7233479d2522c1d03637b7ad449f71830','Preserve concurrent edits'
sample=project(); draft=copy.deepcopy(detail)
draft['creative'].update(document=sample['document'],digest=digest(sample['document']))
manifest=rehearsal_manifest(draft,draft['creative']['digest'])
program=request('/api/previs/sequence',manifest)
print('Revised motion:',[(s['segment_id'],s['assessment']) for s in program['segments']])
print('Issues:',[(s['segment_id'],s.get('shot_review',{}).get('issues')) for s in program['segments'] if s['assessment']!='reviewable'])
assert not program['blocked_shot_ids'] and not program['needs_revision_shot_ids'],'Inspect before saving'
s=detail['session']
scope=dict(session_id=sid,expected_revision=s['revision'],cancellation_generation=s['cancellation_generation'],take_id=s['take_id'],plan_id=None)
result=request('/api/director/creative',envelope()|dict(scope=scope,action='save_document',payload=dict(document=sample['document'])))
assert result['ok'],result
detail=request('/api/director/sessions/'+sid); ref=sid+'/'+detail['creative']['digest']
program=request('/api/previs/sequence',request('/api/director/studio/'+ref))
out=ROOT/'data/asset-scenes-live-evidence'
(out/'demonstration.json').write_text(json.dumps(dict(reference=ref,document=detail['creative']['document'],program=program),indent=2),encoding='utf-8')
print('http://127.0.0.1:8766/?script='+ref)

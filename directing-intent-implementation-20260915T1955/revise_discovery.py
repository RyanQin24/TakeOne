import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from cinematic_upgrade_demo import envelope,request
root=Path(r"C:\TakeOne")
folder=root/'data/directing-intent-candidates-20260915/discovery'
old=json.loads((folder/'installed.json').read_text())
sid=old['reference'].split('/')[0]
detail=request('/api/director/sessions/'+sid)
session=detail['session'];document=detail['creative']['document']
shot=document['scenes'][1]['shots'][0]
for parameter in shot['movement']['parameters']:
    if parameter['name']=='height_start_m': parameter['value']=1.52
    if parameter['name']=='height_end_m': parameter['value']=1.57
scope=dict(session_id=sid,expected_revision=session['revision'],cancellation_generation=session['cancellation_generation'],take_id=session['take_id'],plan_id=None)
request('/api/director/creative',envelope()|dict(scope=scope,action='save_document',payload=dict(document=document)))
detail=request('/api/director/sessions/'+sid)
ref=sid+'/'+detail['creative']['digest'];manifest=request('/api/director/studio/'+ref)
program=request('/api/previs/sequence',manifest)
(folder/'revision-2.json').write_text(json.dumps(dict(reference=ref,document=document,program=program),indent=2))
print(ref);print(program['needs_revision_shot_ids'])

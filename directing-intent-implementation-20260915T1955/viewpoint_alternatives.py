import copy,json,sys
from pathlib import Path
root=Path(r"C:\TakeOne");sys.path.insert(0,str(root/'scripts'))
from first_turn_demo import project
from takeone.previs.templates import compile_template
from takeone.previs.performers import build_samples
from takeone.previs.screen_review import review_screen
sample=project();scene=sample['document']['scenes'][0];shot=scene['shots'][-1];mark=sample['document']['marks'][-1]
shot['design']['screen_targets'][0]['allowed_foreground_actor_ids']=[]
installed=json.loads((root/'data/directing-intent-candidates-20260915/first-turn/installed.json').read_text())
base=installed['program']['segments'][-1]['settings'];rows=[]
for bearing in [0,.15,-.15,.3,-.3]:
    settings=copy.deepcopy(base);settings['bearing_rad']=bearing
    preview=compile_template(settings)['preview'];build_samples(shot,settings,scene,mark,preview)
    result=review_screen(shot,settings,scene,mark,preview)
    rows.append(dict(bearing_rad=bearing,focal_mm=settings['focal_mm'],summary=preview['summary'],screen=result))
    print(bearing,settings['focal_mm'],preview['summary']['max_aim_error_deg'],[i['code'] for i in result['issues']],flush=True)
(root/'data/directing-intent-implementation-20260915T1955/viewpoint-alternatives.json').write_text(json.dumps(rows,indent=2))

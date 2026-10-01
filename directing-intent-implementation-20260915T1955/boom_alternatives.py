import copy,json
from pathlib import Path
from takeone.previs.templates import compile_template
from takeone.previs.shot_review import review
root=Path(r"C:\TakeOne")
program=json.loads((root/"data/directing-intent-candidates-20260915/discovery/installed.json").read_text())['program']
source=json.loads((root/"data/directing-intent-candidates-20260915/discovery/authored.json").read_text())['document']
segment=program['segments'][1]; scene=source['scenes'][1]; shot=scene['shots'][0]; mark=source['marks'][1]
results=[]
for low,high in [(1.54,1.56),(1.52,1.57),(1.56,1.59)]:
    settings=copy.deepcopy(segment['settings']);settings['height_start_m']=low;settings['height_end_m']=high
    preview=compile_template(settings)['preview']
    result=review(shot,settings,scene,mark,preview)
    results.append(dict(request=[low,high],motion=result['motion'],issues=result['issues'],summary=preview['summary']))
    print(low,high,preview['summary']['max_aim_error_deg'],[i['code'] for i in result['issues']],flush=True)
(root/'data/directing-intent-implementation-20260915T1955/boom-alternatives.json').write_text(json.dumps(results,indent=2))

import copy,json,math
from pathlib import Path
from takeone.previs.templates import compile_template,defaults_for
from takeone.previs.channels import ramp
base=defaults_for('boom_up')|dict(duration_s=10,radius_m=2.5,height_start_m=1.51,height_end_m=1.58,focal_mm=35)
p=compile_template(base)['preview'];f=[x for x in p['frames'] if x['time_s']>=p['orbit_start_s']-1e-8]
print('HEIGHT_REFERENCE',p['summary'],flush=True)
for step in (2,6,12):
    indices=sorted(set(round(i*(len(f)-1)/step) for i in range(step+1)))
    keys=[dict(at=(f[i]['time_s']-p['orbit_start_s'])/p['orbit_duration_s'],value=f[i]['camera']['pos'],ease='linear') for i in indices]
    keys[0]['at']=0;keys[-1]['at']=1
    s=copy.deepcopy(base);s['channels']={'camera_position_m':keys}
    v=compile_template(s)['preview'];ff=[x for x in v['frames'] if x['time_s']>=v['orbit_start_s']-1e-8]
    print('KEYS',step,'error',v['summary'].get('max_camera_position_error_m'),'aim',v['summary']['max_aim_error_deg'],'qfirst',ff[0]['q'][3:8],'qlast',ff[-1]['q'][3:8],flush=True)
    Path(__file__).with_name('optical-feasible-'+str(step)+'.json').write_text(json.dumps({'settings':s,'preview':v}),encoding='utf-8')

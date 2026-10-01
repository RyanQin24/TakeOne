import copy, json, time
from pathlib import Path
from takeone.previs.templates import compile_template, defaults_for
from takeone.previs.channels import ramp
from scripts.moving_camera_showcase import joint_settings
root=Path(__file__).parent
results=[]
for shape in ('smooth','linear','preset'):
    for start,end in ((1.48,1.61),(1.51,1.58)):
        s=joint_settings();s['camera_target']={'kind':'actor','position_m':[0,0,-.301]}
        s.update(height_start_m=start,height_end_m=end)
        s['scene']={'actor_facing':'fixed','actor_heading_rad':0,'filming_side':'direction'}
        s['channels']['camera_height_m']=ramp(start,end,.15,.8)
        if shape=='linear':
            for key in s['channels']['actor_position_m']:key['ease']='linear'
        elif shape=='preset':s['channels'].pop('actor_position_m')
        t=time.perf_counter();pv=compile_template(s)['preview']
        row={'name':shape+str(start),'compile_s':time.perf_counter()-t,'settings':s,'summary':pv['summary']}
        results.append(row);print(row['name'],row['compile_s'],row['summary']['max_aim_error_deg'],flush=True)
base=defaults_for('static')|dict(duration_s=8,radius_m=2.5,height_start_m=1.5,height_end_m=1.5,focal_mm=35)
pv=compile_template(base)['preview'];p=next(f['camera']['pos'] for f in pv['frames'] if f['time_s']>=pv['orbit_start_s'])
for axis,delta in ((0,.07),(1,.07),(2,.08)):
    s=copy.deepcopy(base);end=list(p);end[axis]+=delta
    s['channels']={'camera_position_m':ramp(p,end,.15,.8)}
    pv=compile_template(s)['preview'];results.append({'name':'arm-axis-'+str(axis),'settings':s,'summary':pv['summary']})
    print('arm',axis,pv['summary'].get('max_camera_position_error_m'),pv['summary']['max_aim_error_deg'],flush=True)
(root/'exploration.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

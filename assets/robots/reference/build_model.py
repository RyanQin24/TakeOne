"""Adapt pinned RobotStudio SO101 geometry to two five-joint filming arms.

Mounts, payload inertias and cart dimensions are declared simulation assumptions.
The sixth motor/gripper assembly is removed, not merely locked.
"""
from pathlib import Path
import copy
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
JOINTS = ['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll']
ASSUMPTIONS = {
    'cart_mass_kg': 4.0, 'cart_half_size_m': [0.23,0.19,0.065],
    'cart_deck_height_m': 0.22, 'wheelbase_m': 0.32,
    'wheel_track_m': 0.34, 'wheel_radius_m': 0.055,
    'camera_mount_xyz_m': [0.0,-0.14,0.22],
    'light_mount_xyz_m': [0.0,0.14,0.22],
    'phone_holder_mass_kg': 0.30, 'light_holder_mass_kg': 0.12,
    'phone_half_size_m': [0.04,0.08,0.007],
    'optical_offset_from_wrist_roll_m': [0.025,0.05,-0.06],
    'optical_rotation_quaternion_wxyz': [0,1,0,0],
    'servo_kp_Nm_per_rad': 80.0, 'servo_kv_Nms_per_rad': 2.5,
    'assumed_continuous_torque_cap_Nm': 1.0,
    'not_measured': True,
}

def build():
    source=ET.parse(ROOT/'upstream/so101_new_calib.xml').getroot()
    out=ET.Element('mujoco', model='TAKE_ONE_5DOF_dual_arm_illustrative_cart')
    ET.SubElement(out,'compiler',angle='radian',meshdir='upstream/assets',autolimits='true')
    ET.SubElement(out,'option',timestep='0.002',gravity='0 0 -9.81',integrator='implicitfast')
    ET.SubElement(out,'visual').append(ET.Element('global',offwidth='1280',offheight='720'))
    for default in source.findall('default'):
        out.append(copy.deepcopy(default))
    # Upstream's actuator forces are not ratings for the user's voltage/hardware.
    motor=out.find(".//default[@class='sts3215']/position")
    motor.set('kp','80');motor.set('kv','2.5');motor.set('forcerange','-1 1')
    out.append(copy.deepcopy(source.find('asset')))
    world=ET.SubElement(out,'worldbody')
    ET.SubElement(world,'light',pos='0 -2 3',dir='0 0 -1',ambient='.35 .35 .35',diffuse='.8 .8 .8')
    ET.SubElement(world,'light',pos='2 2 3',dir='0 0 -1',diffuse='.6 .6 .6')
    ET.SubElement(world,'geom',name='floor',type='plane',size='5 5 .1',rgba='.7 .74 .78 1')
    ET.SubElement(world,'geom',name='actor_head',type='sphere',pos='1.8 0 1.05',size='.09',rgba='.65 .35 .25 1')
    ET.SubElement(world,'geom',name='actor_body',type='capsule',fromto='1.8 0 .45 1.8 0 .88',size='.13',rgba='.23 .42 .43 1')
    cart=ET.SubElement(world,'body',name='cart')
    for name,typ,axis in [('base_x','slide','1 0 0'),('base_y','slide','0 1 0'),('base_yaw','hinge','0 0 1')]:
        ET.SubElement(cart,'joint',name=name,type=typ,axis=axis,damping='0',limited='false')
    ET.SubElement(cart,'geom',name='cart_box',type='box',pos='0 0 .135',size='.23 .19 .065',mass='4',rgba='.22 .27 .33 1')
    for x in [-.16,.16]:
        for y in [-.17,.17]:
            ET.SubElement(cart,'geom',type='cylinder',pos=f'{x} {y} .055',size='.055 .015',quat='.70710678 .70710678 0 0',mass='.08',rgba='.04 .04 .04 1',contype='0',conaffinity='0')
    actuators=ET.SubElement(out,'actuator')
    for prefix,mount,mass,box in [('cam',ASSUMPTIONS['camera_mount_xyz_m'],.30,[.04,.08,.007]),('light',ASSUMPTIONS['light_mount_xyz_m'],.12,[.05,.04,.008])]:
        arm=copy.deepcopy(source.find('worldbody/body'))
        carrier=arm.find(".//body[@name='gripper']")
        # Preserve q5; replace its entire downstream assembly and aggregate inertia.
        q5=copy.deepcopy(carrier.find('joint'));carrier[:]=[q5]
        carrier.set('name','tool_carrier')
        ET.SubElement(carrier,'geom',name='payload',type='box',pos='0 0 -.045',size=' '.join(map(str,box)),mass=str(mass),rgba=('.2 .4 .8 1' if prefix=='cam' else '.9 .85 .4 1'))
        ET.SubElement(carrier,'site',name='optical',pos='.025 .05 -.06',quat='0 1 0 0',size='.004',rgba='1 0 0 1')
        ET.SubElement(carrier,'camera',name='view',pos='.025 .05 -.06',quat='1 0 0 0',fovy='49.6')
        for element in arm.iter():
            if 'name' in element.attrib:element.set('name',prefix+'_'+element.get('name'))
        arm.set('pos',' '.join(map(str,mount)))
        cart.append(arm)
        for joint in JOINTS:
            ET.SubElement(actuators,'position',name=f'{prefix}_{joint}',joint=f'{prefix}_{joint}',**{'class':'sts3215','forcerange':'-1 1'})
    ET.SubElement(world,'geom',name='test_obstacle',type='sphere',pos='3 3 .5',size='.08',rgba='.9 .2 .2 1')
    ET.indent(out)
    ET.ElementTree(out).write(ROOT/'rig_5dof.xml',encoding='unicode')
    (ROOT/'assumptions.json').write_text(json.dumps(ASSUMPTIONS,indent=2))
    return ROOT/'rig_5dof.xml'

if __name__=='__main__':
    import mujoco
    model=mujoco.MjModel.from_xml_path(str(build()));data=mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    print('nq,nv,nu',model.nq,model.nv,model.nu)
    for name in ['cam_optical','light_optical']:
        s=model.site(name).id
        print(name,data.site_xpos[s],data.site_xmat[s].reshape(3,3)[:,2])
    print('joints', [model.joint(i).name for i in range(model.njnt)])

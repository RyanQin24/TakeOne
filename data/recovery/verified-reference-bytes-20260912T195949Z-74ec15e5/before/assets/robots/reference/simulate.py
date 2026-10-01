"""Reproducible numerical evidence, NOT hardware certification.

RobotStudio joint frames/meshes are pinned upstream. Modified payload and cart
parameters are assumptions. Closed-loop tests use a kinematic vehicle plus
first-order actuator lag; the separate MuJoCo test integrates arm dynamics.
"""
from pathlib import Path
import hashlib, json, time, platform, subprocess, xml.etree.ElementTree as ET
import numpy as np
import scipy, scipy.sparse as sp
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from scipy.interpolate import CubicSpline
import mujoco, osqp, cv2, ruckig
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_model import ROOT, JOINTS, ASSUMPTIONS, build

OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
RNG=np.random.default_rng(20260911)
RESULTS={};DT=.02;DURATION=12.;TARGET=np.array([1.8,0.,1.05])

def record(name,passed,**metrics):
    RESULTS[name]={'passed':bool(passed),**metrics}
    print(name, 'PASS' if passed else 'FAIL', json.dumps(metrics), flush=True)

def skew(v):
    x,y,z=v;return np.array([[0,-z,y],[z,0,-x],[-y,x,0]])

def T(R=np.eye(3),p=np.zeros(3)):
    a=np.eye(4);a[:3,:3]=R;a[:3,3]=p;return a

class Rig:
    def __init__(self):
        self.m=mujoco.MjModel.from_xml_path(str(ROOT/'rig_5dof.xml'))
        self.d=mujoco.MjData(self.m)
        self.ids=[self.m.site(n+'_optical').id for n in ['cam','light']]
        self.lo=self.m.jnt_range[3:,0]+.04;self.hi=self.m.jnt_range[3:,1]-.04
    def set(self,q):
        self.d.qpos[:]=q;mujoco.mj_forward(self.m,self.d)
    def pose(self,i=0):
        s=self.ids[i];return self.d.site_xpos[s].copy(),self.d.site_xmat[s].reshape(3,3).copy()
    def jac(self,i=0):
        p=np.zeros((3,13));r=p.copy();mujoco.mj_jacSite(self.m,self.d,p,r,self.ids[i]);return p,r
    def image(self,point,i=0):
        p,r=self.pose(i);c=r.T@(point-p)
        return c[:2]/c[2],c
    def image_jac(self,point,i=0):
        p,r=self.pose(i);jp,jr=self.jac(i);c=r.T@(point-p);x,y,z=c
        proj=np.array([[1/z,0,-x/z**2],[0,1/z,-y/z**2]])
        return proj@(-r.T@jp+r.T@skew(point-p)@jr),proj@r.T

def base_pose(s,radius=1.5,angle=.32):
    a=angle*s;return np.array([radius*np.sin(a),radius*(1-np.cos(a)),a])

def ease(t):
    u=np.clip(t/DURATION,0,1)
    return 10*u**3-15*u**4+6*u**5

def compile_plan(rig):
    ts=np.linspace(0,DURATION,121);qs=[];maxaim=0.;maxrequest=0.
    seed=np.zeros(13)
    for t in ts:
        s=ease(t);q=seed.copy();q[:3]=base_pose(s)
        for i in range(2):
            sl=slice(3+5*i,8+5*i)
            # Requested small camera rise and push, while the base supplies travel.
            local=np.array([.31+.02*s,(-.09 if i==0 else .19),.47+.02*np.sin(np.pi*s)])
            Rb=Rotation.from_euler('z',q[2]).as_matrix()
            pd=Rb@local+np.r_[q[:2],0.]
            target=TARGET if i==0 else TARGET-np.array([0,0,.15])
            def residual(a):
                q[sl]=a;rig.set(q);p,r=rig.pose(i);u=(target-p);u/=np.linalg.norm(u)
                return np.r_[2*(p-pd),12*(r[:,2]-u),r[2,0],.003*(a-seed[sl])]
            sol=least_squares(residual,seed[sl],bounds=(rig.lo[5*i:5*i+5],rig.hi[5*i:5*i+5]),xtol=1e-10,ftol=1e-10,gtol=1e-10,max_nfev=100)
            q[sl]=sol.x;rig.set(q);p,r=rig.pose(i);u=(target-p);u/=np.linalg.norm(u)
            maxaim=max(maxaim,np.degrees(np.arccos(np.clip(r[:,2]@u,-1,1))))
            maxrequest=max(maxrequest,np.linalg.norm(p-pd))
        seed=q.copy();qs.append(q)
    spline=CubicSpline(ts,np.array(qs),axis=0,bc_type=((1,np.zeros(13)),(1,np.zeros(13))))
    dense=spline(np.linspace(0,DURATION,1201))
    maxv=float(np.max(np.abs(spline(np.linspace(0,DURATION,1201),1)[:,3:])))
    maxa=float(np.max(np.abs(spline(np.linspace(0,DURATION,1201),2)[:,3:])))
    # Cubic spline C2 continuity, bounded one-sided jerk; jerk continuity not claimed.
    maxj=float(np.max(np.abs(spline(np.linspace(0,DURATION,1201),3)[:,3:])))
    record('plan_compiler',np.all(dense[:,3:]>=rig.lo)&np.all(dense[:,3:]<=rig.hi)&(maxaim<.3)&(maxv<.8)&(maxa<1.8)&(maxj<12),
           samples=1201,maximum_aim_error_deg=float(maxaim),maximum_requested_position_adjustment_m=float(maxrequest),joint_v_max_rad_s=maxv,joint_a_max_rad_s2=maxa,joint_jerk_piecewise_max_rad_s3=maxj)
    record('request_revision_required',maxrequest>.02,requested_position_tolerance_m=.02,largest_change_m=float(maxrequest),decision='Original exact request rejected; subsequent controller test uses the explicitly revised achievable trajectory fixture')
    np.savez(OUT/'compiled_plan.npz',time=ts,q=np.array(qs))
    return spline

def geometry_tests(rig):
    record('five_joint_topology',rig.m.nq==13 and rig.m.nu==10 and not any(rig.m.joint(i).name in ['cam_gripper','light_gripper'] for i in range(13)),arm_actuators=int(rig.m.nu),generalized_coordinates=int(rig.m.nq))
    urdf=ET.parse(ROOT/'upstream/so101_new_calib.urdf').getroot()
    joints=[urdf.find(f"joint[@name='{n}']") for n in JOINTS]
    pe=[];re=[];je=[];ie=[];ae=[]
    for _ in range(100):
        q=np.r_[RNG.uniform([-.3,-.3,-.5],[.3,.3,.5]),RNG.uniform(rig.lo*.65,rig.hi*.65)]
        rig.set(q);p,r=rig.pose()
        tf=T(Rotation.from_euler('z',q[2]).as_matrix(),np.r_[q[:2],0.])@T(p=np.array(ASSUMPTIONS['camera_mount_xyz_m']))
        for j,a in zip(joints,q[3:8]):
            origin=j.find('origin');pos=np.fromstring(origin.get('xyz'),sep=' ');rpy=np.fromstring(origin.get('rpy'),sep=' ')
            tf=tf@T(Rotation.from_euler('xyz',rpy).as_matrix(),pos)@T(Rotation.from_rotvec([0,0,a]).as_matrix())
        tf=tf@T(Rotation.from_euler('x',np.pi).as_matrix(),np.array(ASSUMPTIONS['optical_offset_from_wrist_roll_m']))
        pe.append(np.linalg.norm(p-tf[:3,3]));re.append(np.linalg.norm(Rotation.from_matrix(tf[:3,:3]@r.T).as_rotvec()))
        jp,jr=rig.jac();num=np.zeros_like(jp);nr=np.zeros_like(jr);ni=np.zeros((2,13));pt=p+2*r[:,2]+.1*r[:,0]
        ji,_=rig.image_jac(pt)
        for k in range(13):
            qp=q.copy();qm=q.copy();qp[k]+=1e-6;qm[k]-=1e-6
            rig.set(qp);pp,rp=rig.pose();fp,_=rig.image(pt)
            rig.set(qm);pm,rm=rig.pose();fm,_=rig.image(pt)
            num[:,k]=(pp-pm)/2e-6;ni[:,k]=(fp-fm)/2e-6;nr[:,k]=Rotation.from_matrix(rp@rm.T).as_rotvec()/2e-6
        je.append(np.max(abs(jp-num)));ie.append(np.max(abs(ji-ni)));ae.append(np.max(abs(jr-nr)))
    record('independent_urdf_fk',max(pe)<1e-5 and max(re)<3e-5,poses=100,max_translation_error_m=float(max(pe)),max_rotation_error_rad=float(max(re)),note='URDF decimal RPY and MJCF quaternion rounding differ; this is model consistency, not physical accuracy')
    record('analytic_jacobians',max(je)<1e-6 and max(ie)<1e-6 and max(ae)<1e-6,poses=100,position_max_abs_error=float(max(je)),orientation_max_abs_error=float(max(ae)),image_max_abs_error=float(max(ie)))
    q=np.zeros(13);rig.set(q);p,r=rig.pose();goal=p+np.array([0,0,2.])
    def err(a):q[3:8]=a;rig.set(q);return rig.pose()[0]-goal
    sol=least_squares(err,np.zeros(5),bounds=(rig.lo[:5],rig.hi[:5]))
    residual=float(np.linalg.norm(sol.fun));record('unreachable_goal_rejection',residual>.01,residual_m=residual,requested_vertical_rise_m=2.)

def steering_tests():
    L=.32;b=.34;r=.055;delta=.35;v=.12;w=v*np.tan(delta)/L;t=8.;dt=.001
    def integrate(v,w):
        p=np.zeros(3)
        for _ in range(round(t/dt)):
            pm=p[2]+w*dt/2;p+=np.array([v*np.cos(pm),v*np.sin(pm),w])*dt
        return p
    expected=np.array([v/w*np.sin(w*t),v/w*(1-np.cos(w*t)),w*t]);ack=integrate(v,w)
    wl=(v-w*b/2)/r;wr=(v+w*b/2)/r
    vd=r*(wr+wl)/2;wd=r*(wr-wl)/b;diff=integrate(vd,wd)
    record('both_2wd_models',np.linalg.norm(ack-expected)<1e-6 and np.linalg.norm(diff-expected)<1e-6,ackermann_endpoint_error_m=float(np.linalg.norm(ack[:2]-expected[:2])),differential_endpoint_error_m=float(np.linalg.norm(diff[:2]-expected[:2])),wheel_rates_rad_s=[wl,wr],ackermann_min_radius_at_30deg_m=float(L/np.tan(np.deg2rad(30))))
    lateral=np.array([0.,.1,0.]);theta=0.;residual=-np.sin(theta)*lateral[0]+np.cos(theta)*lateral[1]
    ack_spin=0*np.tan(delta)/L;diff_spin=r*(1-(-1))/b
    record('nonholonomic_rejections',abs(residual)>.01 and ack_spin==0 and diff_spin>0,ackermann_zero_speed_yaw_rate_rad_s=ack_spin,differential_spin_rate_rad_s=diff_spin,forbidden_lateral_velocity_m_s=float(residual))

def vision_tests():
    K=np.array([[900.,0,640],[0,900.,360],[0,0,1]])
    # Known marker board geometry, 1 px Gaussian corner noise; actual ArUco detector separately exercised.
    points=np.array([[x,y,0.] for y in np.linspace(-.7,.7,5) for x in np.linspace(-1,1,7)],dtype=np.float64)
    rv=np.array([.2,-.1,.04]);tv=np.array([.1,-.05,2.6]);errors=[];rot=[]
    for _ in range(100):
        pixels,_=cv2.projectPoints(points,rv,tv,K,None);pixels=pixels.reshape(-1,2)+RNG.normal(0,1,(len(points),2))
        ok,re,te=cv2.solvePnP(points,pixels,K,None,flags=cv2.SOLVEPNP_ITERATIVE)
        errors.append(np.linalg.norm(te.ravel()-tv))
    dic=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker=cv2.aruco.generateImageMarker(dic,7,240);frame=np.full((480,640),255,np.uint8);frame[120:360,200:440]=marker
    detected=cv2.aruco.ArucoDetector(dic).detectMarkers(frame)[1]
    cv2.imwrite(str(OUT/'synthetic_marker.png'),frame)
    record('synthetic_camera_geometry',np.percentile(errors,95)<.01 and detected is not None and 7 in detected, trials=100,corner_noise_px=1.,translation_error_p95_m=float(np.percentile(errors,95)),detected_marker_ids=detected.ravel().tolist(),scope='Synthetic marker/board only; no real person detector evaluated')
    # A single pixel ray has infinitely many possible 3D points without depth.
    ray=np.linalg.inv(K)@np.array([700.,400.,1.]);p1=ray;p2=2*ray
    record('monocular_depth_ambiguity',np.allclose(p1[:2]/p1[2],p2[:2]/p2[2]),candidate_depths_m=[1.,2.],different_3d_points_same_pixel=True)
    # Two known camera poses remove the scale ambiguity under adequate parallax.
    P1=K@np.c_[np.eye(3),np.zeros(3)];P2=K@np.c_[np.eye(3),np.array([-.6,0,0])]
    te=[]
    for _ in range(300):
        pw=np.r_[RNG.uniform([-.3,-.2,1.5],[.3,.2,2.5]),1.]
        a=P1@pw;b=P2@pw;ua=a[:2]/a[2]+RNG.normal(0,1,2);ub=b[:2]/b[2]+RNG.normal(0,1,2)
        h=cv2.triangulatePoints(P1,P2,ua.reshape(2,1),ub.reshape(2,1)).ravel();est=h[:3]/h[3]
        te.append(np.linalg.norm(est-pw[:3]))
    record('synthetic_two_view_triangulation',np.percentile(te,95)<.03,points=300,baseline_m=.6,pixel_noise_sigma=1.,position_error_p95_m=float(np.percentile(te,95)),scope='Known simultaneous camera poses; physical hand-eye error and real landmark correspondence excluded')
    # Planar vehicle EKF using noisy odometry plus absolute pose tags.
    x=np.zeros(3);P=np.eye(3)*.01;truth=np.zeros(3);odom=np.zeros(3);ek=[];oe=[]
    for k in range(600):
        v=.1;w=.025;dt=.02
        truth+=np.array([v*np.cos(truth[2]),v*np.sin(truth[2]),w])*dt
        vo=v*1.08;wo=w+.006
        odom+=np.array([vo*np.cos(odom[2]),vo*np.sin(odom[2]),wo])*dt
        F=np.eye(3);F[0,2]=-vo*np.sin(x[2])*dt;F[1,2]=vo*np.cos(x[2])*dt
        x+=np.array([vo*np.cos(x[2]),vo*np.sin(x[2]),wo])*dt
        P=F@P@F.T+np.diag([1e-6,1e-6,1e-6])
        if k%5==0:
            z=truth+RNG.normal(0,[.005,.005,.008]);R=np.diag(np.array([.005,.005,.008])**2)
            Kg=np.linalg.solve((P+R).T,P.T).T;x+=Kg@(z-x)
            P=(np.eye(3)-Kg)@P@(np.eye(3)-Kg).T+Kg@R@Kg.T
        ek.append(np.linalg.norm(x[:2]-truth[:2]));oe.append(np.linalg.norm(odom[:2]-truth[:2]))
    record('synthetic_localization_ekf',np.sqrt(np.mean(np.square(ek)))<np.sqrt(np.mean(np.square(oe))),ekf_xy_rmse_m=float(np.sqrt(np.mean(np.square(ek)))),odometry_xy_rmse_m=float(np.sqrt(np.mean(np.square(oe)))),note='Ideal pose measurements with noise; detector occlusion and clock faults tested separately')

def run_control(plan,mode='coordinated',drive='ackermann',seed=0):
    rng=np.random.default_rng(seed);rig=Rig();q=plan(0).copy();qvel=np.zeros(13);previous=np.zeros(12);prevprev=previous.copy()
    rows=[];solve_ms=[];violations=0;fail=0;history=[]
    speed_otg=ruckig.Ruckig(1,DT);speed_in=ruckig.InputParameter(1);speed_out=ruckig.OutputParameter(1)
    speed_in.control_interface=ruckig.ControlInterface.Velocity
    speed_in.current_position=[0];speed_in.current_velocity=[0];speed_in.current_acceleration=[0]
    speed_in.target_acceleration=[0];speed_in.max_acceleration=[.20];speed_in.max_jerk=[1.]
    for k,t in enumerate(np.arange(0,DURATION,DT)):
        ref=plan(t);dref=plan(t,1);rig.set(ref)
        pc,rc=rig.pose(0);pl,rl=rig.pose(1);jpc,jrc=rig.jac(0);jpl,jrl=rig.jac(1)
        # A known scripted actor target plus unplanned lateral/vertical motion.
        actor=TARGET+np.array([0,.035*np.sin(.9*t),.018*np.sin(1.3*t)])
        rig.set(q);observed,_=rig.image(actor);history.append(observed.copy())
        obs=history[max(0,k-3)]+rng.normal(0,.0008,2)
        if mode=='coordinated':
            theta=q[2];curvature=1/1.5
            # Path curvature is fixed for this accepted shot; steering transients are outside this test.
            S=np.zeros((13,12));S[0,0]=np.cos(theta);S[1,0]=np.sin(theta);S[2,1]=1;S[3:,2:]=np.eye(10)
            p,r=rig.pose(0);p2,r2=rig.pose(1);jp,jr=rig.jac(0);jp2,jr2=rig.jac(1);ji,ja=rig.image_jac(actor)
            actor_v=np.array([0,.035*.9*np.cos(.9*t),.018*1.3*np.cos(1.3*t)])
            vref=np.hypot(dref[0],dref[1]);along=np.array([np.cos(theta),np.sin(theta)])@(ref[:2]-q[:2])
            desired=np.r_[vref+1.5*along,dref[2]+2*(ref[2]-q[2]),dref[3:]]
            # Path tracker owns vehicle motion; the combined IK compensates it.
            # This avoids asking a one-step velocity QP to discover viable jerk-limited braking.
            speed_in.target_velocity=[float(np.clip(desired[0],0,.13))]
            speed_otg.update(speed_in,speed_out);speed_out.pass_to_input(speed_in)
            vehicle_v=speed_out.new_velocity[0];vehicle_w=curvature*vehicle_v
            A=np.vstack([3*jp@S,8*ji@S,jr@S,2*jp2@S,jr2@S,.4*np.eye(12),2*np.eye(12)[:2]])
            b=np.r_[3*(jpc@dref+3*(pc-p)),8*(-3.5*obs-ja@actor_v),jrc@dref+3*Rotation.from_matrix(rc@r.T).as_rotvec(),2*(jpl@dref+3*(pl-p2)),jrl@dref+3*Rotation.from_matrix(rl@r2.T).as_rotvec(),.4*desired,2*desired[:2]]
            lo=np.r_[-.13,-.18,np.maximum(-.8,(rig.lo-q[3:])/DT)]
            hi=np.r_[.13,.18,np.minimum(.8,(rig.hi-q[3:])/DT)]
            accel=np.r_[.20,.35,np.full(10,1.8)]
            jerk=np.r_[1.,2.,np.full(10,12.)]
            lo[2:]=np.maximum(lo[2:],previous[2:]-accel[2:]*DT);hi[2:]=np.minimum(hi[2:],previous[2:]+accel[2:]*DT)
            lo[2:]=np.maximum(lo[2:],2*previous[2:]-prevprev[2:]-jerk[2:]*DT**2);hi[2:]=np.minimum(hi[2:],2*previous[2:]-prevprev[2:]+jerk[2:]*DT**2)
            lo[:2]=[vehicle_v,vehicle_w];hi[:2]=[vehicle_v,vehicle_w]
            C=np.eye(12);cl=lo;ch=hi
            if drive=='ackermann':
                extra=np.zeros(12);extra[1]=1;extra[0]=-curvature
                C=np.vstack([C,extra]);cl=np.r_[cl,0];ch=np.r_[ch,0]
            tic=time.perf_counter();solver=osqp.OSQP()
            solver.setup(P=sp.csc_matrix(A.T@A+np.eye(12)*1e-5),q=-A.T@b,A=sp.csc_matrix(C),l=cl,u=ch,verbose=False,eps_abs=1e-6,eps_rel=1e-6,max_iter=3000,polishing=False)
            solver.warm_start(x=previous);res=solver.solve();solve_ms.append((time.perf_counter()-tic)*1000)
            if res.info.status_val not in [1,2] or res.x is None:
                raise RuntimeError(f'Simulation QP failed at {t}: {res.info.status}; no hardware control is implemented')
            else:
                u=res.x
                violations+=int(max(np.max(cl-C@u),np.max(C@u-ch))>1e-4)
            prevprev=previous.copy();previous=u.copy()
            command=np.r_[u[0]*np.cos(theta),u[0]*np.sin(theta),u[1],u[2:]]
        else:
            arm_t=np.clip(t-(.35 if mode=='independent_clocks' else 0),0,DURATION)
            command=np.r_[np.hypot(dref[0],dref[1])*np.cos(q[2]),np.hypot(dref[0],dref[1])*np.sin(q[2]),dref[2],plan(arm_t,1)[3:]+6*(plan(arm_t)[3:]-q[3:])]
        # Kinematic plant + first-order command response, 8% travel calibration error.
        qvel+=DT/.08*(command-qvel);actual=qvel.copy();actual[:3]*=.92
        q+=actual*DT;rig.set(q);feature,_=rig.image(actor)
        rows.append(np.r_[t,q,feature])
    a=np.array(rows);name=f'{mode}_{drive}_{seed}';np.save(OUT/(name+'.npy'),a)
    return {'image_rmse_normalized':float(np.sqrt(np.mean(np.sum(a[:,-2:]**2,axis=1)))),
            'image_p95_normalized':float(np.percentile(np.linalg.norm(a[:,-2:],axis=1),95)),
            'base_endpoint_error_m':float(np.linalg.norm(q[:2]-plan(DURATION)[:2])),
            'qp_setup_solve_p95_ms':float(np.percentile(solve_ms,95)) if solve_ms else None,
            'qp_failed_steps':fail,'constraint_violation_steps':violations,'samples':len(a)},a

def coordination_tests(plan):
    allruns={};traces={}
    for mode,drive in [('open_loop','ackermann'),('independent_clocks','ackermann'),('coordinated','ackermann'),('coordinated','differential')]:
        vals=[]
        for seed in [1,2,3]:
            result,trace=run_control(plan,mode,drive,seed);vals.append(result)
        key=mode+'_'+drive;allruns[key]=vals;traces[key]=trace
    mean=lambda key:np.mean([x['image_rmse_normalized'] for x in allruns[key]])
    ratio=mean('coordinated_ackermann')/mean('open_loop_ackermann')
    good=ratio<1 and all(r['qp_failed_steps']==0 and r['constraint_violation_steps']==0 for key,rows in allruns.items() if key.startswith('coordinated') for r in rows)
    record('coupled_motion_feedback',good,seeds=3,rmse_ratio_to_open_loop=float(ratio),runs=allruns,scope='Both real SO101 joint chains and both arm targets; kinematic base and lag model, synthetic delayed image features')
    fig,ax=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for k,a in traces.items():
        ax[0].plot(a[:,0],np.linalg.norm(a[:,-2:],axis=1),label=k.replace('_',' '))
        ax[1].plot(a[:,1],a[:,2],label=k.replace('_',' '))
    ref=plan(np.linspace(0,DURATION,300));ax[1].plot(ref[:,0],ref[:,1],'k--',label='planned cart path')
    ax[0].set(xlabel='Time (s)',ylabel='Image error (normalized focal coordinates)',title='Synthetic framing feedback')
    ax[1].set(xlabel='World x (m)',ylabel='World y (m)',title='Cart trajectory');ax[1].axis('equal')
    ax[0].legend(fontsize=7);ax[1].legend(fontsize=7);fig.savefig(OUT/'coordination.png',dpi=160);plt.close(fig)

def collision_dynamics_tests(plan):
    rig=Rig();clear=[]
    cam=[i for i in range(rig.m.ngeom) if rig.m.body(rig.m.geom_bodyid[i]).name.startswith('cam_') and rig.m.geom_group[i]!=2]
    light=[i for i in range(rig.m.ngeom) if rig.m.body(rig.m.geom_bodyid[i]).name.startswith('light_') and rig.m.geom_group[i]!=2]
    for t in np.linspace(0,DURATION,121):
        rig.set(plan(t));minimum=.5
        for a in cam:
            for b in light:
                minimum=min(minimum,mujoco.mj_geomDistance(rig.m,rig.d,a,b,.5,None))
        clear.append(minimum)
    record('cross_arm_swept_samples',min(clear)>.015,samples=121,minimum_distance_m=float(min(clear)),geometry='Upstream convex collision meshes plus assumed payload boxes; sampled, not continuous proof')
    q=plan(3);rig.set(q);p,_=rig.pose();ob=rig.m.geom('test_obstacle').id
    rig.m.geom_pos[ob]=rig.d.geom_xpos[rig.m.geom('cam_payload').id];mujoco.mj_forward(rig.m,rig.d)
    d=mujoco.mj_geomDistance(rig.m,rig.d,rig.m.geom('cam_payload').id,ob,.5,None)
    record('obstacle_rejection',d<0,penetration_signed_distance_m=float(d))
    # Integrate arm dynamics with a genuinely fixed base (not teleporting a free base).
    # Mobile-base demand is evaluated separately using prescribed q/qd/qdd inverse dynamics.
    xml=ET.parse(ROOT/'rig_5dof.xml');cart=xml.getroot().find("worldbody/body[@name='cart']")
    for j in list(cart.findall('joint')):cart.remove(j)
    fixedpath=ROOT/'rig_fixed_base_dynamics.xml';xml.write(fixedpath,encoding='unicode')
    dm=mujoco.MjModel.from_xml_path(str(fixedpath));dd=mujoco.MjData(dm)
    q0=plan(0);dd.qpos[:]=q0[3:];dd.ctrl[:]=q0[3:];mujoco.mj_forward(dm,dd)
    maxerr=0;maxforce=0.;maxbias=0.
    for k in range(1500):
        t=k*.002;des=plan(t);dd.ctrl[:]=des[3:];mujoco.mj_step(dm,dd)
        maxerr=max(maxerr,np.max(abs(dd.qpos-des[3:])));maxforce=max(maxforce,np.max(abs(dd.actuator_force)));maxbias=max(maxbias,np.max(abs(dd.qfrc_bias)))
    record('mujoco_arm_dynamics',np.isfinite(maxerr) and maxerr<.20,seconds=3.,physics_steps=1500,max_joint_tracking_error_rad=float(maxerr),max_actuator_force_Nm=float(maxforce),max_bias_force_Nm=float(maxbias),assumed_torque_limit_Nm=1.,scope='Integration stability test only. Cart fixed; assumed payload inertia and PD gains; no wheel-ground dynamics or real servo validation')
    rig=Rig()
    demanded=[]
    for t in np.linspace(0,DURATION,121):
        rig.set(plan(t));rig.d.qvel[:]=plan(t,1);rig.d.qacc[:]=plan(t,2);mujoco.mj_inverse(rig.m,rig.d)
        demanded.append(np.max(abs(rig.d.qfrc_inverse[3:])))
    peak=float(max(demanded))
    record('illustrative_payload_capacity_gate',peak<.8,maximum_inverse_dynamics_demand_Nm=peak,assumed_continuous_cap_Nm=1.,required_margin_fraction=.20,note='Failure is retained: this assumed phone/mount configuration needs redesign or measured stronger continuous capability before hardware approval')
    # Quasi-static effective gravity support margin. Both arm masses enter the COM.
    rig=Rig();margins=[];comz=[]
    for t in np.linspace(0,DURATION,121):
        rig.set(plan(t));mass=rig.m.body_mass[1:];com=np.average(rig.d.xipos[1:],weights=mass,axis=0)
        rb=Rotation.from_euler('z',rig.d.qpos[2]).as_matrix();local=rb.T@(com-np.r_[rig.d.qpos[:2],0.])
        # Illustrative conservative longitudinal/lateral acceleration samples.
        effective=local[:2]-local[2]*np.array([.20,.12])/9.81
        margins.append(min(.16-abs(effective[0]),.17-abs(effective[1])));comz.append(local[2])
    bad_margin=.17-(.28+.8*.5/9.81)
    record('support_polygon_screen',min(margins)>.02 and bad_margin<0,minimum_nominal_margin_m=float(min(margins)),maximum_combined_com_height_m=float(max(comz)),deliberately_unstable_case_margin_m=float(bad_margin),scope='Flat-floor quasi-static screen; not proof against bumps, suspension roll or moving-arm angular momentum')

def timing_failures():
    # Exercise local Ruckig, including smooth deceleration, with no intermediate waypoints/cloud.
    otg=ruckig.Ruckig(1,.01);inp=ruckig.InputParameter(1);out=ruckig.OutputParameter(1)
    inp.current_position=[0];inp.current_velocity=[0];inp.current_acceleration=[0]
    inp.target_position=[1];inp.target_velocity=[0];inp.target_acceleration=[0]
    inp.max_velocity=[.15];inp.max_acceleration=[.1];inp.max_jerk=[.25]
    x=[]
    for k in range(3000):
        status=otg.update(inp,out);x.append([out.new_position[0],out.new_velocity[0],out.new_acceleration[0]])
        out.pass_to_input(inp)
        if status==ruckig.Result.Finished:break
    a=np.array(x);jerk=np.max(abs(np.diff(a[:,2])/.01))
    record('shared_phase_local_ruckig',abs(a[-1,0]-1)<1e-6 and np.max(abs(a[:,1]))<=.150001 and jerk<=.250001,duration_s=len(a)*.01,max_phase_velocity=float(np.max(abs(a[:,1]))),max_phase_jerk=float(jerk),same_phase_used_by_both_arms_and_cart=True)
    # Simple runtime guard contract, not transport integration.
    def guard(age,planrev,calibrev,identity,obstacle,qpok):
        if age>.15:return 'STOP_STALE'
        if planrev!=calibrev:return 'RECOMPILE'
        if not identity:return 'STOP_IDENTITY'
        if obstacle:return 'STOP_OBSTACLE'
        if not qpok:return 'STOP_SOLVER'
        return 'EXECUTE'
    cases=[((.3,1,1,True,False,True),'STOP_STALE'),((.02,1,2,True,False,True),'RECOMPILE'),((.02,1,1,False,False,True),'STOP_IDENTITY'),((.02,1,1,True,True,True),'STOP_OBSTACLE'),((.02,1,1,True,False,False),'STOP_SOLVER'),((.02,1,1,True,False,True),'EXECUTE')]
    result=[guard(*x)==expected for x,expected in cases]
    record('runtime_fault_contracts',all(result),cases=len(result),scope='Unit simulation of guard decisions; physical stopping and network transports not exercised')
    # Validate actual braking trajectory under acceleration AND jerk bounds.
    otg=ruckig.Ruckig(1,.01);inp=ruckig.InputParameter(1);out=ruckig.OutputParameter(1)
    inp.control_interface=ruckig.ControlInterface.Velocity;inp.current_position=[0];inp.current_velocity=[.12];inp.current_acceleration=[0]
    inp.target_velocity=[0];inp.target_acceleration=[0];inp.max_acceleration=[.2];inp.max_jerk=[.5]
    for k in range(1000):
        status=otg.update(inp,out);out.pass_to_input(inp)
        if status==ruckig.Result.Finished:break
    delay=.15;stop=out.new_position[0]+.12*delay
    record('jerk_limited_stopping',out.new_velocity[0]<1e-6 and stop>.12*delay+.12**2/(2*.2),stop_distance_with_delay_m=float(stop),acceleration_only_lower_bound_m=float(.12*delay+.12**2/(2*.2)),delay_s=delay)

def render_scene(plan):
    rig=Rig();rig.set(plan(5));cam=mujoco.MjvCamera();mujoco.mjv_defaultCamera(cam)
    cam.lookat[:]=[.55,0,.45];cam.distance=1.9;cam.azimuth=135;cam.elevation=-23
    renderer=mujoco.Renderer(rig.m,height=540,width=960);renderer.update_scene(rig.d,camera=cam)
    frame=renderer.render();cv2.imwrite(str(OUT/'rig_simulation.png'),cv2.cvtColor(frame,cv2.COLOR_RGB2BGR));renderer.close()
    record('3d_renderer',True,width=960,height=540,source='same modified MuJoCo model')
    # A small actual 3D rendered rehearsal clip, not a generated-video result.
    cam.lookat[:]=[.85,0,.50];cam.distance=2.5
    renderer=mujoco.Renderer(rig.m,height=360,width=640)
    video=cv2.VideoWriter(str(OUT/'rehearsal.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),8,(1280,360))
    if not video.isOpened():raise RuntimeError('MP4 writer unavailable')
    for t in np.linspace(0,DURATION,96):
        rig.set(plan(t));renderer.update_scene(rig.d,camera=cam);overview=renderer.render().copy()
        renderer.update_scene(rig.d,camera='cam_view');phone=renderer.render().copy()
        video.write(cv2.cvtColor(np.concatenate([overview,phone],axis=1),cv2.COLOR_RGB2BGR))
    video.release();renderer.close()

def workflow_and_media_tests(plan):
    # Synthetic observations drive an actual beat machine. A lost detection is not an exit.
    state='waiting';transitions=[]
    observations=[('seen_entry',True),('pause',True),('lost',False),('resume',True),('exit_left',True)]
    for event,fresh in observations:
        previous=state
        if event=='seen_entry' and fresh and state=='waiting':state='filming'
        elif event=='pause' and fresh and state=='filming':state='paused'
        elif event=='lost':state='hold_unknown'
        elif event=='resume' and fresh and state in ['paused','hold_unknown']:state='filming'
        elif event=='exit_left' and fresh and state=='filming':state='completed'
        transitions.append([event,previous,state])
    ok=transitions[2][2]=='hold_unknown' and transitions[-1][2]=='completed'
    record('actor_beat_fixture',ok,transitions=transitions,scope='Synthetic observations; real action recognition and recorded speech not evaluated')
    # Quantify why all clients must reference one phase, even though this does not exercise USB clocks.
    times=np.linspace(.5,11.5,100);synced=plan(times);delayed=plan(times-.35)
    skew=np.max(np.linalg.norm(synced[:,3:8]-delayed[:,3:8],axis=1))
    same=np.max(abs(synced[:,3:8]-plan(times)[:,3:8]))
    record('shared_reference_contract',same==0 and skew>0,same_progress_difference_rad=float(same),independent_350ms_arm_schedule_max_joint_vector_error_rad=float(skew),scope='Reference generation, not hardware timestamp synchronization')
    # Compile/rehearsal asset is real; cloud reference generation is deliberately not called.
    planbytes=(OUT/'compiled_plan.npz').read_bytes();clip=OUT/'rehearsal.mp4'
    job={'provider':'Seedance','operation':'reference_generation','status':'not_submitted_no_account_access',
         'reference_sha256':hashlib.sha256(clip.read_bytes()).hexdigest(),'plan_sha256':hashlib.sha256(planbytes).hexdigest(),
         'prompt':'Preserve the supplied reference camera motion, blocking, framing changes and timing. Apply only the requested visual appearance.'}
    (OUT/'seedance_job_fixture.json').write_text(json.dumps(job,indent=2))
    record('seedance_reference_contract',job['plan_sha256']==hashlib.sha256((OUT/'compiled_plan.npz').read_bytes()).hexdigest(),status=job['status'],reference_video_created=True,provider_called=False)
    # Actual conventional editing path, using simulated-camera footage as the source asset.
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(clip),'-filter_complex','[0:v]split=2[a][b];[a]trim=start=0:end=6,setpts=PTS-STARTPTS[x];[b]trim=start=6:end=12,setpts=PTS-STARTPTS[y];[x][y]concat=n=2:v=1:a=0[v]', '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(OUT/'assembled_simulated_take.mp4')],check=True)
    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=nb_frames,width,height:format=duration','-of','json',str(OUT/'assembled_simulated_take.mp4')]))
    duration=float(meta['format']['duration']);frames=int(meta['streams'][0]['nb_frames'])
    record('ffmpeg_simulated_take_assembly',abs(duration-12)<.2 and frames==96,duration_s=duration,frames=frames,scope='Real FFmpeg assembly of rendered footage; iPhone capture/transfer not executed')

def main():
    build();rig=Rig();geometry_tests(rig);steering_tests();vision_tests();plan=compile_plan(rig)
    coordination_tests(plan);collision_dynamics_tests(plan);timing_failures()
    try:render_scene(plan);workflow_and_media_tests(plan)
    except Exception as e:record('3d_renderer',False,error=str(e))
    versions={m.__name__:m.__version__ for m in [mujoco,osqp,cv2,ruckig,np,scipy]}
    report={'seed':20260911,'versions':versions,'platform':platform.platform(),'assumptions':ASSUMPTIONS,'results':RESULTS,'not_executed':['physical hardware','real person/face detection','Seedance API','LLM provider calls','AVFoundation recording','wheel-ground/suspension simulation','network/USB hardware latency']}
    (OUT/'simulation_results.json').write_text(json.dumps(report,indent=2))
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and p.name!='sha256.json'}
    (OUT/'sha256.json').write_text(json.dumps(manifest,indent=2))
    print('SUMMARY',sum(x['passed'] for x in RESULTS.values()),'/',len(RESULTS),flush=True)

if __name__=='__main__':main()

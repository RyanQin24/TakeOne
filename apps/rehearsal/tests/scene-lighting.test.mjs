import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {ATMOSPHERE_PROFILES,atmosphereNames,createSceneLibrary} from '../dist/scene-library.js';

function rig(){
  const scene=new THREE.Scene();scene.background=new THREE.Color();
  const ground={material:{color:new THREE.Color()}};
  const sun=new THREE.DirectionalLight();
  const hemisphere=new THREE.HemisphereLight();
  const rim=new THREE.DirectionalLight();
  const subject=new THREE.SpotLight();
  const library=createSceneLibrary(scene,ground,sun,()=>{}, {hemisphere,rim,subject});
  return {scene,ground,sun,hemisphere,rim,subject,library};
}

const practical={object_id:'lamp',asset_id:'practical_light',label:'Practical',position_m:[0,0,.9],size_m:[.4,.4,1.8],yaw_rad:0};

test('all seven atmosphere profiles are finite and day/night are materially different',()=>{
  assert.equal(atmosphereNames().length,7);
  for(const [name,p] of Object.entries(ATMOSPHERE_PROFILES)){
    assert.ok(p.label&&p.subjectRole,name);
    for(const key of ['sunIntensity','hemiIntensity','rimIntensity','subjectIntensity','practicalIntensity'])
      assert.ok(Number.isFinite(p[key])&&p[key]>=0,`${name}:${key}`);
  }
  assert.ok(ATMOSPHERE_PROFILES.exterior_day.sunIntensity>ATMOSPHERE_PROFILES.exterior_night.sunIntensity*10);
  assert.ok(ATMOSPHERE_PROFILES.exterior_night.practicalIntensity>ATMOSPHERE_PROFILES.exterior_day.practicalIntensity);
});

test('loading and switching atmospheres updates real lights without leaking practicals',()=>{
  const {scene,sun,hemisphere,rim,subject,library}=rig();
  library.load({atmosphere:'exterior_night',objects:[practical],cast:[]});
  let practicals=[];library.root.traverse(o=>{if(o.userData?.takeonePractical)practicals.push(o);});
  assert.equal(practicals.length,1);assert.equal(practicals[0].intensity,ATMOSPHERE_PROFILES.exterior_night.practicalIntensity);
  assert.equal(sun.intensity,ATMOSPHERE_PROFILES.exterior_night.sunIntensity);
  assert.equal(hemisphere.intensity,ATMOSPHERE_PROFILES.exterior_night.hemiIntensity);
  assert.equal(rim.intensity,ATMOSPHERE_PROFILES.exterior_night.rimIntensity);
  assert.equal(subject.intensity,ATMOSPHERE_PROFILES.exterior_night.subjectIntensity);
  library.setAtmosphere('exterior_day');
  assert.equal(practicals[0].intensity,0);assert.equal(sun.intensity,ATMOSPHERE_PROFILES.exterior_day.sunIntensity);
  library.load({atmosphere:'interior_warm',objects:[practical],cast:[]});
  practicals=[];library.root.traverse(o=>{if(o.userData?.takeonePractical)practicals.push(o);});
  assert.equal(practicals.length,1,'scene reload must remove the previous practical light');
  assert.ok(scene.children.includes(library.root));
});

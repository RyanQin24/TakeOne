import test from 'node:test';
import assert from 'node:assert/strict';
import {movementFields, readMovement, movementDescription} from '../dist/director-movement.js';

const scale=180/Math.PI;
const catalog={fields:{sweep_rad:{label:'Orbit sweep',minimum:Math.PI/12,maximum:2*Math.PI,scale,unit:'°',step:5},
  rise_start:{label:'Begin change',minimum:0,maximum:0.95,scale:100,unit:'%',step:5},
  duration_s:{label:'Duration',minimum:2,maximum:120,scale:1,unit:'s',step:1}},
  lens_field:{label:'Starting focal length',minimum:13,maximum:360,scale:1,unit:'mm',step:1},
  templates:[{id:'hero_orbit',name:'Hero reveal',parameters:['sweep_rad','rise_start','duration_s'],
    defaults:{sweep_rad:Math.PI/2,rise_start:0.1,focal_mm:35}}]};
const shot={movement:{template_id:'hero_orbit',subject_motion:'hold',parameters:[{name:'sweep_rad',value:Math.PI/6}]}};

test('SI radians and fractions display as degrees and percentages and round-trip',()=>{
  const fields=movementFields(catalog,shot,'hero_orbit');
  assert.ok(Math.abs(fields[0].value-30)<1e-9);
  assert.equal(fields[1].value,10);
  assert.ok(!fields.some(f=>f.key==='duration_s'));
  const movement=readMovement(catalog,shot,'hero_orbit','walk',new Map(fields.map(f=>[f.key,String(f.value)])));
  assert.equal(movement.subject_motion,'walk');
  assert.ok(Math.abs(movement.parameters[0].value-Math.PI/6)<1e-9);
  assert.equal(movement.parameters[1].value,0.1);
  assert.equal(shot.movement.subject_motion,'hold');
});

test('blank, non-finite and outside-range edits never become zero or a guessed movement',()=>{
  const valid=new Map([['sweep_rad','30'],['rise_start','10'],['focal_mm','35']]);
  for(const value of ['', 'Infinity', '-20']) {
    const data=new Map(valid);data.set('focal_mm',value);
    assert.throws(()=>readMovement(catalog,shot,'hero_orbit','hold',data));
  }
  assert.throws(()=>movementFields(catalog,shot,'made_up'));
});

test('movement readout uses human labels and units',()=>{
  assert.match(movementDescription(catalog,shot),/Hero reveal.*Orbit sweep: 30 °/);
  assert.equal(movementDescription(catalog,{}),'Choose a simulator movement');
});

// Characterize physical limitations without mistaking UI checks for motor validation.
// Run: node tests/audit-controller.mjs
import assert from 'node:assert/strict';
import {createState, step} from '../dist/rehearsal.js';

const dt=.02;
const held=createState();
Object.assign(held,{playing:true,actor:.4,robot:.4,velocity:1/16,actorPaused:true});
const before=held.robot;
step(held,dt);
const actualRate=(held.robot-before)/dt;
assert.equal(actualRate,0);
assert.ok(held.velocity>0);

const lost=createState();
Object.assign(lost,{playing:true,actor:.4,robot:.4,velocity:1/16,lost:true});
step(lost,dt);
assert.equal(lost.robot,.4);
assert.equal(lost.velocity,0);

console.log(JSON.stringify({
  actorPause:{previousPhaseRate_per_s:1/16,actualPhaseRateAfterPause_per_s:actualRate,
    storedVelocityAfterPause_per_s:held.velocity,
    finding:'Position clamp overrides the rate limiter; stored velocity is not the realized trajectory derivative.'},
  trackingLoss:{previousPhaseRate_per_s:1/16,nextPhaseRate_per_s:0,
    finding:'Immediate kinematic freeze, not acceleration- or jerk-bounded physical braking.'},
  physicalValidation:false
},null,2));

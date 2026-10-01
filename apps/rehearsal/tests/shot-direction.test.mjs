import test from 'node:test';
import assert from 'node:assert/strict';
import {performanceAt,shootingGuide} from '../dist/shot-direction.js';

const segment={kind:'shot',t0_s:10,setup_s:3,filming_s:8,edit:{start_ms:0,end_ms:5000},
  shot_card:{beats:[{start_s:0,end_s:2,action:'Look first',actor_id:'lead'},{start_s:2,end_s:5,action:'Then turn',actor_id:'lead'}]}};
test('Performance uses filming time, excludes setup and changes at the exact beat',()=>{
  assert.equal(performanceAt(segment,12).phase,'setup');
  assert.equal(performanceAt(segment,13).current.action,'Look first');
  assert.equal(performanceAt(segment,15).current.action,'Then turn');
  assert.equal(performanceAt(segment,18).phase,'outside_edit');
});
test('A short source never invents a performance cue in the preview hold',()=>{
  assert.equal(performanceAt({...segment,filming_s:1},14.1).current,null);
  assert.equal(performanceAt({...segment,t0_s:0,setup_s:0},2).current.action,'Then turn');
});
test('Shooting guide preserves actions and manual limitations in a portable artifact',()=>{
  const guide=shootingGuide({title:'A new story',document_digest:'revision',requested_aspect:'9:16',scenes:[],actors:[{actor_id:'lead',name:'Performer'}],segments:[segment]});
  assert.match(guide,/Look first/);assert.match(guide,/Then turn/);
  assert.match(guide,/9:16/);assert.match(guide,/16:9 landscape/);
  assert.match(guide,/Performer/);assert.match(guide,/Hardware and live tracking need separate qualification/);
});

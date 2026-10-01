import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {Box3,Vector3} from 'three';

for(const variant of ['ring','panel','tube'])test(`${variant} GLB imports as a complete, meter-scale robot`,async()=>{
  const bytes=fs.readFileSync(new URL(`../dist/models/take-one-${variant}.glb`,import.meta.url));
  const buffer=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
  const {scene}=await new GLTFLoader().parseAsync(buffer,'');
  const names=new Set();let count=0;
  scene.traverse(o=>{names.add(o.name);if(o.isMesh)count++;});
  assert.ok(count>70);
  for(const name of ['cart','cam_base','light_base','upright_front','upright_rear','phone_clamp','light_payload','light_emitter'])assert.ok(names.has(name),name);
  const bounds=new Box3().setFromObject(scene),size=bounds.getSize(new Vector3());
  assert.ok(Math.abs(bounds.min.y)<.01,'wheels rest on ground');
  assert.ok(size.y>1.5&&size.y<1.8,'height in meters');
  assert.ok(size.x>.8&&size.x<1.0,'lower cart length follows local +X after rotation');
  assert.ok(size.z>.6&&size.z<1.2,'crosswise width and upper-arm depth');
  for(const side of ['left','right']){
    const front=scene.getObjectByName('drive_'+side).getWorldPosition(new Vector3());
    const rear=scene.getObjectByName('caster_'+side).getWorldPosition(new Vector3());
    assert.ok(Math.abs(front.x+.27)<1e-6,'powered front axle at cart -X');
    assert.ok(Math.abs(rear.x-.32)<1e-6,'rear caster pivot at cart +X');
  }
});

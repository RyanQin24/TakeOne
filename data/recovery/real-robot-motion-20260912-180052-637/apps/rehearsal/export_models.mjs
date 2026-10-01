// Export exactly the compiled geometry used by the simulator, posed at mid-shot.
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {GLTFExporter} from 'three/addons/exporters/GLTFExporter.js';
import {createRobot,poseRobot,disposeRobot} from './dist/robot-model.js';

const root=path.dirname(fileURLToPath(import.meta.url));
globalThis.FileReader=class {
  readAsArrayBuffer(blob){blob.arrayBuffer().then(result=>{this.result=result;this.onloadend?.();});}
  readAsDataURL(blob){blob.arrayBuffer().then(result=>{this.result='data:'+blob.type+';base64,'+Buffer.from(result).toString('base64');this.onloadend?.();});}
};
fs.mkdirSync(path.join(root,'dist','models'),{recursive:true});
for(const variant of ['ring','panel','tube']){
  const python=process.env.TAKEONE_PYTHON || path.resolve(root,'../../.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const payload=JSON.parse(execFileSync(python,['-c',
    `import json; from takeone.simulation.robot import visual_model; from takeone.planning.compiler import compile_shot; s=compile_shot({'lightType':'${variant}'}); print(json.dumps({'model':visual_model('${variant}'),'frame':s['frames'][160]}))`],
    {cwd:root,maxBuffer:64*1024*1024,encoding:'utf8'}));
  const robot=createRobot(payload.model);poseRobot(robot.bodyGroups,payload.frame);
  // Remove the shot's world translation/yaw, then convert Z-up meters to glTF Y-up.
  const cart=robot.bodyGroups[payload.model.bodyNames.indexOf('cart')];
  const origin=cart.position.clone(),inverse=cart.quaternion.clone().invert();
  for(const group of robot.bodyGroups){group.position.sub(origin).applyQuaternion(inverse);group.quaternion.premultiply(inverse);}
  robot.root.rotation.x=-Math.PI/2;robot.root.updateMatrixWorld(true);
  const data=await new GLTFExporter().parseAsync(robot.root,{binary:true});
  const destination=path.join(root,'dist','models',`take-one-${variant}.glb`);
  fs.writeFileSync(destination,Buffer.from(data));console.log(destination);disposeRobot(robot.root);
}

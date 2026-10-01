import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {AssetLayer} from '../dist/asset-library/asset-loader.js';

test('disposing during loading releases late instances and drains idle resources', async () => {
  let resolve, released = 0, drained = 0;
  const library = {
    createInstance: () => new Promise(done => { resolve = done; }),
    cache: {clearIdle: () => drained++},
  };
  const scene = new THREE.Scene(), layer = new AssetLayer(scene, library);
  const pending = layer.load([{asset_id: 'test'}]);
  layer.dispose();
  resolve({root: new THREE.Group(), release: () => released++});
  assert.equal(await pending, false);
  assert.equal(released, 1);
  assert.equal(drained, 2);
  assert.equal(scene.children.length, 0);
  await assert.rejects(layer.load([]), /disposed/);
});

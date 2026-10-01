import test from 'node:test';
import assert from 'node:assert/strict';
import {createSceneObject, matchingAssets, inventoryLines} from '../dist/asset-library/scene-inventory.js';
import {shootingGuide} from '../dist/shot-direction.js';
const asset = {id: 'lib:kenney-furniture:chair-a-1234567890:0123456789abcdef', name: 'Chair', default_size_m: [0.5, 0.6, 0.9]};
const uuid = '12345678-1234-1234-1234-123456789012';

test('long catalog IDs use a separate bounded scene-object identity', () => {
  const value = createSceneObject(asset, ' Work chair ', uuid);
  assert.equal(value.object_id.length, 40);
  assert.equal(value.asset_id, asset.id);
  assert.equal(value.label, 'Work chair');
  assert.equal(value.availability, 'proposed');
  assert.deepEqual(value.position_m, [4, 4, 0.45]);
});
test('instance size edits cannot change the catalog dimensions', () => {
  const value = createSceneObject(asset, '', uuid);
  value.size_m[0] = 3;
  assert.equal(asset.default_size_m[0], 0.5);
});
test('two instances retain one asset reference but distinct object identities', () => {
  const a = createSceneObject(asset), b = createSceneObject(asset);
  assert.notEqual(a.object_id, b.object_id);
  assert.equal(a.asset_id, b.asset_id);
});
test('an invalid instance identity is refused', () => {
  assert.throws(() => createSceneObject(asset, '', 'not-a-uuid'));
});
test('search is bounded and retains the current selection outside the matches', () => {
  const entries = Array.from({length: 100}, (_, i) => ({id: 'chair-' + i, name: 'Chair ' + i}));
  const result = matchingAssets(entries, 'chair', 'chair-99');
  assert.equal(result.total, 100); assert.equal(result.entries.length, 41);
  assert.equal(result.entries[0].id, 'chair-99');
});
test('search matches all typed words without silently choosing the first result', () => {
  assert.equal(matchingAssets([asset], 'KENNEY chair').entries[0].id, asset.id);
  assert.equal(matchingAssets([asset], 'unavailable').entries.length, 0);
});
test('legacy inventory is unconfirmed, never physically present by inference', () => {
  const object = createSceneObject(asset, 'Chair', uuid); delete object.availability;
  assert.match(inventoryLines({objects: [object]})[0], /Unconfirmed physical availability/);
  assert.equal(object.availability, undefined);
});
test('physical declarations reach the same shooting guide as actor cues', () => {
  const object = createSceneObject(asset, 'Chair', uuid); object.availability = 'virtual_only';
  const program = {title: 'Test', document_digest: 'hash', scenes: [{scene_id: 's', objects: [object]}],
    segments: [{kind: 'shot', scene_id: 's', index: 0, edit: {start_ms: 0, end_ms: 1000}, setup_s: 0, filming_s: 1}]};
  assert.match(shootingGuide(program), /Visualization only - not on location/);
  assert.ok(shootingGuide(program).includes(asset.id));
});

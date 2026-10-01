import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ResourceCache, LoadEpoch} from '../dist/asset-library/lifecycle.mjs';

test('concurrent requests share one load and reference-count releases', async () => {
  let calls = 0;
  const cache = new ResourceCache();
  const load = async () => { calls++; return {id: 1}; };
  const [a,b] = await Promise.all([cache.acquire('a',10,load),cache.acquire('a',10,load)]);
  assert.equal(calls,1); assert.equal(a.value,b.value);
  a.release(); a.release(); assert.equal(cache.entries.get('a').refs,1);
  b.release(); assert.equal(cache.entries.get('a').refs,0);
});
test('evicts only idle sources in least-recently-used order', async () => {
  const disposed=[];
  const cache=new ResourceCache({maxEntries:2,maxBytes:20,dispose:value=>disposed.push(value)});
  const a=await cache.acquire('a',10,()=> 'A'); a.release();
  const b=await cache.acquire('b',10,()=> 'B');
  const c=await cache.acquire('c',10,()=> 'C');
  assert.deepEqual(disposed,['A']); assert.equal(cache.bytes,20);
  b.release();c.release();cache.clearIdle();assert.equal(cache.entries.size,0);
});
test('cannot evict active models to meet a byte budget', async () => {
  const cache=new ResourceCache({maxBytes:10});
  const a=await cache.acquire('a',10,()=> 'A');
  await assert.rejects(cache.acquire('b',1,()=> 'B'),/budget/);
  assert.equal(cache.entries.get('a').refs,1); a.release();
});
test('failed fetches do not poison subsequent attempts', async () => {
  const cache=new ResourceCache();
  await assert.rejects(cache.acquire('a',10,()=> {throw new Error('offline');}),/offline/);
  assert.equal(cache.entries.size,0);
  const value=await cache.acquire('a',10,()=> 'OK');assert.equal(value.value,'OK');value.release();
});
test('pending load is never disposed while an instance awaits it', async () => {
  let finish;const disposed=[];
  const cache=new ResourceCache({dispose:value=>disposed.push(value)});
  const pending=cache.acquire('a',10,()=>new Promise(resolve=>{finish=resolve;}));
  await Promise.resolve();cache.clearIdle();assert.deepEqual(disposed,[]);
  finish('A');const lease=await pending;lease.release();cache.clearIdle();assert.deepEqual(disposed,['A']);
});
test('rejects unknown or nonsensical source byte sizes', async () => {
  const cache=new ResourceCache();
  for (const size of [NaN,Infinity,0,-1]) await assert.rejects(cache.acquire('a',size,()=> 'A'),/budget/);
});
test('scene epochs invalidate old asynchronous completions', () => {
  const epoch=new LoadEpoch();const first=epoch.advance();assert.equal(epoch.current(first),true);
  const second=epoch.advance();assert.equal(epoch.current(first),false);assert.equal(epoch.current(second),true);
});

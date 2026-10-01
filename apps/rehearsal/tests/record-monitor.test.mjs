import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { attachMonitorVideo, monitorDevices } from '../dist/record-monitor.js';

function fixture({ ready = false, fail = false } = {}) {
  const video = new EventTarget();
  Object.assign(video, {readyState:ready ? 2 : 0,videoWidth:ready ? 640 : 0,videoHeight:ready ? 360 : 0,
    play:async () => {if(fail)throw new Error('Playback blocked');}});
  const track = {label:'Live Streamer CAM 313',stop:()=>{throw new Error('Must not stop shared camera');}};
  const events=[]; let timeout;
  const cleanup=attachMonitorVideo(video,track,{
    onReady:()=>events.push('ready'),onError:error=>events.push(error),
    makeStream:value=>({track:value}),schedule:callback=>{timeout=callback;return 1;},cancel:()=>{},
  });
  return {video,track,events,cleanup,timeout:()=>timeout()};
}

test('cart camera is selectable as witness but cannot impersonate the iPhone feed', () => {
  const devices=[{label:'Live Streamer CAM 313'},{label:'Galaxy S23'},{label:'HDMI capture'}];
  assert.deepEqual(monitorDevices(devices,'witness_camera'),devices);
  assert.deepEqual(monitorDevices(devices,'phone_lens_feed'),[devices[2]]);
});

test('an opened track is attached but does not hide the empty state without frames', async () => {
  const f=fixture(); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.video.srcObject.track,f.track);
  assert.deepEqual(f.events,[]);
  f.timeout(); assert.match(f.events[0],/no video frames arrived/);
});

test('already flowing shared camera is displayed and cleaned up without stopping its track', async () => {
  const f=fixture({ready:true}); await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(f.events,['ready']);
  f.cleanup(); assert.equal(f.video.srcObject,null);
});

test('late frames can recover after a no-frame error', () => {
  const f=fixture();f.timeout();
  Object.assign(f.video,{readyState:2,videoWidth:640,videoHeight:360});
  f.video.dispatchEvent(new Event('loadeddata'));
  assert.equal(f.events.at(-1),'ready');
  f.cleanup();
});

test('playback rejection is visible instead of swallowed', async () => {
  const f=fixture({fail:true});await new Promise(resolve=>setImmediate(resolve));
  assert.match(f.events[0],/Playback blocked/);f.cleanup();
});

test('old track callbacks cannot overwrite a replaced monitor', async () => {
  const f=fixture({fail:true});f.cleanup();f.timeout();
  f.video.dispatchEvent(new Event('playing'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(f.events,[]);
});

test('record controls precede the monitors and shot list in document order', async () => {
  const html=await readFile(new URL('../dist/record.html',import.meta.url),'utf8');
  assert.ok(html.indexOf('id="transportButton"') < html.indexOf('id="monitorFrame"'));
  assert.ok(html.indexOf('id="transportButton"') < html.indexOf('id="scenesPanel"'));
  assert.equal((html.match(/id="transportButton"/g)||[]).length,1);
  assert.match(html,/moves the robot and records the iPhone for the selected shot only/);
  assert.match(html,/id="reconnectRecorder"/);
});

test('Record attaches a shared live track and exposes the actual playback error', async () => {
  const js=await readFile(new URL('../dist/record.js',import.meta.url),'utf8');
  assert.match(js,/attachRecordMonitor\(monitorCamera.track\)/);
  assert.match(js,/cameraState: view.monitorReady/);
  assert.doesNotMatch(js,/video.play\(\).catch\(\(\) => \{\}\)/);
  assert.match(js,/view.recording\?\.error/);
  assert.match(js,/Reconnecting does not start a take/);
});

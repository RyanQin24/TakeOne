/* One camera, reference counted, with permission denial as a state. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { CAMERA_STATES, MonitorCamera } from '../dist/camera-source.js';

class FakeTrack {
  constructor(label = 'Rig camera') {
    this.label = label;
    this.readyState = 'live';
    this.stopped = 0;
  }
  addEventListener() {}
  stop() {
    this.stopped += 1;
    this.readyState = 'ended';
  }
}

class FakeStream {
  constructor(track) {
    this.track = track;
  }
  getVideoTracks() {
    return [this.track];
  }
  getTracks() {
    return [this.track];
  }
}

function camera({ fail = null, loops = [] } = {}) {
  const track = new FakeTrack();
  let opens = 0;
  const instance = new MonitorCamera({
    getUserMedia: async () => {
      opens += 1;
      if (fail) throw fail;
      return new FakeStream(track);
    },
    loadConfig: async () => ({ target_fps: 15 }),
    makeLoop: options => {
      const loop = { options, started: 0, stopped: 0, start: async () => { loop.started += 1; }, stop: () => { loop.stopped += 1; } };
      loops.push(loop);
      return loop;
    },
  });
  return { instance, track, loops, opens: () => opens };
}

test('the five camera states are the whole vocabulary', () => {
  assert.deepEqual(CAMERA_STATES, ['idle', 'starting', 'live', 'denied', 'unavailable']);
});

test('two consumers share one stream and the last one out stops it', async () => {
  const { instance, track, opens } = camera();
  const first = await instance.acquire('record');
  const second = await instance.acquire('voice-live');
  assert.equal(first, second);
  assert.equal(opens(), 1, 'the device is opened once');
  assert.equal(instance.state, 'live');
  instance.release('record');
  assert.equal(track.stopped, 0, 'a remaining consumer keeps the camera open');
  assert.equal(instance.state, 'live');
  instance.release('voice-live');
  assert.equal(track.stopped, 1);
  assert.equal(instance.state, 'idle');
});

test('concurrent acquires do not open two devices', async () => {
  const { instance, opens } = camera();
  const [a, b] = await Promise.all([instance.acquire('record'), instance.acquire('voice-live')]);
  assert.equal(a, b);
  assert.equal(opens(), 1);
});

test('one perception loop serves every reader', async () => {
  const loops = [];
  const { instance } = camera({ loops });
  await instance.acquire('record');
  await instance.startPerception({});
  await instance.startPerception({});
  assert.equal(loops.length, 1, 'exactly one inference loop');

  const seen = [];
  instance.subscribe(reading => seen.push(reading));
  instance.subscribe(reading => seen.push(reading));
  let published = 0;
  instance.setPublisher(async () => {
    published += 1;
    return { state: { people: [] }, behavior: null };
  });
  await loops[0].options.channel.publish([], 1);
  assert.equal(published, 1, 'one inference is published upstream once');
  assert.equal(seen.length, 2, 'every subscriber reads the same result');

  instance.release('record');
  assert.equal(loops[0].stopped, 1);
});

test('a denied camera is a state, not an exception that tears anything down', async () => {
  const denied = Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' });
  const { instance } = camera({ fail: denied });
  await assert.rejects(() => instance.acquire('record'));
  assert.equal(instance.state, 'denied');
  assert.equal(instance.status().consumers, 0);
  assert.equal(instance.deviceLabel(), null);
});

test('any other failure is unavailable rather than denied', async () => {
  const { instance } = camera({ fail: new Error('No such device') });
  await assert.rejects(() => instance.acquire('record'));
  assert.equal(instance.state, 'unavailable');
});

test('the caption names the real device', async () => {
  const { instance } = camera();
  await instance.acquire('record');
  assert.equal(instance.deviceLabel(), 'Rig camera');
});

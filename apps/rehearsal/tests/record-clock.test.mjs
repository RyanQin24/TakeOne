import test from 'node:test';
import assert from 'node:assert/strict';
import { elapsedTakeSeconds } from '../dist/record-clock.js';

test('record timecode subtracts monotonic stamps before crossing clock domains', () => {
  const take = {state:'recording', events:[{kind:'start_acknowledged', ack_monotonic_ns:'8200000000000000'}]};
  assert.equal(elapsedTakeSeconds(take, '8200002500000000', 400, 900), 3);
  take.events.push({kind:'stop_acknowledged', ack_monotonic_ns:'8200004000000000'});
  take.state = 'ready';
  assert.equal(elapsedTakeSeconds(take, '8200090000000000', 400, 90000), 4);
});

test('record timecode stays zero before a measured start', () => {
  assert.equal(elapsedTakeSeconds({state:'starting', events:[]}, '1000000000', 0, 500), 0);
});

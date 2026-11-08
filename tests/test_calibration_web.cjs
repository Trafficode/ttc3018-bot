// Service state/leases use simulated HTTP only, with no physical CNC access.
const assert = require('node:assert/strict');

(async () => {
  const {createController} = await import('../ui/src/controller.js');
  const posts = [];
  const timers = new Map();
  let timerId = 0;
  const clock = {setTimeout(callback, delay) {timers.set(++timerId, {callback, delay});return timerId;},clearTimeout(id) {timers.delete(id);}};
  const state = {control_token: 'fixture-only', cnc: {
    connected: true, fresh: true, state: 'Idle', position: [2,3,1],
    job: {id: 'production', state: 'ready'},
    z_probe: {state: 'idle', active: false},
    calibration: {session: 'service', map: {id: 'map', valid: false}, job: {state: 'empty'}},
  }};
  const fetcher = async (url, options = {}) => {
    if (options.method === 'POST') {
      const payload = JSON.parse(options.body);
      posts.push(payload);
      if (payload.action === 'service_prepare') {
        state.cnc.z_probe = {kind: 'calibration', state: 'xy_wait', active: true, completed: 2, total: 5};
        return {ok: true, json: async () => ({probe_lease: 'probe-only'})};
      }
      if (payload.action === 'service_cut') {
        state.cnc.calibration.job = {id: 'trial', state: 'running'};
        return {ok: true, json: async () => ({lease:'trial-owner'})};
      }
      return {ok: true, json: async () => ({})};
    }
    return {ok: true, json: async () => structuredClone(state)};
  };
  const controller = createController(fetcher, clock);
  await controller.refresh();
  assert.equal(posts.length, 0, 'polling must never start a service action');
  await controller.send({action: 'service_prepare'});
  assert.equal(controller.probing.value, true);
  assert.equal(controller.manualReady.value, false);
  assert.match(controller.notice.value.text, /2 \/ 5/);
  state.cnc.z_probe = {kind: 'calibration', state: 'completed', active: false};
  state.cnc.calibration.map.valid = true;
  await controller.refresh();
  assert.equal(controller.manualReady.value, true);
  assert.match(controller.notice.value.text, /Mapa Z gotowa/);
  assert.equal(posts.filter(v => v.action === 'service_cut').length, 0);
  const before = controller.snapshot();
  state.cnc.calibration.session = 'changed';
  assert.equal(await controller.confirmedSend({action:'service_cut'}, before, () => true), false);
  assert.equal(posts.filter(v => v.action === 'service_cut').length, 0);
  await controller.send({action:'service_cut'});
  assert.equal(controller.job.value.id, 'trial');
  assert.equal(controller.manualReady.value, false);
  controller.start();
  await new Promise(resolve => setImmediate(resolve));
  assert(posts.some(v => v.action === 'job_heartbeat' && v.lease === 'trial-owner'), 'service lease must survive status refresh while production file is only ready');
  const beforeObserver = posts.length;
  const observer = createController(fetcher, clock);
  observer.start();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(posts.length, beforeObserver, 'an observer must not renew another service session');
  observer.stop();
  await controller.send({action:'job_stop'}, true);
  assert.equal(posts.at(-1).action, 'job_stop');
  state.cnc.calibration.job.state = 'completed';
  await controller.refresh();
  assert.equal(controller.job.value.id, 'production');
  assert.equal(controller.manualReady.value, true);
  controller.stop();
  console.log('Service UI: passive polling, five-point progress, no auto-cut, stale-session guard, owner heartbeat, exclusive trial and global Stop: PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});

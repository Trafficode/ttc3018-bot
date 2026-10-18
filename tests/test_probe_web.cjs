const assert = require('node:assert/strict');

(async () => {
  const {createController} = await import('../ui/src/controller.js');
  const timers = new Map(); let timerId = 0;
  const clock = {setTimeout(callback, delay) {timers.set(++timerId, {callback, delay}); return timerId;}, clearTimeout(id) {timers.delete(id);}};
  const actions = [];
  const status = {control_token:'test-only', cnc:{connected:true, fresh:true, state:'Idle', position:[0,0,1], probe_triggered:false, probe_tested:true, job:{id:'file',state:'ready'},z_probe:{state:'idle',active:false}}};
  const fetcher = async (url, options = {}) => {
    const payload = options.body ? JSON.parse(options.body) : null;
    let result = {};
    if (payload) {
      actions.push(payload);
      if (payload.action === 'probe_start') {
        status.cnc.z_probe = {state:'starting',active:true};
        result.probe_lease = 'owner-only';
      }
    }
    return {ok:true,json:async()=>JSON.parse(JSON.stringify(payload ? result : status))};
  };
  const owner = createController(fetcher, clock);
  owner.start();
  await new Promise(resolve=>setImmediate(resolve));
  await owner.confirmedSend({action:'probe_start',confirmed:true},owner.snapshot(),()=>owner.manualReady.value);
  assert.equal(owner.probing.value,true);
  assert.equal(owner.active.value,true);
  assert.equal(owner.manualReady.value,false);
  assert.equal(owner.connectReady.value,false);
  assert.match(owner.notice.value.text,/sondowanie aktywne/);
  const [heartbeatId, heartbeat] = [...timers].find(([,timer])=>timer.delay===2000);
  timers.delete(heartbeatId); await heartbeat.callback();
  assert(actions.some(payload=>payload.action==='probe_heartbeat'&&payload.lease==='owner-only'));
  owner.stop();
  const observer = createController(fetcher, clock);
  const before = actions.length;
  observer.start(); await new Promise(resolve=>setImmediate(resolve));
  const [observerId, observerHeartbeat] = [...timers].find(([,timer])=>timer.delay===2000);
  timers.delete(observerId); await observerHeartbeat.callback();
  assert.equal(actions.length,before,'An observer must never renew another probe');
  observer.stop();
  status.cnc.z_probe = {state:'completed',active:false};
  await owner.refresh();
  assert.equal(owner.manualReady.value,true);
  assert.match(owner.notice.value.text,/Zero Z ustawione sondą/);
  status.cnc.z_probe = {state:'failed',active:false,error:'Probe lost'};
  await owner.refresh();
  assert.match(owner.notice.value.text,/Probe lost/);
  owner.acknowledge();
  await owner.refresh();
  assert.doesNotMatch(owner.notice.value.text,/Probe lost/);
  console.log('Probe UI controller: ownership, heartbeat, command guards, completion and persistent errors: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});

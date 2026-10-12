// Exercise operator connection states with simulated HTTP and DOM, never USB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: '', disabled: false, className: '', listeners: {},
    addEventListener(event, callback) { this.listeners[event] = callback; },
    removeAttribute() {},
    focus() {},
    showModal() { this.open = true; },
    close(value) { this.open = false; this.returnValue = value; this.listeners.close?.(); },
  });
  return elements.get(id);
}
const manual = element('manual');
let status = {
  control_token: 'test-only',
  cnc: {connected: false, fresh: false, state: null, position: null},
  camera: {ok: false}, environment: {ok: false},
};
let offline = false;
let releaseAction;
let heldAction = false;
let rejectedAction = false;
const actions = [];
const context = vm.createContext({
  document: {
    getElementById: element,
    querySelectorAll: selector => selector === '[data-manual]' ? [manual] : [],
    querySelector: () => ({value: '0.1'}),
  },
  AbortSignal, Date, Number, Array, Error,
  setTimeout() {}, // Do not run background polling in this test.
  clearTimeout() {},
  confirm: () => { throw new Error('Native confirmation must never be used'); },
  fetch: async (url, options = {}) => {
    if (offline) throw new Error('offline');
    if (options.method === 'POST') {
      const action = JSON.parse(options.body).action;
      actions.push(action);
      if (heldAction) await new Promise(resolve => { releaseAction = resolve; });
      if (rejectedAction) return {ok: false, json: async () => ({error: 'Test controller error'})};
      if (action === 'connect') status.cnc = {connected: true, fresh: true, state: 'Idle', position: [1, 2, 3]};
      if (action === 'disconnect') status.cnc = {connected: false, fresh: false, state: null, position: null};
      return {ok: true, json: async () => ({ok: true})};
    }
    return {ok: true, json: async () => status};
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);
const run = code => vm.runInContext(code, context);

(async () => {
  await run('refresh()');
  assert.equal(element('connect-cnc').textContent, 'Połącz CNC');
  assert.equal(element('connect-cnc').disabled, false);
  assert.equal(manual.disabled, true);
  heldAction = true;
  const connecting = run('sendAction({action: "connect"})');
  assert.equal(element('connect-cnc').textContent, 'Łączenie…');
  assert.equal(element('connect-cnc').disabled, true);
  releaseAction();
  await connecting;
  assert.equal(element('connect-cnc').textContent, 'Rozłącz CNC');
  assert.equal(manual.disabled, false);
  status.cnc.fresh = false;
  status.cnc.state = null;
  status.cnc.position = null;
  await run('refresh()');
  assert.equal(element('connect-cnc').textContent, 'Rozłącz CNC');
  assert.equal(element('connect-cnc').disabled, true);
  assert.equal(manual.disabled, true);
  offline = true;
  await run('refresh()');
  assert.equal(element('connect-cnc').textContent, 'Stan CNC nieznany');
  assert.equal(element('connect-cnc').disabled, true);
  assert.equal(element('position-X').textContent, '—');
  element('connect-cnc').listeners.click();
  assert.deepEqual(actions, ['connect']);
  offline = false;
  status.cnc = {connected: true, fresh: true, state: 'Run', position: [1, 2, 3]};
  await run('refresh()');
  assert.equal(element('connect-cnc').disabled, true);
  status.cnc.state = 'Idle';
  await run('refresh()');
  const disconnecting = run('sendAction({action: "disconnect"})');
  assert.equal(element('connect-cnc').textContent, 'Rozłączanie…');
  releaseAction();
  await disconnecting;
  assert.equal(element('connect-cnc').textContent, 'Połącz CNC');
  assert.equal(element('position-X').textContent, '—');
  assert.equal(manual.disabled, true);
  status.cnc.job = {id: 'job1', state: 'ready', name: 'sample.nc', total: 9, acknowledged: 0};
  await run('refresh()');
  assert.equal(element('job-file').disabled, false);
  assert.equal(element('job-start').disabled, true);
  status.cnc.connected = true;
  status.cnc.fresh = true;
  status.cnc.state = 'Idle';
  await run('refresh()');
  assert.equal(element('job-start').disabled, false);
  status.cnc.job.state = 'running';
  await run('refresh()');
  assert.equal(element('job-file').disabled, true);
  assert.equal(element('job-start').disabled, true);
  assert.equal(element('job-pause').disabled, false);
  assert.equal(element('job-stop').disabled, false);
  assert.equal(element('connect-cnc').disabled, true);
  assert.equal(manual.disabled, true);
  status.cnc.job.state = 'paused';
  await run('refresh()');
  assert.equal(element('job-pause').textContent, 'Wznów');
  assert.equal(manual.disabled, true);
  offline = true;
  await run('refresh()');
  assert.equal(element('job-pause').disabled, true);
  assert.equal(element('job-stop').disabled, true);
  assert.match(element('job-status').textContent, /nieznany/);
  assert.equal(element('operator-alert').hidden, false);
  assert.match(element('operator-alert-message').textContent, /Brak odpowiedzi/);

  // Dialog cancellation never sends an action, and stale confirmation cannot start.
  heldAction = false;
  offline = false;
  status.cnc = {connected: true, fresh: true, state: 'Idle', position: [1, 2, 3],
    job: {id: 'job-a', state: 'ready', name: '<unsafe>.nc', total: 9}};
  await run('refresh()');
  const before = actions.length;
  const cancelled = element('job-start').listeners.click();
  assert.equal(element('action-dialog').open, true);
  assert.match(element('dialog-description').textContent, /<unsafe>\.nc/);
  assert.equal(actions.length, before);
  element('dialog-cancel').listeners.click();
  await cancelled;
  assert.equal(actions.length, before);
  const escaped = element('job-start').listeners.click();
  element('action-dialog').listeners.cancel({preventDefault() {}});
  await escaped;
  assert.equal(actions.length, before);
  const stale = element('job-start').listeners.click();
  status.cnc.job.id = 'job-b';
  element('dialog-confirm').listeners.click();
  await stale;
  assert.equal(actions.length, before);
  assert.match(element('operator-alert-message').textContent, /zmienił się/);
  const moved = element('job-start').listeners.click();
  status.cnc.position = [4, 2, 3];
  element('dialog-confirm').listeners.click();
  await moved;
  assert.equal(actions.length, before);
  const started = element('job-start').listeners.click();
  element('dialog-confirm').listeners.click();
  await started;
  assert.equal(actions.at(-1), 'job_start');

  // Pausing and stopping do not open a dialog; a resume dialog exposes Stop.
  status.cnc.job.state = 'running';
  await run('refresh()');
  await element('job-pause').listeners.click();
  assert.equal(actions.at(-1), 'job_pause');
  assert.equal(element('action-dialog').open, false);
  status.cnc.job.state = 'paused';
  await run('refresh()');
  const resuming = element('job-pause').listeners.click();
  assert.equal(element('dialog-stop').hidden, false);
  element('dialog-stop').listeners.click();
  await resuming;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(actions.at(-1), 'job_stop');
  assert.equal(actions.includes('job_resume'), false);
  await element('job-stop').listeners.click();
  assert.equal(actions.at(-1), 'job_stop');
  assert.equal(element('action-dialog').open, false);

  // Action errors survive successful status polling and require acknowledgement.
  rejectedAction = true;
  await run('sendAction({action: "job_pause"})');
  rejectedAction = false;
  await run('refresh()');
  assert.match(element('operator-alert-message').textContent, /Test controller error/);
  element('dismiss-action-error').listeners.click();
  assert.doesNotMatch(element('operator-alert-message').textContent, /Test controller error/);
  console.log('Connection/job states, dialog cancellation/staleness, immediate Stop/Pause and persistent errors passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });

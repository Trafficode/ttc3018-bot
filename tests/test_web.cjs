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
const actions = [];
const context = vm.createContext({
  document: {
    getElementById: element,
    querySelectorAll: selector => selector === '[data-manual]' ? [manual] : [],
    querySelector: () => ({value: '0.1'}),
  },
  AbortSignal, Date, Number, Array, Error,
  setTimeout() {}, // Do not run background polling in this test.
  confirm: () => true,
  fetch: async (url, options = {}) => {
    if (offline) throw new Error('offline');
    if (options.method === 'POST') {
      const action = JSON.parse(options.body).action;
      actions.push(action);
      if (heldAction) await new Promise(resolve => { releaseAction = resolve; });
      status.cnc = action === 'connect'
        ? {connected: true, fresh: true, state: 'Idle', position: [1, 2, 3]}
        : {connected: false, fresh: false, state: null, position: null};
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
  console.log('Connection and job ready/running/paused/offline UI states passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });

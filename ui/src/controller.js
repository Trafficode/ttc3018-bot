import {signal, computed} from '@preact/signals';

export const activeStates = ['running', 'draining', 'pausing', 'paused', 'resuming'];
export function createController(fetcher = fetch, clock = globalThis) {
  const data = signal(null);
  const offline = signal(true);
  const attempted = signal(false);
  const pending = signal(null);
  const actionError = signal('');
  const latest = signal('');
  const events = signal([]);
  const stopEpoch = signal(0);
  const acknowledgedStop = signal(-1);
  const cnc = computed(() => data.value?.cnc || {});
  const job = computed(() => cnc.value.job || {state: 'empty'});
  const active = computed(() => activeStates.includes(job.value.state));
  const known = computed(() => !!data.value && !offline.value);
  const manualReady = computed(() => known.value && cnc.value.connected && cnc.value.fresh && cnc.value.state === 'Idle' && !active.value && !pending.value);
  const connectReady = computed(() => known.value && !active.value && !pending.value && (!cnc.value.connected || (cnc.value.fresh && cnc.value.state === 'Idle')));
  let lease = null;
  let running = false;
  let pollTimer;
  let heartbeatTimer;
  let messageTimer;
  let refreshing = null;
  let lastCondition = '';
  let wasConnected = false;
  let intentionalDisconnect = false;
  let connectionLost = false;
  const requests = new Map();
  const record = text => { events.value = [{text, time: new Date().toLocaleTimeString('pl-PL')}, ...events.value].slice(0, 20); };
  const info = text => {
    record(text); latest.value = text;
    clock.clearTimeout(messageTimer);
    messageTimer = clock.setTimeout(() => { latest.value = ''; }, 6000);
  };
  const error = text => { actionError.value = text; record(text); };
  const notice = computed(() => {
    if (offline.value) return {tone: attempted.value ? 'error' : 'info', text: attempted.value ? 'Brak odpowiedzi panelu. Stan CNC nieznany — sprawdź maszynę.' : 'Łączenie z panelem stanowiska…'};
    if (cnc.value.connected && !cnc.value.fresh) return {tone: 'error', text: 'Brak aktualnego odczytu CNC. Sprawdź maszynę; sterowanie jest zablokowane.'};
    if (cnc.value.state === 'Alarm') return {tone: 'error', text: 'Sterownik zgłasza alarm. Sprawdź maszynę i wrzeciono.'};
    if (job.value.state === 'failed') return {tone: 'error', text: job.value.error || 'Błąd programu. Sprawdź maszynę; nie ponawiaj poleceń w ciemno.'};
    if (actionError.value) return {tone: 'error', text: actionError.value, dismissible: true};
    if (job.value.state === 'stopped' && acknowledgedStop.value !== stopEpoch.value) return {tone: 'warning', text: 'Program przerwany. Sprawdź wrzeciono, połączenie i zero materiału.', dismissible: true};
    if (connectionLost && !cnc.value.connected) return {tone: 'error', text: 'Utracono połączenie CNC. Sprawdź maszynę i wrzeciono.'};
    if (pending.value) return {tone: 'info', text: 'Oczekiwanie na potwierdzenie polecenia przez sterownik…'};
    if (active.value) return {tone: job.value.state === 'paused' ? 'warning' : 'info', text: job.value.state === 'paused' ? 'Program wstrzymany. Wrzeciono może nadal pracować.' : 'Program aktywny. Pozostań przy stanowisku.'};
    if (latest.value) return {tone: 'success', text: latest.value};
    return {tone: cnc.value.connected ? 'success' : 'info', text: cnc.value.connected ? 'CNC połączone. Ruch wymaga Twojego polecenia.' : 'CNC rozłączone. Połącz sterownik przy stanowisku.'};
  });

  async function refresh(force = false) {
    if (refreshing) { await refreshing; if (!force) return; }
    refreshing = (async () => {
      try {
        const response = await fetcher('/api/status', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
        if (!response.ok) throw new Error('Brak odpowiedzi');
        const next = await response.json();
        const oldJob = job.value;
        if (next.cnc.job?.state === 'stopped' && (oldJob.state !== 'stopped' || oldJob.id !== next.cnc.job.id)) stopEpoch.value++;
        connectionLost = next.cnc.connected ? false : (connectionLost || (wasConnected && !intentionalDisconnect));
        wasConnected = next.cnc.connected;
        if (intentionalDisconnect && !next.cnc.connected) connectionLost = false;
        intentionalDisconnect = false;
        data.value = next;
        offline.value = false;
        if (!activeStates.includes(next.cnc.job?.state)) lease = null;
        if (next.cnc.job?.state === 'completed' && activeStates.includes(oldJob.state)) info('Program zakończony. Sterownik zgłasza bezczynność.');
        const condition = [next.cnc.state === 'Alarm' ? 'Alarm CNC' : '', next.cnc.job?.error || ''].filter(Boolean).join(' · ');
        if (condition && condition !== lastCondition) record(condition);
        lastCondition = condition;
      } catch { offline.value = true; }
      finally { attempted.value = true; }
    })();
    try { await refreshing; } finally { refreshing = null; }
  }

  async function send(payload, urgent = false) {
    if ((!urgent && pending.value) || !known.value || !data.value?.control_token) return false;
    const action = payload.action;
    const requestId = Symbol(action);
    requests.set(requestId, action);
    pending.value = action;
    try {
      const response = await fetcher('/api/cnc/action', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PiloMill-Token': data.value.control_token}, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Błąd sterownika');
      if (result.lease) lease = result.lease;
      intentionalDisconnect = ['disconnect', 'job_stop'].includes(action);
      const messages = {connect: 'CNC połączone.', disconnect: 'CNC rozłączone przez operatora.', zero_xy: 'Zero X/Y ustawione.', zero_z: 'Zero Z ustawione.', job_load: 'Plik sprawdzony. Start wymaga potwierdzenia.', job_clear: 'Plik usunięty.', job_start: 'Uruchomienie programu zlecone.', job_pause: 'Pauza zlecona.', job_resume: 'Wznowienie zlecone.', job_stop: 'Przerwanie programu zlecone.', spindle_on: 'Polecenie włączenia wrzeciona przyjęte.', spindle_off: 'Polecenie wyłączenia wrzeciona przyjęte.'};
      if (messages[action]) info(messages[action]);
      return true;
    } catch (cause) { error(`${cause.message}. Sprawdź maszynę; nie ponawiaj polecenia w ciemno.`); return false; }
    finally { requests.delete(requestId); pending.value = [...requests.values()].at(-1) || null; await refresh(); }
  }

  // Only explicit UI confirmation calls this. Polling and mounting never execute actions.
  function snapshot() { return JSON.stringify([cnc.value.connected, cnc.value.position, job.value.id]); }
  async function confirmedSend(payload, before, valid) {
    await refresh(true);
    if (!known.value || pending.value || snapshot() !== before || !valid()) {
      error('Stan CNC, pozycja lub plik zmieniły się. Polecenie nie zostało wysłane.'); return false;
    }
    return send(payload);
  }
  async function heartbeat() {
    if (lease && active.value && data.value?.control_token) {
      try { await fetcher('/api/cnc/action', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PiloMill-Token': data.value.control_token}, body: JSON.stringify({action: 'job_heartbeat', lease}), signal: AbortSignal.timeout(2000)}); } catch { /* RPi expires the lease and requests hold. */ }
    }
    if (running) heartbeatTimer = clock.setTimeout(heartbeat, 2000);
  }
  async function poll() { await refresh(); if (running) pollTimer = clock.setTimeout(poll, 3000); }
  function start() { if (running) return; running = true; poll(); heartbeat(); }
  function stop() { running = false; clock.clearTimeout(pollTimer); clock.clearTimeout(heartbeatTimer); clock.clearTimeout(messageTimer); }
  function acknowledge() {
    if (actionError.value) actionError.value = '';
    else if (job.value.state === 'stopped') {acknowledgedStop.value = stopEpoch.value; latest.value = '';}
  }
  return {data, cnc, job, active, known, manualReady, connectReady, pending, offline, notice, events, refresh, send, snapshot, confirmedSend, info, error, start, stop, acknowledge};
}

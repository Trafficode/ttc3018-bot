const temperature = document.getElementById('temperature');
const humidity = document.getElementById('humidity');
const sensorStatus = document.getElementById('sensor-status');
const cameraStatus = document.getElementById('camera-status');
const camera = document.getElementById('camera');
const toggle = document.getElementById('toggle');
const monitorBadge = document.getElementById('monitor-badge');
let paused = false;
let streamActive = false;
let controlToken = null;
let cncConnected = false;
let cncIdle = false;
let cncFresh = false;
let cncKnown = false;
let cncPosition = null;
let pendingAction = null;
let actionPending = false;
let actionMessage = '';
const cncBadge = document.getElementById('cnc-badge');
const cncStatus = document.getElementById('cnc-status');
const connectButton = document.getElementById('connect-cnc');
let job = {state: 'empty'};
let jobLease = null;
const activeJobStates = ['running', 'draining', 'pausing', 'paused', 'resuming'];
const jobFile = document.getElementById('job-file');
const jobStart = document.getElementById('job-start');
const jobPause = document.getElementById('job-pause');
const jobStop = document.getElementById('job-stop');
const actionDialog = document.getElementById('action-dialog');
const dialogCancel = document.getElementById('dialog-cancel');
const dialogConfirm = document.getElementById('dialog-confirm');
const dialogStop = document.getElementById('dialog-stop');
const notification = document.getElementById('notification');
let confirmation = null;
let notificationTimer = null;
let intentionalDisconnect = false;
const operatorErrors = {action: '', connection: '', machine: '', server: ''};

function renderErrors() {
  const messages = [...new Set(Object.values(operatorErrors).filter(Boolean))];
  document.getElementById('operator-alert').hidden = messages.length === 0;
  document.getElementById('operator-alert-message').textContent = messages.join('\n');
  document.getElementById('dismiss-action-error').hidden = !operatorErrors.action;
}

document.getElementById('dismiss-action-error').addEventListener('click', () => {
  operatorErrors.action = '';
  renderErrors();
});

function notify(message) {
  clearTimeout(notificationTimer);
  notification.textContent = message;
  notification.hidden = false;
  notificationTimer = setTimeout(() => { notification.hidden = true; }, 6000);
}

function askConfirmation(title, description, label) {
  if (confirmation || actionPending || !controlToken || !cncKnown) return Promise.resolve(false);
  document.getElementById('dialog-title').textContent = title;
  document.getElementById('dialog-description').textContent = description;
  dialogConfirm.textContent = label;
  dialogStop.hidden = !activeJobStates.includes(job.state);
  actionDialog.returnValue = '';
  return new Promise(resolve => {
    confirmation = resolve;
    actionDialog.showModal();
    dialogCancel.focus();
  });
}

actionDialog.addEventListener('close', () => {
  const resolve = confirmation;
  confirmation = null;
  if (resolve) resolve(actionDialog.returnValue === 'confirmed');
});
actionDialog.addEventListener('cancel', event => {
  event.preventDefault();
  actionDialog.close('cancelled');
});
dialogCancel.addEventListener('click', () => actionDialog.close('cancelled'));
dialogConfirm.addEventListener('click', () => actionDialog.close('confirmed'));
dialogStop.addEventListener('click', () => {
  actionDialog.close('cancelled');
  return sendAction({action: 'job_stop'});
});

async function confirmedAction(payload, title, description, label, stillValid) {
  const positionBefore = cncConnected ? JSON.stringify(cncPosition) : null;
  if (!await askConfirmation(title, description, label)) return;
  // A second viewer or a failed poll can change the state while the dialog is open.
  await refresh();
  if (!controlToken || !cncKnown || actionPending || !stillValid()
      || (positionBefore !== null && JSON.stringify(cncPosition) !== positionBefore)) {
    operatorErrors.action = 'Stan CNC lub zadania zmienił się. Polecenie nie zostało wysłane. Sprawdź aktualny stan.';
    renderErrors();
    return;
  }
  await sendAction(payload);
}

function manualReady() {
  return cncConnected && cncFresh && cncIdle && !activeJobStates.includes(job.state);
}

function updateControls() {
  const jobActive = activeJobStates.includes(job.state);
  for (const field of document.querySelectorAll('[data-manual]')) {
    field.disabled = !cncConnected || !cncFresh || !cncIdle || actionPending || jobActive;
  }
  connectButton.textContent = pendingAction === 'connect' ? 'Łączenie…'
    : pendingAction === 'disconnect' ? 'Rozłączanie…'
    : !cncKnown ? 'Stan CNC nieznany'
    : cncConnected ? 'Rozłącz CNC' : 'Połącz CNC';
  connectButton.disabled = !controlToken || !cncKnown || actionPending || jobActive
    || (cncConnected && (!cncFresh || !cncIdle));
  if (pendingAction === 'connect' || pendingAction === 'disconnect') {
    cncBadge.textContent = pendingAction === 'connect' ? 'CNC: łączenie…' : 'CNC: rozłączanie…';
    cncBadge.className = 'badge muted';
  }
  document.getElementById('cancel-jog').disabled = !cncConnected || !cncKnown || actionPending || jobActive;
  jobFile.disabled = !controlToken || !cncKnown || actionPending || jobActive;
  document.getElementById('job-clear').disabled = !job.id || !controlToken || !cncKnown || actionPending || jobActive;
  jobStart.disabled = !job.id || jobActive || !cncConnected || !cncFresh || !cncIdle || actionPending;
  jobPause.textContent = job.state === 'paused' ? 'Wznów' : 'Pauza';
  jobPause.disabled = !controlToken || !cncKnown || actionPending || !['running', 'draining', 'paused'].includes(job.state) || (job.state === 'paused' && !cncFresh);
  jobStop.disabled = !controlToken || !cncKnown || actionPending || !jobActive;
}

document.getElementById('cancel-jog').addEventListener('click', () => sendAction({action: 'jog_cancel'}));

async function sendAction(payload) {
  if (actionPending || !controlToken) return;
  actionPending = true;
  pendingAction = payload.action;
  actionMessage = payload.action === 'connect' ? 'Łączenie ze sterownikiem…'
    : payload.action === 'disconnect' ? 'Rozłączanie CNC…'
    : 'Oczekiwanie na odpowiedź sterownika…';
  cncStatus.textContent = actionMessage;
  updateControls();
  try {
    const response = await fetch('/api/cnc/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-PiloMill-Token': controlToken},
      body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Błąd sterownika');
    if (result.lease) jobLease = result.lease;
    intentionalDisconnect = ['disconnect', 'job_stop'].includes(payload.action);
    actionMessage = payload.action === 'connect' ? 'CNC połączone.'
      : payload.action === 'disconnect' ? 'CNC rozłączone przez operatora.'
      : payload.action === 'job_load' ? 'Plik sprawdzony. Start wymaga Twojego potwierdzenia.'
      : 'Sterownik przyjął polecenie. Sprawdź maszynę i pozycję.';
    const messages = {
      connect: 'CNC połączone.', disconnect: 'CNC rozłączone.',
      zero_xy: 'Zero X/Y ustawione.', zero_z: 'Zero Z ustawione.',
      job_load: 'Plik sprawdzony. Możesz przygotować Start.',
      job_clear: 'Plik usunięty.', job_start: 'Uruchomienie programu zlecone.',
      job_pause: 'Pauza zlecona. Wrzeciono może nadal pracować.',
      job_resume: 'Wznowienie programu zlecone.',
      job_stop: 'Przerwanie zlecone. Sprawdź wrzeciono i ponownie ustaw zero.',
      spindle_on: 'Polecenie włączenia wrzeciona przyjęte.',
      spindle_off: 'Polecenie wyłączenia wrzeciona przyjęte.',
    };
    if (messages[payload.action]) notify(messages[payload.action]);
  } catch (error) {
    actionMessage = `Błąd: ${error.message}. Nie ponawiaj w ciemno — sprawdź maszynę.`;
    operatorErrors.action = actionMessage;
    renderErrors();
  } finally {
    actionPending = false;
    pendingAction = null;
    await refresh();
    updateControls();
  }
}

jobFile.addEventListener('change', async () => {
  const file = jobFile.files?.[0];
  if (!file) return;
  if (file.size > 1024 * 1024) {
    document.getElementById('job-summary').textContent = 'Limit pliku: 1 MiB.';
    operatorErrors.action = 'Nie wczytano pliku. Maksymalny rozmiar to 1 MiB.';
    renderErrors();
    jobFile.value = '';
    return;
  }
  try {
    await sendAction({action: 'job_load', name: file.name, content: await file.text()});
  } catch (error) {
    document.getElementById('job-summary').textContent = `Nie odczytano pliku: ${error.message}`;
    operatorErrors.action = `Nie odczytano pliku: ${error.message}`;
    renderErrors();
  } finally { jobFile.value = ''; }
});
jobStart.addEventListener('click', () => {
  if (jobStart.disabled) return;
  const id = job.id;
  return confirmedAction({action: 'job_start', job_id: id, confirmed: true},
    'Uruchomić program?', `${job.name}\n\nSprawdź narzędzie, zakres programu, mocowania, zero X/Y i Z oraz wysokość przejazdów. Program może włączyć wrzeciono. Pozostań przy maszynie z dostępem do wyłącznika.`,
    'Uruchom program', () => manualReady() && job.id === id);
});
document.getElementById('job-clear').addEventListener('click', () => sendAction({action: 'job_clear'}));
jobPause.addEventListener('click', () => {
  if (jobPause.disabled) return;
  const resume = job.state === 'paused';
  const id = job.id;
  if (resume) return confirmedAction({action: 'job_resume', job_id: id, confirmed: true},
    'Wznowić program?', 'Wznowienie uruchomi ruch narzędzia. Sprawdź maszynę, narzędzie oraz wrzeciono i usuń przedmioty ze strefy pracy.',
    'Wznów program', () => cncConnected && cncFresh && job.state === 'paused' && job.id === id);
  return sendAction({action: 'job_pause', job_id: id});
});
jobStop.addEventListener('click', () => {
  return sendAction({action: 'job_stop'});
});
async function jobHeartbeat() {
  if (jobLease && activeJobStates.includes(job.state)) {
    try {
      await fetch('/api/cnc/action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-PiloMill-Token': controlToken},
        body: JSON.stringify({action: 'job_heartbeat', lease: jobLease}),
        signal: AbortSignal.timeout(2000),
      });
    } catch (_) { /* The RPi pauses the sender when its lease expires. */ }
  }
  setTimeout(jobHeartbeat, 2000);
}
jobHeartbeat();

connectButton.addEventListener('click', () => {
  if (connectButton.disabled || !cncKnown || actionPending) return;
  if (cncConnected) {
    return confirmedAction({action: 'disconnect'}, 'Rozłączyć CNC?',
      'Frezarka musi być bezczynna, a wrzeciono wyłączone. Rozłączenie USB samo nie zatrzymuje wrzeciona.',
      'Rozłącz CNC', manualReady);
  }
  return confirmedAction({action: 'connect'}, 'Połączyć ze sterownikiem?',
    'Upewnij się, że frezarka stoi, wrzeciono jest wyłączone i jesteś przy stanowisku. Otwarcie połączenia USB może zresetować sterownik.',
    'Połącz CNC', () => !cncConnected && !activeJobStates.includes(job.state));
});
for (const button of document.querySelectorAll('[data-axis]')) {
  button.addEventListener('click', () => sendAction({
    action: 'jog', axis: button.dataset.axis,
    distance: Number(document.querySelector('input[name="step"]:checked').value) * Number(button.dataset.direction),
    feed: Number(document.getElementById('jog-feed').value),
  }));
}
for (const button of document.querySelectorAll('[data-action]')) {
  button.addEventListener('click', () => {
    const action = button.dataset.action;
    if (button.disabled) return;
    const payload = {action, power: Number(document.getElementById('spindle-power').value)};
    if (action.startsWith('zero_')) return confirmedAction(payload,
      action === 'zero_z' ? 'Ustawić zero Z?' : 'Ustawić zero X/Y?',
      'Aktualne położenie narzędzia zostanie zapisane jako zero materiału. Polecenie nie przesuwa osi. Dla Z uwzględnij grubość papieru, jeśli był używany.',
      'Ustaw zero', manualReady);
    if (action === 'spindle_on') return confirmedAction(payload, 'Włączyć wrzeciono?',
      `Moc sterownika: ${payload.power} / 1000. Usuń ręce i luźne przedmioty ze strefy pracy.`,
      'Włącz wrzeciono', manualReady);
    return sendAction(payload);
  });
}

const toolTabs = Array.from(document.querySelectorAll('[role="tab"]'));
function selectTool(tab, focus = false) {
  for (const item of toolTabs) {
    const active = item === tab;
    item.setAttribute('aria-selected', String(active));
    item.tabIndex = active ? 0 : -1;
    document.getElementById(item.getAttribute('aria-controls')).hidden = !active;
  }
  if (focus) tab.focus();
}
for (const tab of toolTabs) {
  tab.addEventListener('click', () => selectTool(tab));
  tab.addEventListener('keydown', event => {
    const index = toolTabs.indexOf(tab);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % toolTabs.length;
    else if (event.key === 'ArrowLeft') next = (index + toolTabs.length - 1) % toolTabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = toolTabs.length - 1;
    else return;
    event.preventDefault();
    selectTool(toolTabs[next], true);
  });
}

function stopStream() {
  camera.removeAttribute('src');
  streamActive = false;
}
camera.addEventListener('error', stopStream);
toggle.addEventListener('click', () => {
  paused = !paused;
  toggle.textContent = paused ? 'Wznów podgląd' : 'Wstrzymaj podgląd';
  if (paused) stopStream();
  cameraStatus.textContent = paused ? 'Podgląd wstrzymany.' : 'Wznawianie podglądu…';
});

async function refresh() {
  try {
    const response = await fetch('/api/status', {
      cache: 'no-store', signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error('Brak odpowiedzi serwera');
    const status = await response.json();
    operatorErrors.server = '';
    controlToken = status.control_token;
    const wasConnected = cncConnected;
    const previousJobState = job.state;
    cncConnected = status.cnc.connected;
    cncPosition = status.cnc.position || null;
    cncFresh = status.cnc.fresh === true;
    cncKnown = true;
    cncIdle = cncFresh && status.cnc.state === 'Idle';
    job = status.cnc.job || {state: 'empty'};
    if (job.state === 'completed' && activeJobStates.includes(previousJobState)) notify('Program zakończony. Sterownik zgłasza bezczynność.');
    operatorErrors.connection = cncConnected && !cncFresh
      ? 'Brak aktualnego odczytu CNC. Sterowanie jest zablokowane; sprawdź maszynę.'
      : wasConnected && !cncConnected && !intentionalDisconnect
        ? 'Utracono połączenie ze sterownikiem CNC. Sprawdź maszynę i wrzeciono.'
        : !cncConnected ? operatorErrors.connection : '';
    if (intentionalDisconnect && !cncConnected) operatorErrors.connection = '';
    intentionalDisconnect = false;
    operatorErrors.machine = job.error || (status.cnc.state === 'Alarm' ? 'Sterownik CNC zgłasza alarm. Sprawdź maszynę.' : '');
    renderErrors();
    if (actionDialog.open) dialogStop.hidden = !activeJobStates.includes(job.state);
    const jobNames = {empty: 'Brak zadania', ready: 'Gotowy', running: 'Wykonywanie', draining: 'Oczekiwanie na zakończenie ruchu', pausing: 'Zatrzymywanie posuwu', paused: 'Pauza — wrzeciono może pracować', resuming: 'Wznawianie', completed: 'Zakończono', stopped: 'Przerwano', failed: 'Błąd — sprawdź maszynę'};
    document.getElementById('job-summary').textContent = job.name
      ? `${job.name} · ${job.total} poleceń · F ≤ ${job.max_feed} mm/min · S ≤ ${job.max_power}`
      : 'Wybierz plik. Wgranie nie uruchamia maszyny.';
    document.getElementById('job-bounds').textContent = job.bounds_mm
      ? ['X', 'Y', 'Z'].map(axis => `${axis}: ${job.bounds_mm[axis].map(value => value == null ? '—' : value.toFixed(3)).join(' … ')} mm`).join('\n') : '';
    const progress = document.getElementById('job-progress');
    progress.max = job.total || 1;
    progress.value = job.acknowledged || 0;
    document.getElementById('job-status').textContent = `${jobNames[job.state] || job.state} · przyjęto ${job.acknowledged || 0}/${job.total || 0}${job.source_line ? ` · linia pliku ${job.source_line}` : ''}${job.error ? ` · ${job.error}` : ''}`;
    if (!activeJobStates.includes(job.state)) jobLease = null;
    if (wasConnected && !cncConnected && !actionPending) actionMessage = '';
    const machineStates = {Idle: 'Gotowa', Jog: 'Ruch ręczny', Run: 'Ruch', Alarm: 'Alarm'};
    cncBadge.textContent = cncConnected
      ? `CNC połączone · ${cncFresh ? (machineStates[status.cnc.state] || status.cnc.state) : 'brak aktualnego odczytu'}`
      : 'CNC rozłączone';
    cncBadge.className = cncConnected && cncFresh ? 'badge' : 'badge warning';
    for (const [index, axis] of ['X', 'Y', 'Z'].entries()) {
      const value = status.cnc.position?.[index];
      document.getElementById(`position-${axis}`).textContent = Number.isFinite(value) ? value.toFixed(3) : '—';
    }
    cncStatus.textContent = (actionPending && actionMessage)
      || (!cncConnected && status.cnc.reason)
      || (cncConnected && !cncFresh ? 'Brak aktualnego odczytu — sterowanie zablokowane.' : '')
      || actionMessage || 'Połączono. Ruch wyłącznie po Twoim kliknięciu.';
    updateControls();
    monitorBadge.textContent = status.camera.ok ? 'Kamera działa' : 'Brak obrazu';
    monitorBadge.className = status.camera.ok ? 'badge' : 'badge warning';
    const environment = status.environment;
    temperature.textContent = environment.ok
      ? `${environment.temperature_c.toFixed(1)} °C` : '—';
    humidity.textContent = environment.ok
      ? `${environment.humidity_percent.toFixed(1)} %` : '—';
    sensorStatus.className = environment.ok ? '' : 'warning';
    sensorStatus.textContent = environment.ok
      ? `Odczyt sprzed ${environment.age_seconds.toFixed(1)} s · ${new Date(environment.timestamp).toLocaleTimeString('pl-PL')}`
      : `Czujnik: brak aktualnego odczytu. ${environment.error || ''}`;
    cameraStatus.className = status.camera.ok ? '' : 'warning';
    cameraStatus.textContent = status.camera.ok
      ? (paused ? 'Podgląd wstrzymany przez użytkownika.' : 'Podgląd na żywo · 960 × 540 · 8 kl./s')
      : `Kamera niedostępna. ${status.camera.error || ''}`;
    if (status.camera.ok && !paused && !streamActive) {
      camera.src = `/camera.mjpg?t=${Date.now()}`;
      streamActive = true;
    } else if (!status.camera.ok) {
      stopStream();
    }
  } catch (error) {
    operatorErrors.server = 'Brak odpowiedzi panelu. Stan CNC jest nieznany — sprawdź maszynę. Nie ponawiaj poleceń w ciemno.';
    renderErrors();
    controlToken = null;
    cncKnown = false;
    cncFresh = false;
    cncIdle = false;
    cncPosition = null;
    updateControls();
    cncBadge.textContent = 'CNC: stan nieznany';
    cncBadge.className = 'badge warning';
    cncStatus.textContent = 'Brak odpowiedzi panelu — stan CNC nieznany. Sprawdź maszynę.';
    document.getElementById('job-status').textContent = 'Brak odpowiedzi — stan zadania nieznany. Nie uruchamiaj ponownie w ciemno.';
    for (const axis of ['X', 'Y', 'Z']) document.getElementById(`position-${axis}`).textContent = '—';
    monitorBadge.textContent = 'Brak połączenia';
    monitorBadge.className = 'badge warning';
    temperature.textContent = '—';
    humidity.textContent = '—';
    sensorStatus.className = 'warning';
    sensorStatus.textContent = 'Brak połączenia — wartości nie są aktualne.';
    cameraStatus.textContent = 'Podgląd niedostępny. Sprawdź połączenie Tailscale.';
    stopStream();
  }
}
// Serial polling prevents overlap when the network is slow.
async function poll() {
  await refresh();
  setTimeout(poll, 3000);
}
poll();

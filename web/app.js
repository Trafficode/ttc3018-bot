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
    actionMessage = payload.action === 'connect' ? 'CNC połączone.'
      : payload.action === 'disconnect' ? 'CNC rozłączone przez operatora.'
      : payload.action === 'job_load' ? 'Plik sprawdzony. Start wymaga Twojego potwierdzenia.'
      : 'Sterownik przyjął polecenie. Sprawdź maszynę i pozycję.';
  } catch (error) {
    actionMessage = `Błąd: ${error.message}. Nie ponawiaj w ciemno — sprawdź maszynę.`;
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
    jobFile.value = '';
    return;
  }
  try {
    await sendAction({action: 'job_load', name: file.name, content: await file.text()});
  } catch (error) {
    document.getElementById('job-summary').textContent = `Nie odczytano pliku: ${error.message}`;
  } finally { jobFile.value = ''; }
});
jobStart.addEventListener('click', () => {
  if (confirm(`Uruchomić ${job.name}? Sprawdź narzędzie, zakres programu, mocowania, zero X/Y i Z oraz bezpieczną wysokość. Pozostań przy frezarce z dostępem do wyłącznika.`)) {
    sendAction({action: 'job_start', job_id: job.id, confirmed: true});
  }
});
document.getElementById('job-clear').addEventListener('click', () => sendAction({action: 'job_clear'}));
jobPause.addEventListener('click', () => {
  const resume = job.state === 'paused';
  if (resume && !confirm('Wznowić ruch i wykonywanie programu? Sprawdź maszynę, narzędzie i wrzeciono.')) return;
  sendAction({action: resume ? 'job_resume' : 'job_pause', job_id: job.id, confirmed: resume});
});
jobStop.addEventListener('click', () => {
  sendAction({action: 'job_stop'});
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
  if (!cncKnown || actionPending) return;
  if (cncConnected) {
    if (confirm('Rozłączyć CNC? Frezarka musi być bezczynna, a wrzeciono fizycznie wyłączone. Rozłączenie USB nie zatrzymuje wrzeciona.')) {
      sendAction({action: 'disconnect'});
    }
    return;
  }
  if (confirm('Czy frezarka stoi, wrzeciono jest wyłączone i jesteś przy maszynie? Otwarcie USB może zresetować sterownik.')) {
    sendAction({action: 'connect'});
  }
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
    if (action.startsWith('zero_') && !confirm('Czy narzędzie jest w wybranym punkcie zera materiału? Ta akcja zmienia zero, ale nie przesuwa osi.')) return;
    if (action === 'spindle_on' && !confirm('Uruchomić wrzeciono? Usuń ręce i luźne przedmioty ze strefy pracy.')) return;
    sendAction({action, power: Number(document.getElementById('spindle-power').value)});
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
    controlToken = status.control_token;
    const wasConnected = cncConnected;
    cncConnected = status.cnc.connected;
    cncFresh = status.cnc.fresh === true;
    cncKnown = true;
    cncIdle = cncFresh && status.cnc.state === 'Idle';
    job = status.cnc.job || {state: 'empty'};
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
    controlToken = null;
    cncKnown = false;
    cncFresh = false;
    cncIdle = false;
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

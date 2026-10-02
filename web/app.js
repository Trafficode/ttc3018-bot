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
let actionPending = false;
let actionMessage = '';
const cncBadge = document.getElementById('cnc-badge');
const cncStatus = document.getElementById('cnc-status');
const connectButton = document.getElementById('connect-cnc');

function updateControls() {
  for (const field of document.querySelectorAll('[data-manual]')) {
    field.disabled = !cncConnected || !cncIdle || actionPending;
  }
  connectButton.disabled = !controlToken || cncConnected || actionPending;
  document.getElementById('cancel-jog').disabled = !cncConnected || actionPending;
}

document.getElementById('cancel-jog').addEventListener('click', () => sendAction({action: 'jog_cancel'}));

async function sendAction(payload) {
  if (actionPending || !controlToken) return;
  actionPending = true;
  actionMessage = 'Oczekiwanie na odpowiedź sterownika…';
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
    actionMessage = 'Sterownik przyjął polecenie. Sprawdź maszynę i pozycję.';
  } catch (error) {
    actionMessage = `Błąd: ${error.message}. Nie ponawiaj w ciemno — sprawdź maszynę.`;
  } finally {
    actionPending = false;
    await refresh();
    cncStatus.textContent = actionMessage;
    updateControls();
  }
}

connectButton.addEventListener('click', () => {
  if (confirm('Czy frezarka stoi, wrzeciono jest wyłączone i jesteś przy maszynie? Otwarcie USB może zresetować sterownik.')) {
    sendAction({action: 'connect'});
  }
});
for (const button of document.querySelectorAll('[data-axis]')) {
  button.addEventListener('click', () => sendAction({
    action: 'jog', axis: button.dataset.axis,
    distance: Number(document.getElementById('jog-step').value) * Number(button.dataset.direction),
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
    cncConnected = status.cnc.connected;
    cncIdle = status.cnc.state === 'Idle';
    cncBadge.textContent = cncConnected ? `CNC: ${status.cnc.state}` : 'CNC niepodłączone';
    cncBadge.className = cncConnected ? 'badge' : 'badge warning';
    for (const [index, axis] of ['X', 'Y', 'Z'].entries()) {
      const value = status.cnc.position?.[index];
      document.getElementById(`position-${axis}`).textContent = Number.isFinite(value) ? value.toFixed(3) : '—';
    }
    cncStatus.textContent = actionMessage || status.cnc.reason || 'Połączono. Ruch wyłącznie po Twoim kliknięciu.';
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
    cncConnected = false;
    cncIdle = false;
    updateControls();
    cncBadge.textContent = 'CNC: brak aktualnego odczytu';
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

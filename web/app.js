const temperature = document.getElementById('temperature');
const humidity = document.getElementById('humidity');
const sensorStatus = document.getElementById('sensor-status');
const cameraStatus = document.getElementById('camera-status');
const camera = document.getElementById('camera');
const toggle = document.getElementById('toggle');
const monitorBadge = document.getElementById('monitor-badge');
let paused = false;
let streamActive = false;

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

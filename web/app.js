const temperature = document.getElementById('temperature');
const humidity = document.getElementById('humidity');
const sensorStatus = document.getElementById('sensor-status');
const cameraStatus = document.getElementById('camera-status');
const camera = document.getElementById('camera');
const toggle = document.getElementById('toggle');
let paused = false;
let streamActive = false;

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

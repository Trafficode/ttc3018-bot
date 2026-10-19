import {render} from 'preact';
import {useEffect, useLayoutEffect, useRef, useState} from 'preact/hooks';
import {IconArrowsMaximize, IconArrowsMinimize, IconPlugConnected, IconPlugConnectedX, IconTemperature, IconDroplet, IconInfoCircle, IconAlertTriangle, IconChevronDown, IconChevronUp, IconArrowsMove, IconFocus2, IconFileCode, IconTool, IconPlayerPlay, IconPlayerPause, IconPlayerStop, IconFolder, IconSettings, IconCamera, IconPower} from '@tabler/icons-preact';
import {createController} from './controller.js';
import {SurfaceOverview} from './SurfacePlan.jsx';
import {surfaceMatches} from './surface-plan.js';
import {FilePanel} from './FilePanel.jsx';
import './style.css';
import './probe.css';
import './compact.css';

const controller = createController();
const tabs = [{id: 'move', label: 'Ruch', icon: IconArrowsMove}, {id: 'zero', label: 'Zero', icon: IconFocus2}, {id: 'file', label: 'Plik', icon: IconFileCode}, {id: 'spindle', label: 'Wrzeciono', icon: IconTool}];
const machineNames = {Idle: 'Bezczynne', Run: 'Praca', Jog: 'Ruch ręczny', Alarm: 'Alarm'};
const jobNames = {ready: 'Gotowy plik', running: 'Praca', draining: 'Kończenie ruchu', pausing: 'Zatrzymywanie', paused: 'Pauza', resuming: 'Wznawianie', completed: 'Zakończono', stopped: 'Przerwano', failed: 'Błąd'};

function Button({icon: Icon, children, ...props}) { return <button type="button" {...props}>{Icon && <Icon size={19} aria-hidden="true"/>}<span>{children}</span></button>; }
function Header({onRequest}) {
  const cnc = controller.cnc.value;
  const status = controller.data.value;
  const notice = controller.notice.value;
  const [details, setDetails] = useState(false);
  const badge = !controller.known.value ? 'Stan nieznany' : cnc.connected ? `CNC połączone · ${cnc.fresh ? (machineNames[cnc.state] || cnc.state) : 'brak odczytu'}` : 'CNC rozłączone';
  const Icon = cnc.connected ? IconPlugConnected : IconPlugConnectedX;
  const environment = status?.environment;
  const probeContact = controller.known.value && cnc.connected && cnc.fresh ? cnc.probe_triggered : null;
  const probeLabel = probeContact === true ? 'STYK' : probeContact === false ? 'BRAK STYKU' : 'BRAK ODCZYTU';
  return <header class="topbar">
    <div class="brand"><div><h1>Bark Beetle</h1><span>TTC3018</span></div><span id="cnc-badge" class={`connection ${!controller.known.value || (cnc.connected && !cnc.fresh) ? 'unknown' : cnc.connected ? 'connected' : 'disconnected'}`}><Icon size={20} aria-hidden="true"/>{badge}</span></div>
    <section class="positions" aria-label="Pozycja względem zera materiału"><p>Pozycja (G54)</p><div class="axes">{['X','Y','Z'].map((axis,index) => <div key={axis}><strong>{axis}</strong><output id={`position-${axis}`}>{controller.known.value && cnc.connected && cnc.fresh && Number.isFinite(cnc.position?.[index]) ? cnc.position[index].toFixed(3) : '—'}</output><small>mm</small></div>)}</div></section>
    <div class="environment" aria-label="Warunki otoczenia"><div><span>Temperatura</span><strong><IconTemperature size={21} aria-hidden="true"/>{!controller.offline.value && environment?.ok ? `${environment.temperature_c.toFixed(1)} °C` : '—'}</strong></div><div><span>Wilgotność</span><strong><IconDroplet size={21} aria-hidden="true"/>{!controller.offline.value && environment?.ok ? `${environment.humidity_percent.toFixed(1)} %` : '—'}</strong></div><div id="probe-indicator" class={`probe-indicator ${probeContact === true ? 'contact' : probeContact === false ? 'open' : 'unavailable'}`} role="status" aria-live="polite" aria-atomic="true" title="Stan logiczny wejścia PROBE raportowany przez sterownik. Zwarcie krokodylków powinno zmieniać wskazanie."><IconFocus2 size={22} aria-hidden="true"/><span>PROBE</span><strong>{probeLabel}</strong></div></div>
    <div class="header-actions"><Button id="connect-cnc" class="connect" icon={IconPlugConnected} title={cnc.connected ? 'Rozłącz CNC' : 'Połącz CNC'} aria-label={cnc.connected ? 'Rozłącz CNC' : 'Połącz CNC'} disabled={!controller.connectReady.value} onClick={() => onRequest(cnc.connected ? 'disconnect' : 'connect')}>{controller.pending.value === 'connect' ? 'Łączenie…' : controller.pending.value === 'disconnect' ? 'Rozłączanie…' : cnc.connected ? 'Rozłącz' : 'Połącz'}</Button><Button id="top-job-stop" class="stop" icon={IconPlayerStop} disabled={!controller.known.value || !controller.active.value} title={controller.active.value ? 'Przerwij aktywne zadanie lub pomiar' : 'Brak aktywnego zadania do przerwania'} onClick={() => controller.send({action: controller.probing.value ? 'probe_stop' : 'job_stop'},true)}>Stop</Button></div>
    <section id="station-notice" class={`station-notice ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'} aria-live={notice.tone === 'error' ? 'assertive' : 'polite'} aria-atomic="true"><IconInfoCircle size={23} aria-hidden="true"/><p>{notice.text}</p>{notice.dismissible && <button type="button" class="text-button" onClick={controller.acknowledge}>Rozumiem</button>}<button type="button" class="text-button details-toggle" aria-label="Szczegóły stanu stanowiska" aria-expanded={details} aria-controls="station-details" onClick={() => setDetails(!details)}>Szczegóły {details ? <IconChevronUp size={17}/> : <IconChevronDown size={17}/>}</button></section>
    {details && <section id="station-details" class="station-details"><p>Odczyt CNC: {cnc.fresh ? 'aktualny' : 'nieaktualny'} · Kamera: {status?.camera?.ok ? 'dostępna' : 'niedostępna'} · Czujnik: {environment?.ok ? `odczyt sprzed ${environment.age_seconds?.toFixed(1)} s` : 'brak odczytu'}</p><ol>{controller.events.value.length ? controller.events.value.map(event => <li><time>{event.time}</time>{event.text}</li>) : <li>Brak zdarzeń w tej sesji przeglądarki.</li>}</ol></section>}
  </header>;
}

function Confirmation({request, onClose, onConfirm}) {
  const ref = useRef();
  useLayoutEffect(() => { if (request) { ref.current.showModal(); ref.current.querySelector('#dialog-cancel').focus(); } }, [request]);
  return <dialog ref={ref} id="action-dialog" aria-labelledby="dialog-title" aria-describedby="dialog-description" onCancel={event => {event.preventDefault(); onClose();}}>
    {request && <><div class="dialog-heading"><IconAlertTriangle size={32} aria-hidden="true"/><div><small>Potwierdzenie operatora</small><h2 id="dialog-title">{request.title}</h2></div></div><p id="dialog-description">{request.description}</p><p class="muted">Polecenie zostanie wysłane dopiero po potwierdzeniu.</p><div class="button-row"><Button id="dialog-cancel" onClick={onClose}>Anuluj</Button><Button id="dialog-confirm" class="primary" onClick={onConfirm}>{request.label}</Button></div>{controller.active.value && <Button class="stop" id="dialog-stop" icon={IconPlayerStop} onClick={() => {onClose(); controller.send({action: controller.probing.value ? 'probe_stop' : 'job_stop'}, true);}}>Przerwij program teraz</Button>}</>}
  </dialog>;
}

function Camera() {
  const ok = !controller.offline.value && controller.data.value?.camera?.ok;
  const [collapsed, setCollapsed] = useState(() => window.matchMedia('(max-width:760px)').matches);
  const [paused, setPaused] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => { if (ok) setFailed(false); }, [ok, controller.data.value]);
  return <section class={`camera-panel panel ${collapsed ? 'collapsed' : ''} ${expanded ? 'expanded' : ''}`} aria-labelledby="camera-heading"><div class="panel-heading"><h2 id="camera-heading">Podgląd na żywo</h2><div class="camera-actions"><Button aria-label={paused ? 'Wznów podgląd' : 'Wstrzymaj podgląd'} title={paused ? 'Wznów podgląd' : 'Wstrzymaj podgląd'} icon={paused ? IconPlayerPlay : IconPlayerPause} onClick={() => {setPaused(!paused); setFailed(false);}}/><Button class="expand-camera" aria-label={expanded ? 'Zmniejsz kamerę' : 'Powiększ kamerę'} title={expanded ? 'Przywróć mały podgląd' : 'Powiększ podgląd do co najmniej połowy ekranu'} aria-pressed={expanded} icon={expanded ? IconArrowsMinimize : IconArrowsMaximize} onClick={() => {setExpanded(!expanded);setCollapsed(false);}}/><Button class="collapse-camera" aria-label={collapsed ? 'Rozwiń kamerę' : 'Zwiń kamerę'} icon={collapsed ? IconChevronDown : IconChevronUp} onClick={() => {setCollapsed(!collapsed);setExpanded(false);}}/></div></div>{!collapsed && <><div class="camera-stage">{ok && !paused && !failed ? <img id="camera" src="/camera.mjpg" alt="Obraz z kamery stanowiska CNC" onError={() => setFailed(true)}/> : <p><IconCamera size={28}/>{paused ? 'Podgląd wstrzymany' : 'Kamera niedostępna'}</p>}</div><div class="camera-meta"><span>{ok && !paused && !failed ? '960 × 540 · 8 kl./s' : 'Podgląd stanowiska'}</span><a href="/camera.jpg" target="_blank" rel="noopener">Zdjęcie</a></div></>}</section>;
}

function App() {
  const [tab, setTab] = useState('file');
  const [jobPhase, setJobPhase] = useState('cut');
  const [fileFeed, setFileFeed] = useState('100');
  const [originalFeed, setOriginalFeed] = useState(true);
  const [showMap, setShowMap] = useState(false);
  const [step, setStep] = useState(0.1);
  const [feed, setFeed] = useState('100');
  const [power, setPower] = useState('300');
  const [probeDistance, setProbeDistance] = useState('1');
  const [probeFeed, setProbeFeed] = useState('20');
  const [request, setRequest] = useState(null);
  const [surfaceSettings, setSurfaceSettings] = useState(null);
  const [useSurfaceMap, setUseSurfaceMap] = useState(true);
  const inputRef = useRef();
  const opener = useRef();
  const cnc = controller.cnc.value;
  const job = controller.job.value;
  const manual = controller.manualReady.value;
  const free = controller.known.value && !controller.pending.value && !controller.active.value;
  const powerValid = Number.isInteger(Number(power)) && Number(power) >= 1 && Number(power) <= 1000;
  const bounds = job.bounds_mm;
  const fileFeedValid = Number.isFinite(Number(fileFeed)) && Number(fileFeed) >= 1 && Number(fileFeed) <= 300;
  const surfaceReady = cnc.surface_map?.valid && surfaceMatches(cnc.surface_map, job.id, surfaceSettings, bounds);
  const probeValid = Number.isFinite(Number(probeDistance)) && Number(probeDistance) >= 0.1 && Number(probeDistance) <= 5 && Number.isFinite(Number(probeFeed)) && Number(probeFeed) >= 10 && Number(probeFeed) <= 60;
  const probeReady = manual && cnc.probe_tested && cnc.probe_triggered === false && probeValid && Array.isArray(cnc.position) && cnc.position.length === 3 && cnc.position.every(Number.isFinite);
  useEffect(() => {setSurfaceSettings(null);setUseSurfaceMap(true);setOriginalFeed(true);setFileFeed(String(job.max_feed || 100));setShowMap(false);setJobPhase('cut');}, [job.id]);
  useEffect(() => {if (cnc.z_probe?.active && cnc.z_probe.kind === 'surface') setJobPhase('prepare'); else if (cnc.z_probe?.state === 'completed' && cnc.z_probe.kind === 'surface') setJobPhase('cut');}, [cnc.z_probe?.active, cnc.z_probe?.state]);
  useEffect(() => {controller.start(); return controller.stop;}, []);
  function ask(action, extra = {}) {
    if (request) return;
    if (action === 'job_start' && !originalFeed && !fileFeedValid) return;
    const id = job.id;
    const payload = {action, ...extra};
    const definitions = {
      connect: ['Połączyć CNC?', 'Upewnij się, że frezarka stoi, wrzeciono jest wyłączone i jesteś przy stanowisku. Otwarcie USB może zresetować sterownik.', 'Połącz CNC', () => controller.connectReady.value && !controller.cnc.value.connected],
      disconnect: ['Rozłączyć CNC?', 'Frezarka musi być bezczynna, a wrzeciono fizycznie wyłączone. Rozłączenie USB samo nie zatrzymuje wrzeciona.', 'Rozłącz CNC', () => controller.manualReady.value],
      job_start: ['Uruchomić program?', `${job.name}\n\nPosuw XY: ${originalFeed ? 'według pliku' : `${fileFeed} mm/min`}. Zagłębianie Z i rampy: według pliku.\n${surfaceReady && useSurfaceMap ? 'Kompensacja Z: aktualna mapa powierzchni.' : 'Program BEZ kompensacji powierzchni Z.'}\nSprawdź narzędzie, zakres, mocowania, zero materiału i prześwit. Usuń krokodylek z frezu. Program może uruchomić wrzeciono. Pozostań przy wyłączniku.`, 'Uruchom program', () => controller.manualReady.value && controller.job.value.id === id],
      surface_start: ['Zmierzyć powierzchnię PCB?', `${job.name}\n\nNajpierw pomiar referencyjny Z nad aktualną pozycją: maks. ${extra.distance} mm w dół, od Z=${cnc.position?.[2]?.toFixed(3)} do Z=${(Number(cnc.position?.[2]) - Number(extra.distance)).toFixed(3)} mm. To limit szukania styku, nie głębokość frezowania. Następnie ${extra.columns * extra.rows} punktów siatki, prześwit Z ${extra.clearance} mm, sondowanie do Z=−${extra.below} mm, posuw ${extra.feed} mm/min.\nWyłącz wrzeciono. Aktualny punkt i cała siatka muszą leżeć nad miedzią. Sprawdź uchwyty i miejsce na podniesienie frezu. Pomiar ustawi zero Z; X/Y pozostaną bez zmian.`, 'Rozpocznij pomiar', () => controller.manualReady.value && controller.cnc.value.probe_tested && controller.cnc.value.probe_triggered === false && controller.job.value.id === id],
      job_resume: ['Wznowić program?', 'Wznowienie uruchomi ruch narzędzia. Sprawdź maszynę, narzędzie i wrzeciono.', 'Wznów program', () => controller.known.value && controller.cnc.value.connected && controller.cnc.value.fresh && controller.job.value.state === 'paused' && controller.job.value.id === id],
      zero_xy: ['Ustawić zero X/Y?', 'Aktualna pozycja zostanie zapisana jako zero materiału. Polecenie nie przesuwa osi.', 'Ustaw zero', () => controller.manualReady.value],
      zero_z: ['Ustawić zero Z?', 'Aktualna wysokość zostanie zapisana jako powierzchnia materiału. Uwzględnij grubość papieru, jeśli był używany. Polecenie nie przesuwa osi.', 'Ustaw zero', () => controller.manualReady.value],
      probe_start: ['Ustawić zero Z sondą?', `Frez zjedzie maksymalnie ${probeDistance} mm z posuwem ${probeFeed} mm/min. Kontakt bezpośrednio z miedzią ustawi Z=0, potem frez podniesie się do Z=1 mm. Nie używaj dodatkowej płytki pomiarowej. Wyłącz wrzeciono i potwierdź poprawne wykrywanie zwarcia krokodylków. Pozostań przy wyłączniku.`, 'Rozpocznij sondowanie Z', () => controller.manualReady.value && controller.cnc.value.probe_tested && controller.cnc.value.probe_triggered === false],
      spindle_on: ['Włączyć wrzeciono?', `Wartość S: ${power} / 1000. Usuń ręce i luźne przedmioty ze strefy pracy. To skala sterownika, nie pomiar RPM.`, 'Włącz wrzeciono', () => controller.manualReady.value],
    };
    const definition = definitions[action];
    if (!definition) return;
    if (action.startsWith('job_')) Object.assign(payload, {job_id: id, confirmed: true});
    if (action === 'job_start' && surfaceReady && useSurfaceMap) payload.surface_map_id = cnc.surface_map.id;
    if (action === 'job_start' && !originalFeed) payload.xy_feed = Number(fileFeed);
    if (action === 'surface_start') {Object.assign(payload, {job_id:id, confirmed:true, position:[...cnc.position]});setUseSurfaceMap(true);}
    if (action === 'spindle_on') {if (!powerValid) return; payload.power = Number(power);}
    if (action === 'probe_start') {if (!probeReady) return; Object.assign(payload, {confirmed: true, distance: Number(probeDistance), feed: Number(probeFeed), position: [...cnc.position]});}
    opener.current = document.activeElement;
    setRequest({payload, title: definition[0], description: definition[1], label: definition[2], valid: definition[3], before: controller.snapshot()});
  }
  function close() {setRequest(null); document.getElementById('action-dialog')?.close(); opener.current?.focus();}
  async function upload(event) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {if (file.size > 1024 * 1024) throw new Error('Maksymalny rozmiar pliku to 1 MiB'); await controller.send({action: 'job_load', name: file.name, content: await file.text()});}
    catch (cause) {controller.error(`Nie wczytano pliku: ${cause.message}`);}
    finally {if (inputRef.current) inputRef.current.value = '';}
  }
  function move(axis, direction) {controller.send({action: 'jog', axis, distance: step * direction, feed: Number(feed)});}
  function tabKey(event, index) {
    let next;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault(); setTab(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`).focus();
  }
  return <main class={`shell compact phase-${jobPhase}`}><Header onRequest={ask}/><div class="workspace"><nav class="tabs" role="tablist" aria-label="Narzędzia operatora">{tabs.map((item,index) => <button id={`tab-${item.id}`} role="tab" type="button" aria-selected={tab === item.id} aria-controls={`tool-${item.id}`} tabIndex={tab === item.id ? 0 : -1} onClick={() => setTab(item.id)} onKeyDown={event => tabKey(event,index)}><item.icon size={20} aria-hidden="true"/><span>{item.label}</span></button>)}</nav><section class="operator panel">
    <div class="tool-scroll"><section id={`tool-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0}>
    {tab === 'move' && <><h2>Ręczne przesuwanie</h2><fieldset disabled={!manual}><div class="motion-settings"><div><label>Krok</label><div class="step-options">{[0.1,1,10].map(value => <label><input type="radio" name="step" value={value} checked={step === value} onChange={() => setStep(value)}/><span>{String(value).replace('.',',')} mm</span></label>)}</div></div><label>Prędkość · mm/min<input id="jog-feed" type="number" min="1" max="300" value={feed} onInput={event => setFeed(event.currentTarget.value)}/></label></div><div class="jog-controls"><div class="xy-pad"><Button class="up" onClick={() => move('Y',1)}>Y +</Button><Button class="left" onClick={() => move('X',-1)}>X −</Button><span>X / Y</span><Button class="right" onClick={() => move('X',1)}>X +</Button><Button class="down" onClick={() => move('Y',-1)}>Y −</Button></div><div class="z-pad"><Button onClick={() => move('Z',1)}>Z +</Button><span>Oś Z</span><Button onClick={() => move('Z',-1)}>Z −</Button></div></div></fieldset><Button id="cancel-jog" class="stop" icon={IconPlayerStop} disabled={!controller.known.value || !cnc.connected || controller.active.value} onClick={() => controller.send({action: 'jog_cancel'},true)}>Przerwij ruch</Button><p class="hint">Bez krańcówek: pilnuj końca zakresu. Zacznij od 0,1 mm.</p></>}
    {tab === 'zero' && <><h2>Zero materiału</h2><p class="hint">Ręcznie: ustaw narzędzie w punkcie odniesienia. Dla Z uwzględnij grubość papieru.</p><div class="button-row"><Button disabled={!manual} onClick={() => ask('zero_xy')}>Zero X / Y</Button><Button disabled={!manual} onClick={() => ask('zero_z')}>Zero Z ręcznie</Button></div><section class="zero-probe" aria-labelledby="zero-probe-title"><h3 id="zero-probe-title">Automatyczne zero Z</h3><p>Dotyk frezu bezpośrednio do miedzi PCB. Bez dodatkowej płytki pomiarowej.</p><p class="probe-check">{cnc.probe_tested ? 'Wejście wykryło styk. Przed startem rozewrzyj krokodylki.' : 'Najpierw zewrzyj krokodylki, sprawdź STYK w nagłówku i rozewrzyj je. Test jest wymagany po każdym połączeniu CNC.'}</p><fieldset disabled={!manual}><div class="probe-inputs"><label>Maks. zjazd Z · mm<input id="probe-distance" type="number" min="0.1" max="5" step="0.1" value={probeDistance} onInput={event => setProbeDistance(event.currentTarget.value)}/></label><label>Posuw · mm/min<input id="probe-feed" type="number" min="10" max="60" step="1" value={probeFeed} onInput={event => setProbeFeed(event.currentTarget.value)}/></label></div></fieldset><Button id="probe-start" class="primary" icon={IconFocus2} disabled={!probeReady} onClick={() => ask('probe_start')}>Ustaw zero Z sondą</Button><Button id="probe-stop" class="stop" icon={IconPlayerStop} disabled={!controller.known.value || !controller.probing.value} onClick={() => controller.send({action: 'probe_stop'},true)}>Przerwij sondę</Button><p class="hint">Wrzeciono wyłączone. Ustaw frez blisko nad miedzią i zapewnij 1 mm miejsca na odsunięcie w górę. Po sukcesie Z=1 mm; przed włączeniem wrzeciona zdejmij krokodylek z narzędzia.</p></section></>}
    {tab === 'file' && <FilePanel controller={controller} job={job} cnc={cnc} free={free} manual={manual} request={request} inputRef={inputRef} upload={upload} phase={jobPhase} onPhase={setJobPhase} fileFeed={fileFeed} onFeed={setFileFeed} originalFeed={originalFeed} onOriginal={setOriginalFeed} feedValid={fileFeedValid} surfaceReady={surfaceReady} surfaceSettings={surfaceSettings} onSurfaceSettings={setSurfaceSettings} useMap={useSurfaceMap} onUseMap={setUseSurfaceMap} showMap={showMap} onShowMap={setShowMap} ask={ask}/>}
    {tab === 'spindle' && <><h2>Wrzeciono</h2><label for="spindle-range" class="slider-label">S wrzeciona · 1–1000</label><div class="spindle-setting"><input id="spindle-range" type="range" min="1" max="1000" step="1" value={powerValid ? power : 1} disabled={!manual} onInput={event => setPower(event.currentTarget.value)}/><input id="spindle-power" type="number" aria-label="Wartość S wrzeciona" min="1" max="1000" step="1" value={power} disabled={!manual} onInput={event => setPower(event.currentTarget.value)}/></div><p class="hint">Skala sterownika, nie pomiar RPM.</p><div class="button-row spindle-actions"><Button class="primary" icon={IconPlayerPlay} disabled={!manual || !powerValid} onClick={() => ask('spindle_on')}>Włącz</Button><Button icon={IconPlayerStop} disabled={!manual} onClick={() => controller.send({action: 'spindle_off'})}>Wyłącz</Button></div><p class="hint">Wartość zostanie wysłana po kliknięciu Włącz.</p></>}
    </section></div></section><aside class="machine-preview"><Camera/>{tab === 'file' && jobPhase === 'cut' && <div class="desktop-map"><SurfaceOverview job={job} map={surfaceReady ? cnc.surface_map : null}/></div>}</aside>{tab === 'file' && <div class="job-actions"><div class="job-progress"><div class="progress-label"><span>Postęp</span><span>{job.acknowledged || 0} / {job.total || 0}</span></div><progress id="job-progress" max={job.total || 1} value={job.acknowledged || 0} aria-label="Polecenia przyjęte przez sterownik"/>{controller.active.value && <small>Posuw XY: {job.xy_feed ? job.xy_feed + ' mm/min' : 'według pliku'}</small>}</div><div class="execution-buttons"><Button id="job-start" class="primary" icon={IconPlayerPlay} disabled={!manual || !job.id || jobPhase !== 'cut' || (!originalFeed && !fileFeedValid)} title={!manual ? 'Start wymaga połączonego CNC w stanie bezczynności' : jobPhase !== 'cut' ? 'Przejdź do Frezowania' : 'Start po potwierdzeniu parametrów'} onClick={() => ask('job_start')}>{controller.pending.value === 'job_start' ? 'Uruchamianie…' : 'Start frezowania'}</Button><Button id="job-pause" title={controller.active.value ? 'Pauza nie wyłącza wrzeciona' : 'Pauza dostępna podczas pracy programu'} icon={job.state === 'paused' ? IconPlayerPlay : IconPlayerPause} disabled={!controller.known.value || !cnc.connected || !cnc.fresh || !['running','draining','paused'].includes(job.state)} onClick={() => job.state === 'paused' ? ask('job_resume') : controller.send({action: 'job_pause', job_id: job.id},true)}>{job.state === 'paused' ? 'Wznów' : 'Pauza'}</Button><Button id="job-stop" class="stop" icon={IconPlayerStop} disabled={!controller.known.value || !controller.active.value} onClick={() => controller.send({action: controller.probing.value ? 'probe_stop' : 'job_stop'},true)}>Stop</Button></div></div>}</div><footer class="safety"><IconPower size={22} aria-hidden="true"/><p>W razie niebezpieczeństwa użyj fizycznego wyłącznika maszyny.</p></footer><Confirmation request={request} onClose={close} onConfirm={() => {const current = request; close(); controller.confirmedSend(current.payload,current.before,current.valid);}}/></main>;
}
render(<App/>, document.getElementById('app'));

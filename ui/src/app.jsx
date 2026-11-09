import {render} from 'preact';
import {useEffect, useLayoutEffect, useRef, useState} from 'preact/hooks';
import {IconArrowsMaximize, IconArrowsMinimize, IconPlugConnected, IconPlugConnectedX, IconTemperature, IconDroplet, IconInfoCircle, IconAlertTriangle, IconChevronDown, IconChevronUp, IconArrowsMove, IconFocus2, IconFileCode, IconTool, IconPlayerPlay, IconPlayerPause, IconPlayerStop, IconFolder, IconSettings, IconCamera, IconPower} from '@tabler/icons-preact';
import {createController} from './controller.js';
import {SurfacePreview} from './SurfacePlan.jsx';
import {surfaceMatches, defaultSurfaceSettings} from './surface-plan.js';
import {FilePanel} from './FilePanel.jsx';
import {ServicePanel} from './ServicePanel.jsx';
import {JogPanel} from './JogPanel.jsx';
import {ProfileBar} from './Profiles.jsx';
import {ProfilePanel} from './ProfilePanel.jsx';
import {ZeroPanel} from './ZeroPanel.jsx';
import {probeBlockReason} from './probe-ready.js';
import {ParameterField} from './ParameterField.jsx';
import {toolDiameter} from './service-geometry.js';
import './style.css';
import './probe.css';
import './compact.css';
import {attachAppLifecycle} from './pwa.js';
import {InstallApp} from './InstallApp.jsx';

const controller = createController();
attachAppLifecycle(controller);
const tabs = [{id: 'move', label: 'Ruch', icon: IconArrowsMove}, {id: 'zero', label: 'Zero', icon: IconFocus2}, {id: 'file', label: 'Plik', icon: IconFileCode}, {id: 'spindle', label: 'Wrzeciono', icon: IconTool}, {id: 'service', label: 'Serwis', icon: IconSettings}, {id:'profiles',label:'Profile',icon:IconSettings}];
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
    <section id="station-notice" class={`station-notice ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'} aria-live={notice.tone === 'error' ? 'assertive' : 'polite'} aria-atomic="true"><IconInfoCircle size={23} aria-hidden="true"/><p>{notice.text}</p><ProfileBar controller={controller} cnc={cnc}/>{notice.dismissible && <button type="button" class="text-button" onClick={controller.acknowledge}>Rozumiem</button>}<button type="button" class="text-button details-toggle" aria-label="Szczegóły stanu stanowiska" aria-expanded={details} aria-controls="station-details" onClick={() => setDetails(!details)}>Szczegóły {details ? <IconChevronUp size={17}/> : <IconChevronDown size={17}/>}</button></section>
    {details && <section id="station-details" class="station-details"><p>Odczyt CNC: {cnc.fresh ? 'aktualny' : 'nieaktualny'} · Kamera: {status?.camera?.ok ? 'dostępna' : 'niedostępna'} · Czujnik: {environment?.ok ? `odczyt sprzed ${environment.age_seconds?.toFixed(1)} s` : 'brak odczytu'}</p><InstallApp/><ol>{controller.events.value.length ? controller.events.value.map(event => <li><time>{event.time}</time>{event.text}</li>) : <li>Brak zdarzeń w tej sesji przeglądarki.</li>}</ol></section>}
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
  const [step, setStep] = useState(0.1);
  const [customStep, setCustomStep] = useState('');
  const [feed, setFeed] = useState('300');
  const [power, setPower] = useState('300');
  const [probeDistance, setProbeDistance] = useState('1');
  const [probeFeed, setProbeFeed] = useState('20');
  const [request, setRequest] = useState(null);
  const [surfaceSettings, setSurfaceSettings] = useState(null);
  const [useSurfaceMap, setUseSurfaceMap] = useState(true);
  const [useServiceDepth, setUseServiceDepth] = useState(false);
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
  const flowStartReady = !job.pcb_flow || (job.state==='ready' && (job.pcb_flow.zPreparation==='grid3' ? surfaceReady && useSurfaceMap && cnc.surface_map.columns>=3 && cnc.surface_map.rows>=3 && (job.pcb_flow.kind!=='outline' || cnc.surface_map.perimeterOnly) : cnc.z_probe?.kind==='point' && cnc.z_probe.state==='completed' && cnc.z_probe.job_id===job.id));
  const probeReason = probeBlockReason({cnc,known:controller.known.value,pending:controller.pending.value,active:controller.active.value,distance:probeDistance,feed:probeFeed});
  const probeReady = !probeReason;
  useEffect(() => {setSurfaceSettings(job.pcb_flow?.kind==='outline' ? {...defaultSurfaceSettings(job.bounds_mm),perimeterOnly:true} : null);setUseSurfaceMap(true);setUseServiceDepth(false);setOriginalFeed(true);setFileFeed(String(job.max_feed || 100));setJobPhase(job.pcb_flow ? 'prepare' : 'cut');}, [job.id]);
  useEffect(() => {if (cnc.z_probe?.active && cnc.z_probe.kind === 'surface') setJobPhase('prepare'); else if (cnc.z_probe?.state === 'completed' && cnc.z_probe.kind === 'surface') setJobPhase('cut');}, [cnc.z_probe?.active, cnc.z_probe?.state]);
  useEffect(() => {controller.start(); return controller.stop;}, []);
  useLayoutEffect(() => {const scroll=document.querySelector('.tool-scroll');if(scroll) scroll.scrollTop=0;}, [tab]);
  useEffect(() => {setOriginalFeed(true);setUseServiceDepth(false);}, [cnc.calibration_profiles?.selected?.fingerprint]);
  function ask(action, extra = {}) {
    if (request) return;
    if (action === 'job_start') {
      const profile = cnc.calibration_profiles?.selected;
      const matches = profile?.model ? job.cam_profile?.id === profile.id && job.cam_profile?.fingerprint === profile.fingerprint : !job.cam_profile;
      if (!matches) {controller.error('Plik NC nie odpowiada aktywnemu profilowi. Wygeneruj CAM na PC albo wybierz profil zgodny z plikiem.');return;}
    }
    if (action === 'job_start' && !originalFeed && !fileFeedValid) return;
    const id = job.id;
    const payload = {action, ...extra};
    const definitions = {
      profile_test_finish: ['Powtórzyć przejazd wykańczający?', `Profil: ${cnc.calibration_profiles?.selected?.name}. Ta sama głębokość ${extra.depth} mm, ten sam tor i zapisana kompensacja Z. Bez dodatkowego pogłębiania.\n\nPotwierdzasz, że laminat, mocowanie, narzędzie i zero nie zostały zmienione. Usuń opiłki przy zatrzymanym wrzecionie, zdejmij krokodylek i usuń przewody z pola pracy. Program ponownie uruchomi wrzeciono i wykona jeden przejazd. Pozostań przy fizycznym wyłączniku.`, 'Wykonaj jeden przejazd', () => controller.manualReady.value && controller.cnc.value.calibration?.repeat?.available && controller.cnc.value.calibration?.repeat?.id === extra.repeat_id],
      profile_delete: ['Usunąć profil?', `Profil „${extra.name}” zostanie usunięty z listy. Jeśli jest wybrany, aplikacja przełączy się na Domyślny. Pliki CAM przygotowane dla usuniętego profilu nie będą zgodne z nowym wyborem.`, 'Usuń profil', () => controller.known.value && !controller.active.value && (!controller.cnc.value.connected || controller.manualReady.value)],
      profile_test_prepare: ['Zmierzyć 9 punktów testu profilu?', `Profil: ${cnc.calibration_profiles?.selected?.name}. Obszar ${Number(extra.area_width).toFixed(2)} × ${Number(extra.area_height).toFixed(2)} mm. ${extra.new_session ? 'Początek: aktualne X/Y.' : 'Kolejne świeże pole w Y.'}\n\nSiatka 3×3. Istniejące Z=0 pozostaje bez zmian. Prześwit Z=1 mm, sondowanie do Z=−0,4 mm, F20; maksymalny zjazd 1,4 mm. Wyłącz wrzeciono, sprawdź sondę i świeżą miedź pod całym polem. Frezowanie wymaga osobnego potwierdzenia.`, 'Zmierz 9 punktów', () => controller.manualReady.value && controller.cnc.value.probe_tested && controller.cnc.value.probe_triggered === false],
      profile_test_cut: ['Wykonać test wybranego profilu?', `Profil: ${cnc.calibration_profiles?.selected?.name}. Stałe zagłębienie ${extra.depth} mm, XY ${extra.feed}, Z ${extra.plunge} mm/min, wrzeciono S${extra.power}.\n\nPaski 10 mm o szerokościach 0,3 / 0,5 / 1 mm oraz ośmiokąty o przekątnych 1 i 2 mm. Tylko rowki izolacyjne. Aktualna mapa 9 punktów Z zostanie uwzględniona. Zdejmij krokodylek i przewód z pola pracy. Pozostań przy fizycznym wyłączniku.`, 'Frezuj test profilu', () => controller.manualReady.value && controller.cnc.value.calibration?.mode === 'profile_test' && controller.cnc.value.calibration?.map?.valid && controller.cnc.value.calibration?.session === extra.session],
      service_prepare: ['Zmierzyć pole serwisowe?', `Pomiar 5 punktów: cztery rogi i środek pola 12 × 5 mm. ${extra.new_session ? 'Początek: aktualne X/Y.' : 'Kolejne pole: +6,5 mm w Y od poprzedniego.'}\n\nZ=0 pozostanie bez zmian. Najpierw przejazd do Z=1 mm, potem przejazdy i sondowanie do Z=−0,4 mm z F20. Każdy zjazd sondy: maks. 1,4 mm. Zapewnij prześwit, świeżą miedź na całym polu i wyłącz wrzeciono. Sprawdź przewód sondy. Po pomiarze wykonanie próbki wymaga osobnego potwierdzenia.`, 'Zmierz 5 punktów', () => controller.manualReady.value && controller.cnc.value.probe_tested && controller.cnc.value.probe_triggered === false],
      service_cut: ['Wykonać próbkę serwisową?', `Zagłębienie ${extra.depth} mm pod lokalną powierzchnię. Pasek nominalnie ${extra.width} mm; rowek i pasek długości 10 mm. Posuw X/Y: ${extra.feed} mm/min, zagłębianie Z: ${extra.plunge} mm/min, wrzeciono S${extra.power} (nie pomiar RPM).\n\nZdejmij krokodylek z frezu i usuń przewód z pola ruchu. Mapa Z jest uwzględniona, istniejące zero pozostaje bez zmian. Pole zostanie oznaczone jako wykorzystane. Pozostań przy fizycznym wyłączniku.`, 'Wykonaj próbkę', () => controller.manualReady.value && controller.cnc.value.calibration?.map?.valid && controller.cnc.value.calibration?.session === extra.session],
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
    if (action.startsWith('service_') || action.startsWith('profile_test_')) payload.confirmed = true;
    if (action === 'profile_delete') payload.confirmed = true;
    if (action === 'service_cut') definition[1] += `\nFrez: końcówka ${extra.tip} mm, kąt całkowity ${extra.angle}°. Rowek teoretyczny bez korekt profilu: ${(extra.predicted_diameter ?? toolDiameter(extra.tip, extra.angle, extra.depth)).toFixed(3)} mm.`;
    if (action.startsWith('job_')) Object.assign(payload, {job_id: id, confirmed: true});
    if (action === 'job_start' && surfaceReady && useSurfaceMap) payload.surface_map_id = cnc.surface_map.id;
    if (action === 'job_start' && !originalFeed) payload.xy_feed = Number(fileFeed);
    if (action === 'job_start' && useServiceDepth && cnc.calibration?.profile) {
      payload.service_depth = true;
      payload.expected_depth = cnc.calibration.profile.depth;
      definition[1] += `\nProfil serwisowy: głębokość ${cnc.calibration.profile.depth} mm. Tylko pliki z jednym poziomem cięcia, bez ramp.`;
    }
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
    {tab === 'move' && <JogPanel controller={controller} cnc={cnc} step={step} onStep={setStep} customStep={customStep} onCustomStep={setCustomStep} feed={feed} onFeed={setFeed}/>}
    {tab === 'zero' && <ZeroPanel controller={controller} cnc={cnc} ask={ask} distance={probeDistance} onDistance={setProbeDistance} feed={probeFeed} onFeed={setProbeFeed} reason={probeReason}/>}
    {tab === 'file' && <FilePanel controller={controller} job={job} cnc={cnc} free={free} manual={manual} request={request} inputRef={inputRef} upload={upload} phase={jobPhase} onPhase={setJobPhase} fileFeed={fileFeed} onFeed={setFileFeed} originalFeed={originalFeed} onOriginal={setOriginalFeed} feedValid={fileFeedValid} surfaceReady={surfaceReady} surfaceSettings={surfaceSettings} onSurfaceSettings={setSurfaceSettings} useMap={useSurfaceMap} onUseMap={setUseSurfaceMap} ask={ask} onOpenZero={()=>setTab('zero')}/>}
    {tab === 'profiles' && <ProfilePanel controller={controller} cnc={cnc} ask={ask}/>}
    {tab === 'service' && <ServicePanel controller={controller} cnc={cnc} ask={ask}/>}
    {tab === 'file' && job.id && cnc.calibration?.profile && !cnc.calibration_profiles?.selected?.model && <label class="service-check"><input id="file-service-depth" type="checkbox" disabled={!free || !!request} checked={useServiceDepth} onChange={event => setUseServiceDepth(event.currentTarget.checked)}/>Użyj zagłębienia z Serwisu: {cnc.calibration.profile.depth.toFixed(2)} mm · jeden poziom cięcia, bez ramp</label>}
    {tab === 'spindle' && <><h2>Wrzeciono</h2><ParameterField id="spindle-power" label="Ustawienie wrzeciona · S" value={power} onChange={setPower} options={[100,200,300,400,500,600,700,800,900,1000]} min={1} max={1000} disabled={!manual} format={v=>`S${v} · ${v/10}%`} help="S1000 to pełna skala sterownika; S300 to 30%. To nie jest pomiar obrotów RPM."/><input id="spindle-range" type="range" aria-label="Ustawienie wrzeciona suwakiem" min="1" max="1000" step="1" value={powerValid ? power : 1} disabled={!manual} onInput={event => setPower(event.currentTarget.value)}/><div class="button-row spindle-actions"><Button class="primary" icon={IconPlayerPlay} disabled={!manual || !powerValid} onClick={() => ask('spindle_on')}>Włącz</Button><Button icon={IconPlayerStop} disabled={!manual} onClick={() => controller.send({action: 'spindle_off'})}>Wyłącz</Button></div><p class="hint">Zmiana listy lub suwaka nie włącza wrzeciona. Ustawienie jest wysyłane po kliknięciu Włącz.</p></>}
    </section></div></section><aside class="machine-preview"><Camera/>{tab === 'file' && jobPhase === 'cut' && <SurfacePreview job={job} map={surfaceReady ? cnc.surface_map : null}/>}</aside>{tab === 'file' && <div class="job-actions"><div class="job-progress"><div class="progress-label"><span>Postęp</span><span>{job.acknowledged || 0} / {job.total || 0}</span></div><progress id="job-progress" max={job.total || 1} value={job.acknowledged || 0} aria-label="Polecenia przyjęte przez sterownik"/>{controller.active.value && <small>Posuw XY: {job.xy_feed ? job.xy_feed + ' mm/min' : 'według pliku'}</small>}</div><div class="execution-buttons"><Button id="job-start" class="primary" icon={IconPlayerPlay} disabled={!flowStartReady || !manual || !job.id || jobPhase !== 'cut' || (!originalFeed && !fileFeedValid)} title={!manual ? 'Start wymaga połączonego CNC w stanie bezczynności' : jobPhase !== 'cut' ? 'Przejdź do Frezowania' : 'Start po potwierdzeniu parametrów'} onClick={() => ask('job_start')}>{controller.pending.value === 'job_start' ? 'Uruchamianie…' : 'Start frezowania'}</Button><Button id="job-pause" title={controller.active.value ? 'Pauza nie wyłącza wrzeciona' : 'Pauza dostępna podczas pracy programu'} icon={job.state === 'paused' ? IconPlayerPlay : IconPlayerPause} disabled={!controller.known.value || !cnc.connected || !cnc.fresh || !['running','draining','paused'].includes(job.state)} onClick={() => job.state === 'paused' ? ask('job_resume') : controller.send({action: 'job_pause', job_id: job.id},true)}>{job.state === 'paused' ? 'Wznów' : 'Pauza'}</Button><Button id="job-stop" class="stop" icon={IconPlayerStop} disabled={!controller.known.value || !controller.active.value} onClick={() => controller.send({action: controller.probing.value ? 'probe_stop' : 'job_stop'},true)}>Stop</Button></div></div>}</div><footer class="safety"><IconPower size={22} aria-hidden="true"/><p>W razie niebezpieczeństwa użyj fizycznego wyłącznika maszyny.</p></footer><Confirmation request={request} onClose={close} onConfirm={() => {const current = request; close(); controller.confirmedSend(current.payload,current.before,current.valid);}}/></main>;
}
render(<App/>, document.getElementById('app'));

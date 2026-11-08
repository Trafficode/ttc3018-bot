import {useState} from 'preact/hooks';
import {IconFocus2, IconPlayerPlay, IconDeviceFloppy, IconPlayerStop} from '@tabler/icons-preact';
import './service.css';
import {serviceGeometry} from './service-geometry.js';
import {ParameterField} from './ParameterField.jsx';

const activeStates = ['running', 'draining', 'pausing', 'paused', 'resuming'];
const format = value => Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(3)}` : '—';

function TrialParameters({entry}) {
  return <small class="trial-parameters">Pasek {entry.width} mm · frez {entry.tip ?? .1} / {entry.angle ?? 30}° · XY {entry.feed} · Z {entry.plunge ?? 20} mm/min · S {entry.power}{entry.geometry && <> · rowek {entry.geometry.diameter_mm.toFixed(3)} mm · rozstaw {entry.geometry.centreline_spacing_mm.toFixed(3)} mm</>}</small>;
}

function ToolSettings({tip, angle, disabled, onTip, onAngle}) {
  return <fieldset class="service-module"><legend>Frez V</legend><div class="service-fields service-speeds"><label>Końcówka · mm<input id="service-tip" type="number" min="0.01" max="0.5" step="0.01" value={tip} disabled={disabled} onInput={event => onTip(event.currentTarget.value)}/></label><label>Kąt całkowity · °<input id="service-angle" type="number" min="10" max="90" step="1" value={angle} disabled={disabled} onInput={event => onAngle(event.currentTarget.value)}/></label></div><small>Domyślnie 0,1 mm / 30°. Zmiana frezu wymaga nowego pomiaru Z.</small></fieldset>;
}

function SampleMap({map, width, origin, geometry}) {
  const points = [[0,0], [12,0], [12,5], [0,5], [6,2.5]];
  const samples = map?.samples || [];
  const reference = geometry.diameter ?? 0;
  const half = (Number(width) + reference) / 2;
  const stroke = Math.max(1, (geometry.diameter ?? 0) * 25);
  const values = samples.map(point => point.z);
  const spread = values.length ? Math.max(...values) - Math.min(...values) : null;
  const x = value => 60 + value * 25;
  const y = value => 180 - value * 25;
  return <figure class="service-map">
    <figcaption><strong>Wzór próbki · 10 mm</strong><span>{samples.length} / 5 punktów{spread !== null && ` · ΔZ ${spread.toFixed(3)} mm`}</span></figcaption>
    <svg viewBox="0 30 430 205" role="img" aria-label="Plan próbki: rowek oraz pasek miedzi długości 10 mm. Pięć punktów sondowania, osie lokalne X i Y. Wartości wysokości względem istniejącego Z zero.">
      <rect x="60" y="55" width="300" height="125" fill="#c98d58" stroke="#ac7446"/>
      <line x1={x(1)} y1={y(1)} x2={x(11)} y2={y(1)} stroke="#f6efd8" stroke-width={stroke}/>
      <rect x={x(1-reference/2)} y={y(3.3+half)} width={(10+reference)*25} height={half*50} fill="none" stroke="#f6efd8" stroke-width={stroke}/>
      <text x={x(6)} y={y(1)+17} text-anchor="middle">rowek</text>
      <text x={x(6)} y={y(3.3)-20} text-anchor="middle">pasek {width} mm nominalnie</text>
      <path d="M60 202H360M60 202V192M360 202V192M38 180V55M38 55H44M38 180H44" stroke="#54616d" fill="none"/>
      <text x="210" y="222" text-anchor="middle">X → 12 mm · cięcie 10 mm</text>
      <text x="20" y="118" text-anchor="middle" transform="rotate(-90 20 118)">Y → 5 mm</text>
      {points.map(([px,py], index) => {
        const measured = samples[index];
        const current = map?.active && index === samples.length;
        return <g key={index} class={current ? 'probe-current' : ''}>
          <circle cx={x(px)} cy={y(py)} r="6" fill={measured ? '#287b5c' : current ? '#ac6500' : '#fff'} stroke="#273642" stroke-width="1.2"/>
          <text x={x(px)} y={y(py)+(py === 0 || index === 4 ? 18 : -13)} text-anchor="middle">{index+1} · {format(measured?.z)}</text>
        </g>;
      })}
    </svg>
    <small>Wysokości względem Z=0 · początek X {origin?.[0]?.toFixed(2) ?? '—'}, Y {origin?.[1]?.toFixed(2) ?? '—'}</small>
  </figure>;
}

export function ServicePanel({controller, cnc, ask}) {
  const state = cnc.calibration || {};
  const service = {...state, history:state.history?.filter(entry=>entry.mode!=='profile_test')};
  const initial = (service.mode === 'service' ? service.settings : null) || service.profile || {};
  const [depth, setDepth] = useState(String(initial.depth || 0.05));
  const [width, setWidth] = useState(String(initial.width || 0.5));
  const [tip, setTip] = useState(String(initial.tip || 0.1));
  const [angle, setAngle] = useState(String(initial.angle || 30));
  const [feed, setFeed] = useState(String(initial.feed || 100));
  const [plunge, setPlunge] = useState(String(initial.plunge || 20));
  const [power, setPower] = useState(String(initial.power || 300));
  const [newSession, setNewSession] = useState(service.mode==='profile_test' || !service.base);
  const [clipRemoved, setClipRemoved] = useState(false);
  const map = service.mode === 'profile_test' ? null : service.map;
  const job = service.mode === 'profile_test' ? {} : service.job || {};
  const toolMatches = Number(tip) === (service.settings?.tip ?? .1) && Number(angle) === (service.settings?.angle ?? 30);
  const ready = map?.valid && !newSession && toolMatches;
  const busy = controller.active.value || !!controller.pending.value;
  const manual = controller.manualReady.value;
  const config = {depth: Number(depth), width: Number(width), tip: Number(tip), angle: Number(angle), feed: Number(feed), plunge: Number(plunge), power: Number(power)};
  const geometry = serviceGeometry(config);
  const valid = !geometry.error && Object.values(config).every(Number.isFinite) && config.feed >= 10 && config.feed <= 300 && config.plunge >= 1 && config.plunge <= 100 && config.power >= 1 && config.power <= 1000;
  const canProbe = manual && valid && cnc.probe_tested && cnc.probe_triggered === false && Array.isArray(cnc.position) && cnc.position[2] >= 0 && cnc.position[2] <= 3;
  const cutting = activeStates.includes(job.state);
  const origin = newSession ? cnc.position : ready || map?.active || cutting ? service.origin : (service.origin ? [service.origin[0], service.origin[1]+6.5] : cnc.position);
  const shownMap = ready || map?.active || cutting ? map : null;
  function adjust(delta) {
    setDepth(String(Math.min(.3, Math.max(.01, Math.round((Number(depth || .05)+delta)*100)/100))));
  }
  const params = {...config, predicted_diameter:geometry.diameter, session: service.session || null, position: cnc.position ? [...cnc.position] : null};
  return <section class="service-panel" aria-labelledby="service-title">
    <div class="service-title"><h2 id="service-title">Próba zagłębienia</h2><span>{map?.active ? 'Pomiar Z' : activeStates.includes(job.state) ? 'Frezowanie' : ready ? 'Mapa gotowa' : 'Przygotowanie'}</span></div>
    <p class="service-hint">Tryb niezależny od profili. Wszystkie parametry tej próby ustawiasz ręcznie; korekta aktywnego profilu nie jest stosowana.</p>
    <SampleMap map={shownMap} width={width} origin={origin} geometry={geometry}/>
    <ToolSettings tip={tip} angle={angle} disabled={busy} onTip={value => {setTip(value);setClipRemoved(false);}} onAngle={value => {setAngle(value);setClipRemoved(false);}}/>
    <fieldset class="service-module"><legend>Próbka</legend><label class="service-strip-label" for="service-width">Nominalna szerokość paska · mm<input id="service-width" type="number" min="0.2" max="2" step="0.1" value={width} disabled={busy} onInput={event => setWidth(event.currentTarget.value)}/></label>
    <div class="depth-control"><label for="service-depth">Zagłębienie pod powierzchnię <small>mm</small></label><div class="depth-value"><button type="button" disabled={busy} onClick={() => adjust(-.01)} aria-label="Zmniejsz zagłębienie o 0,01 mm">−</button><input id="service-depth" type="number" min="0.01" max="0.3" step="0.01" value={depth} disabled={busy} onInput={event => setDepth(event.currentTarget.value)}/><button type="button" disabled={busy} onClick={() => adjust(.01)} aria-label="Zwiększ zagłębienie o 0,01 mm">+</button></div><input id="service-depth-slider" type="range" aria-label="Zagłębienie frezu w mm" min="0.01" max="0.3" step="0.01" value={valid ? depth : .05} disabled={busy} onInput={event => setDepth(event.currentTarget.value)}/></div>
    <div class="service-estimate"><span>Przewidywana szerokość rowka</span><output id="service-groove" aria-live="polite">{geometry.diameter !== undefined ? geometry.diameter.toLocaleString('pl-PL',{minimumFractionDigits:3,maximumFractionDigits:3}) + ' mm' : '—'}</output></div><small>Teoria z geometrii frezu, bez korekty profilu. Odsunięcia X/Y uwzględniają aktualne zagłębienie, aby zachować zadaną szerokość paska.</small></fieldset>
    {geometry.error && <p class="field-error" role="alert">{geometry.error}</p>}
    {map?.valid && !toolMatches && <p class="service-hint">Frez zmieniony — wykonaj nowy pomiar Z.</p>}
    <fieldset class="service-module" disabled={busy}><legend>Prędkości</legend>
    <div class="service-fields service-speeds"><ParameterField id="service-feed" label="Prędkość frezowania XY · mm/min" value={feed} onChange={setFeed} options={[10,25,50,75,100,150,200,250,300]} min={10} max={300} disabled={busy} help="Prędkość poziomego ruchu frezu podczas wycinania próbki."/><ParameterField id="service-plunge" label="Wejście w materiał Z · mm/min" value={plunge} onChange={setPlunge} options={[1,5,10,15,20,30,40,50,75,100]} min={1} max={100} disabled={busy} help="Prędkość opuszczania frezu przy rozpoczęciu cięcia. Przy 20 mm/min zjazd o 1 mm trwa 3 sekundy."/></div>
    <div class="service-spindle"><ParameterField id="service-power" label="Wrzeciono · S" value={power} onChange={setPower} options={[100,200,300,400,500,600,700,800,900,1000]} min={1} max={1000} disabled={busy} format={v=>`S${v} · ${v/10}%`} help="S1000 to pełna skala sterownika. S nie jest pomiarem RPM."/><input id="service-power-range" type="range" aria-label="Ustawienie wrzeciona w próbie" min="1" max="1000" value={Number(power) >= 1 && Number(power) <= 1000 ? power : 1} disabled={busy} onInput={event => setPower(event.currentTarget.value)}/></div>
    <p class="service-hint">Zmiany dotyczą następnej próby. S to skala sterownika, nie pomiar RPM. Sondowanie pozostaje F20; przejazdy G0 według sterownika.</p>
    </fieldset>
    <label class="service-check"><input id="service-new" type="checkbox" disabled={busy} checked={newSession} onChange={event => {setNewSession(event.currentTarget.checked);setClipRemoved(false);}}/>Nowa sesja od aktualnego X/Y</label>
    <p class="service-hint">Istniejące Z=0 · pole 12 × 5 mm · następne pole +6,5 mm w Y. Zjazd sondy maks. 1,4 mm. Suwak ustawia tylko następną próbę.</p>
    {!cnc.probe_tested && <p class="service-hint">Przed pomiarem sprawdź zwarcie krokodylków i rozewrzyj je. Ustaw Z pomiędzy 0 a 3 mm.</p>}
    <div class="service-actions"><button id="service-probe" type="button" class={ready ? '' : 'primary'} disabled={!canProbe} onClick={() => {setClipRemoved(false);ask('service_prepare', {...params, new_session: newSession});setNewSession(false);}}><IconFocus2 size={17}/>{ready ? 'Pomiar następnego pola' : '1. Zmierz 5 punktów'}</button>
    <label class="service-check"><input id="service-clip" type="checkbox" disabled={!ready || busy} checked={clipRemoved && ready} onChange={event => setClipRemoved(event.currentTarget.checked)}/>Krokodylek zdjęty z frezu</label>
    <button id="service-cut" type="button" class="primary" disabled={!manual || !ready || !valid || !clipRemoved || cnc.probe_triggered !== false} onClick={() => ask('service_cut', {...params, map_id: map.id, clip_removed: true})}><IconPlayerPlay size={17}/>2. Wykonaj próbkę</button>
    {controller.active.value && <button id="service-stop" class="stop" type="button" onClick={() => controller.send({action: controller.probing.value ? 'probe_stop' : 'job_stop'},true)}><IconPlayerStop size={17}/>Stop</button>}</div>
    {activeStates.includes(job.state) && <progress max={job.total || 1} value={job.acknowledged || 0} aria-label="Postęp próbki"/>}
    {service.history?.length > 0 && <details class="service-history"><summary>Historia prób · {service.history.length}</summary><ol>{[...service.history].reverse().map(entry => <li key={`${entry.number}-${entry.origin}`}><span>#{entry.number} · <strong>{entry.depth.toFixed(2)} mm</strong> · {entry.state === 'completed' ? 'zakończona' : 'przerwana'}<TrialParameters entry={entry}/></span><button type="button" title="Zapisz parametry robocze; nie tworzy korekty geometrycznej" disabled={busy || !controller.known.value || entry.state !== 'completed'} onClick={() => controller.send({action: 'service_save', number: entry.number, session: service.session})}><IconDeviceFloppy size={15}/>Zapisz parametry</button></li>)}</ol></details>}
    {service.profile && <p class="service-hint">Profil: frez {service.profile.tip ?? .1} mm / {service.profile.angle ?? 30}° · pasek {service.profile.width} mm · Z −{service.profile.depth.toFixed(2)} mm · XY {service.profile.feed} · Z {service.profile.plunge ?? 20} mm/min · S {service.profile.power}.</p>}
  </section>;
}

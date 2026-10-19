import {useLayoutEffect, useRef, useState} from 'preact/hooks';
import {IconChevronDown, IconChevronUp, IconPlayerPlay, IconPlayerStop} from '@tabler/icons-preact';
import {createSurfacePlan, defaultSurfaceSettings, surfaceRequest, surfaceMatches, surfaceHeights} from './surface-plan.js';

const number = value => Number(value).toLocaleString('pl-PL', {maximumFractionDigits: 3});
const delta = value => `${value >= 0 ? '+' : '−'}${Math.abs(value).toLocaleString('pl-PL', {minimumFractionDigits:3, maximumFractionDigits:3})}`;
const heightColor = value => Math.abs(value) < 0.0005 ? '#167342' : value > 0 ? '#a34813' : '#175fa5';

// A data plot, not an illustration: every dot is derived from the loaded job.
function PlanPlot({plan, bounds, map}) {
  const ref = useRef();
  const heights = surfaceHeights(map);
  useLayoutEffect(() => {
    const canvas = ref.current;
    function draw() {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      const ctx = canvas.getContext('2d');
      ctx.scale(ratio, ratio);
      const left = 46, top = 32, bottom = height - 51, right = width - 30;
      const xSpan = plan.area.X[1] - plan.area.X[0];
      const ySpan = plan.area.Y[1] - plan.area.Y[0];
      const scaleX = (right - left) / xSpan, scaleY = (bottom - top) / ySpan;
      const plotWidth = xSpan * scaleX, plotHeight = ySpan * scaleY;
      const originX = left + (right - left - plotWidth) / 2;
      const originY = bottom - (bottom - top - plotHeight) / 2;
      const x = value => originX + (value - plan.area.X[0]) * scaleX;
      const y = value => originY - (value - plan.area.Y[0]) * scaleY;
      ctx.font = '12px system-ui';
      ctx.lineWidth = 1;
      ctx.strokeStyle = '#dad8d1';
      // The only rectangle is the actual machining extent, never a claimed
      // physical PCB outline; G-code contains no knowledge of stock/clamps.
      ctx.strokeRect(x(bounds.X[0]), y(bounds.Y[1]),
        (bounds.X[1] - bounds.X[0]) * scaleX, (bounds.Y[1] - bounds.Y[0]) * scaleY);
      ctx.setLineDash([3, 5]);
      ctx.strokeStyle = '#dedbd4';
      ctx.beginPath();
      plan.points.forEach((point, index) => {
        if (index) ctx.lineTo(x(point.x), y(point.y));
        else ctx.moveTo(x(point.x), y(point.y));
      });
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.strokeStyle = '#49515a';
      const baseX = originX - 13, baseY = originY + 13;
      const tipX = originX + plotWidth + 12, tipY = originY - plotHeight - 12;
      ctx.beginPath();
      ctx.moveTo(baseX, tipY); ctx.lineTo(baseX, baseY); ctx.lineTo(tipX, baseY);
      ctx.moveTo(baseX - 4, tipY + 7); ctx.lineTo(baseX, tipY); ctx.lineTo(baseX + 4, tipY + 7);
      ctx.moveTo(tipX - 7, baseY - 4); ctx.lineTo(tipX, baseY); ctx.lineTo(tipX - 7, baseY + 4);
      ctx.stroke();
      ctx.fillStyle = '#28323c';
      ctx.textAlign = 'left';
      ctx.fillText('+Y [mm]', Math.max(4, baseX - 4), tipY - 10);
      ctx.textAlign = 'right';
      ctx.fillText('+X [mm]', width - 2, baseY + 32);
      ctx.fillText('ΔZ [mm] · zero: 0,0', width - 2, 11);
      ctx.fillStyle = '#69717a';
      for (const fraction of [0, 0.5, 1]) {
        const tickX = plan.area.X[0] + fraction * xSpan;
        const tickY = plan.area.Y[0] + fraction * ySpan;
        ctx.textAlign = 'center';
        ctx.fillText(number(tickX), x(tickX), baseY + 17);
        ctx.textAlign = 'right';
        ctx.fillText(number(tickY), baseX - 5, y(tickY) + 4);
      }
      plan.points.forEach(point => {
        ctx.beginPath(); ctx.arc(x(point.x), y(point.y), 4, 0, Math.PI * 2);
        const sample = map?.samples?.find(item => item.number === point.number);
        const measured = heights.values.find(item => item.number === point.number);
        ctx.fillStyle = measured ? heightColor(measured.delta) : sample ? '#167342' : map?.active && point.number === map.completed + 1 ? '#a96300' : '#85898b'; ctx.fill();
        ctx.textAlign = 'center';
        const label = measured ? delta(measured.delta) : sample ? 'Z: …' : String(point.number);
        ctx.font = '11px system-ui';
        ctx.fillStyle = '#faf9f5';
        ctx.fillRect(x(point.x) - 23, y(point.y) - 23, 46, 15);
        ctx.fillStyle = measured ? heightColor(measured.delta) : '#28323c';
        ctx.fillText(label, x(point.x), y(point.y) - 11);
      });
    }
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => observer.disconnect();
  }, [plan, bounds, map]);
  return <div class="surface-plot-scroll" tabIndex="0" aria-label="Mapa pomiarów; większą siatkę można przewijać"><canvas ref={ref} class="surface-plot" role="img"
    style={{minWidth:Math.max(280, (plan.columns - 1) * 55 + 95), '--surface-height':`${Math.max(180, (plan.rows - 1) * 55 + 70)}px`}}
    aria-label={`Plan ${plan.points.length} punktów. Oś X w prawo, Y w górę. Wartości ΔZ w mm względem X=0, Y=0; dokładne wyniki w liście punktów poniżej.`}/></div>;
}

export function SurfaceOverview({job, map}) {
  if (!job.bounds_mm || !map?.area || !map?.samples?.length) return <p class="map-empty">Brak zmierzonej mapy dla tego pliku.</p>;
  const plan = createSurfacePlan(job.bounds_mm, {columns:map.columns, rows:map.rows, area:map.area});
  if (plan.error) return <p class="map-empty">{plan.error}</p>;
  const heights = surfaceHeights(map);
  return <section class="surface-overview" aria-label="Podgląd mapy Z"><h3>Mapa Z <small>{map.completed} / {map.total} · {map.valid ? 'gotowa' : map.active ? 'pomiar' : 'nieaktualna'}</small></h3><PlanPlot plan={plan} bounds={job.bounds_mm} map={map}/><p>ΔZ względem X=0, Y=0 · mm</p>{heights.min !== null && <p>Min {delta(heights.min)} · max {delta(heights.max)} · różnica {number(heights.max - heights.min)} mm</p>}<p>Brąz: wyżej · niebieski: niżej · zielony: zero</p></section>;
}

export function SurfacePlan({job, settings, onChange, locked, canProbe, map, onStart, onStop, canStop, useMap, onUseMap}) {
  const [open, setOpen] = useState(true);
  const [editArea, setEditArea] = useState(false);
  const [custom, setCustom] = useState(false);
  if (!job.id || !job.bounds_mm) return null;
  const current = settings || defaultSurfaceSettings(job.bounds_mm);
  const customSelected = custom || !([3, 5].includes(Number(current.columns)) && Number(current.columns) === Number(current.rows));
  const plan = createSurfacePlan(job.bounds_mm, current);
  const params = surfaceRequest(job.bounds_mm, current);
  const currentMap = surfaceMatches(map, job.id, current, job.bounds_mm) ? map : null;
  const ready = currentMap?.valid === true;
  const heights = surfaceHeights(currentMap);
  const choose = count => {onChange({...current, columns: count, rows: count}); setCustom(false);};
  function changeArea(axis, index, value) {
    const area = {...current.area, [axis]: [...current.area[axis]]};
    area[axis][index] = value;
    onChange({...current, area});
  }
  return <section class={`surface-plan ${currentMap?.active ? 'measuring' : ''}`} aria-labelledby="surface-heading">
    <div class="surface-heading"><button type="button" class="surface-toggle" aria-expanded={open} aria-controls="surface-body" onClick={() => setOpen(!open)}><h3 id="surface-heading">Pomiar powierzchni</h3>{open ? <IconChevronUp size={18}/> : <IconChevronDown size={18}/>}</button>{open && <button type="button" class="text-button" aria-expanded={editArea} onClick={() => setEditArea(!editArea)}>Zmień obszar</button>}</div>
    {open && <div id="surface-body">
      <p class="surface-description">Plan punktów w obszarze obróbki z pliku.</p>
      <fieldset disabled={locked} class="surface-settings">
        <div class="surface-grid" role="group" aria-label="Gęstość siatki pomiarowej">
          {[3, 5].map(count => <button type="button" aria-pressed={!customSelected && Number(current.columns) === count && Number(current.rows) === count} onClick={() => choose(count)}>{count} × {count}</button>)}
          <button type="button" aria-pressed={customSelected} onClick={() => setCustom(true)}>Własna</button>
        </div>
        {customSelected && <div class="surface-custom">{[['columns', 'Punkty X'], ['rows', 'Punkty Y']].map(([key, label]) => <label>{label}<input type="number" min="2" max="11" step="1" value={current[key]} onInput={event => onChange({...current, [key]: event.currentTarget.value})}/></label>)}</div>}
        {editArea && <div class="surface-area">{['X','Y'].map(axis => <div><label>{axis} min · mm<input type="number" step="0.1" value={current.area[axis][0]} onInput={event => changeArea(axis, 0, event.currentTarget.value)}/></label><label>{axis} max · mm<input type="number" step="0.1" value={current.area[axis][1]} onInput={event => changeArea(axis, 1, event.currentTarget.value)}/></label></div>)}<button type="button" class="text-button" onClick={() => onChange({...current, area: defaultSurfaceSettings(job.bounds_mm).area})}>Przywróć zakres z pliku</button></div>}
      </fieldset>
      <details class="surface-motion"><summary>Parametry · pierwszy zjazd {number(current.distance ?? 1.5)} mm</summary><fieldset disabled={locked}><div class="surface-custom">{[['distance','Maks. pierwszy zjazd · mm',0.1,5,0.1,1.5],['clearance','Prześwit Z · mm',1,3,0.1,2],['below','Zakres pod zerem · mm',0.1,2,0.1,1],['feed','Posuw sondy · mm/min',10,60,1,20]].map(([key,label,min,max,step,fallback]) => <label>{label}<input type="number" min={min} max={max} step={step} value={current[key] ?? fallback} onInput={event => onChange({...current,[key]:event.currentTarget.value})}/></label>)}</div></fieldset></details>
      {plan.error ? <p class="surface-validation" role="status">{plan.error}</p> : <div class="surface-preview"><PlanPlot plan={plan} bounds={job.bounds_mm} map={currentMap}/><div class="surface-summary"><ul class="surface-legend"><li><span class="extent-key"/>Obszar obróbki</li><li class="height-legend"><span>Brąz: wyżej</span><span>Niebieski: niżej</span><span>Zielony: zero · szary: oczekuje</span></li></ul><strong id="surface-count">{currentMap ? `${currentMap.completed} / ${plan.points.length} · ${ready ? 'mapa gotowa' : currentMap.active ? 'pomiar' : 'nieaktualna'}` : `${plan.points.length} punktów · plan`}</strong><div class="surface-heights" role="status"><strong>ΔZ względem X=0, Y=0 · mm</strong><p>{heights.source ? heights.source === 'interpolated' ? 'Poziom 0,0: interpolacja pomiarów.' : 'Poziom 0,0: pomiar bezpośredni.' : 'Poziom 0,0 niedostępny — wymagany pomiar w zerze lub wokół niego.'}</p>{heights.min !== null && <p>Min {delta(heights.min)} · max {delta(heights.max)}<br/>Różnica wysokości: {number(heights.max - heights.min)} mm</p>}</div><p class="surface-spacing"><span>Rozstaw X: {number(plan.spacingX)} mm</span><span>Rozstaw Y: {number(plan.spacingY)} mm</span></p><button hidden={currentMap?.active} id="surface-start" type="button" class="primary" disabled={locked || !canProbe || !!params.error} onClick={() => onStart(params)}><IconPlayerPlay size={18}/>{ready ? 'Powtórz pomiar' : 'Rozpocznij pomiar'}</button>{currentMap?.active && <button id="surface-stop" type="button" class="stop" disabled={!canStop} onClick={onStop}><IconPlayerStop size={18}/>Przerwij pomiar</button>}<p id="surface-readiness">{ready ? 'Mapa gotowa. Zdejmij krokodylek z frezu przed frezowaniem.' : currentMap?.active ? 'Pomiar trwa. Stop przerywa całą siatkę.' : !canProbe ? 'Połącz CNC, sprawdź STYK przy zwarciu, potem rozewrzyj sondę.' : 'Pomiar uruchamia ruch osi po potwierdzeniu.'}</p></div></div>}
      {!plan.error && params.error && <p class="surface-validation">{params.error}</p>}
      {ready && <label class="surface-use"><input id="surface-use" type="checkbox" checked={useMap} disabled={locked} onChange={event => onUseMap(event.currentTarget.checked)}/>Używaj tej mapy do kompensacji Z przy starcie pliku</label>}
      {currentMap && !currentMap.valid && !currentMap.active && <p class="surface-note">Mapa nieaktualna lub pomiar przerwany — wykonaj pełny pomiar ponownie.</p>}
      <p class="surface-note">Ustaw frez blisko nad miedzią. Najpierw pomiar referencyjny i zero Z, potem siatka. Wrzeciono wyłączone; sprawdź miedź, uchwyty i prześwit. Po zmianie narzędzia, mocowania lub zera powtórz pomiar.</p>
      {!plan.error && <details class="surface-points"><summary>Lista punktów · X / Y / ΔZ</summary><ol>{plan.points.map(point => <li key={point.number}><span>{point.number}</span><span>X {number(point.x)} mm</span><span>Y {number(point.y)} mm</span><span>ΔZ {heights.values.find(item => item.number === point.number) ? delta(heights.values.find(item => item.number === point.number).delta) + ' mm' : '—'}</span></li>)}</ol></details>}
    </div>}
  </section>;
}

import {useLayoutEffect, useRef, useState} from 'preact/hooks';
import {IconChevronDown, IconChevronUp, IconPlayerPlay} from '@tabler/icons-preact';
import {createSurfacePlan, defaultSurfaceSettings} from './surface-plan.js';

const number = value => Number(value).toLocaleString('pl-PL', {maximumFractionDigits: 3});

// A data plot, not an illustration: every dot is derived from the loaded job.
function PlanPlot({plan, bounds}) {
  const ref = useRef();
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
      const scale = Math.min((right - left) / xSpan, (bottom - top) / ySpan);
      const plotWidth = xSpan * scale, plotHeight = ySpan * scale;
      const originX = left + (right - left - plotWidth) / 2;
      const originY = bottom - (bottom - top - plotHeight) / 2;
      const x = value => originX + (value - plan.area.X[0]) * scale;
      const y = value => originY - (value - plan.area.Y[0]) * scale;
      ctx.font = '12px system-ui';
      ctx.lineWidth = 1;
      ctx.strokeStyle = '#dad8d1';
      // The only rectangle is the actual machining extent, never a claimed
      // physical PCB outline; G-code contains no knowledge of stock/clamps.
      ctx.strokeRect(x(bounds.X[0]), y(bounds.Y[1]),
        (bounds.X[1] - bounds.X[0]) * scale, (bounds.Y[1] - bounds.Y[0]) * scale);
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
        ctx.fillStyle = '#85898b'; ctx.fill();
        // Dense grids retain dots; labels live in the accessible point list.
        if (plan.points.length <= 25) {
          ctx.fillStyle = '#28323c'; ctx.textAlign = 'center';
          ctx.fillText(String(point.number), x(point.x), y(point.y) - 9);
        }
      });
    }
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => observer.disconnect();
  }, [plan, bounds]);
  return <canvas ref={ref} class="surface-plot" role="img"
    aria-label={`Plan ${plan.points.length} punktów. Oś X w prawo, Y w górę. Współrzędne względem zera materiału; lista punktów poniżej.`}/>;
}

export function SurfacePlan({job, settings, onChange, locked}) {
  const [open, setOpen] = useState(true);
  const [editArea, setEditArea] = useState(false);
  const [custom, setCustom] = useState(false);
  if (!job.id || !job.bounds_mm) return null;
  const current = settings || defaultSurfaceSettings(job.bounds_mm);
  const customSelected = custom || !([3, 5].includes(Number(current.columns)) && Number(current.columns) === Number(current.rows));
  const plan = createSurfacePlan(job.bounds_mm, current);
  const choose = count => {onChange({...current, columns: count, rows: count}); setCustom(false);};
  function changeArea(axis, index, value) {
    const area = {...current.area, [axis]: [...current.area[axis]]};
    area[axis][index] = value;
    onChange({...current, area});
  }
  return <section class="surface-plan" aria-labelledby="surface-heading">
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
      {plan.error ? <p class="surface-validation" role="status">{plan.error}</p> : <div class="surface-preview"><PlanPlot plan={plan} bounds={job.bounds_mm}/><div class="surface-summary"><ul class="surface-legend"><li><span class="extent-key"/>Obszar obróbki</li><li><span class="point-key"/>Punkty pomiaru — oczekują</li></ul><strong id="surface-count">{plan.points.length} punktów · plan</strong><p class="surface-spacing"><span>Rozstaw X: {number(plan.spacingX)} mm</span><span>Rozstaw Y: {number(plan.spacingY)} mm</span></p><button id="surface-start" type="button" class="primary" disabled aria-describedby="surface-unavailable"><IconPlayerPlay size={18}/>Rozpocznij pomiar</button><p id="surface-unavailable">Sondowanie Z nie jest jeszcze dostępne.</p></div></div>}
      <p class="surface-note">Współrzędne G54 względem zera materiału (0,0). Przed pomiarem sprawdź miedź i uchwyty. Wrzeciono musi być wyłączone.</p>
      {!plan.error && <details class="surface-points"><summary>Lista punktów · X / Y</summary><ol>{plan.points.map(point => <li key={point.number}><span>{point.number}</span><span>X {number(point.x)} mm</span><span>Y {number(point.y)} mm</span></li>)}</ol></details>}
    </div>}
  </section>;
}

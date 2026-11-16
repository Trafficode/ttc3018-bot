import {useEffect, useState} from 'preact/hooks';
import {ProfileSettings, defaultProfile} from './Profiles.jsx';
import {AppSelect} from './AppSelect.jsx';
import './profile-test.css';

const mm = value => Number(value).toLocaleString('pl-PL',{maximumFractionDigits:3});
const activeStates = ['running','draining','paused','pausing','resuming'];

function TestPreview({plan, map, origin}) {
  const scale = Math.min(270/plan.width, 235/plan.height);
  const bottom = 35 + plan.height*scale;
  const x = value => 48+value*scale;
  const y = value => bottom-value*scale;
  const points = list => list.map(([a,b])=>`${x(a)},${y(b)}`).join(' ');
  return <figure class="profile-test-preview"><figcaption><strong>Wzór testu · tylko izolacja</strong><span>{map?.samples?.length || 0} / 9 punktów Z</span></figcaption>
    <svg viewBox={`0 0 365 ${bottom+45}`} role="img" aria-label="Trzy paski miedzi długości 10 mm: 0,3, 0,5 i 1 mm. Dwa ośmiokąty o przekątnych 1 i 2 mm. Siatka pomiaru wysokości 3 na 3, osie X i Y.">
      <rect x={x(0)} y={y(plan.height)} width={plan.width*scale} height={plan.height*scale} fill="#c98d58" stroke="#ac7446"/>
      {plan.shapes.map((shape,index)=><g key={index}><polygon points={points(shape.path)} fill="none" stroke="#f6efd8" stroke-width={plan.diameter*scale} stroke-linejoin="round"/>{shape.kind==='strip' ? <text x={x((shape.copper[0][0]+shape.copper[1][0])/2)} y={y(shape.copper[0][1])-8} text-anchor="middle">10 × {mm(shape.width)} mm</text> : <text x={x((shape.copper[0][0]+shape.copper[4][0])/2)} y={y(shape.copper[6][1])+14} text-anchor="middle">↔ {shape.diameter} mm</text>}</g>)}
      {[0,1,2].flatMap(row=>[0,1,2].map(column=>{
        const a=column*plan.width/2,b=row*plan.height/2;
        const sample=map?.samples?.find(p=>Math.abs(p.x-(origin?.[0]+a))<.001&&Math.abs(p.y-(origin?.[1]+b))<.001);
        return <g key={`${row}-${column}`}><circle cx={x(a)} cy={y(b)} r="4" fill={sample?'#287b5c':'#fff'} stroke="#273642"/><text x={x(a)} y={y(b)+(row===0?15:-9)} text-anchor="middle">{sample ? `${sample.z>=0?'+':''}${sample.z.toFixed(3)}` : '—'}</text></g>;
      }))}
      <path d={`M${x(0)} ${bottom+20}H${x(plan.width)}M28 ${y(0)}V${y(plan.height)}`} stroke="#53616d" fill="none"/>
      <text x={x(plan.width/2)} y={bottom+37} text-anchor="middle">X → {mm(plan.width)} mm</text><text x="14" y={35+plan.height*scale/2} text-anchor="middle" transform={`rotate(-90 14 ${35+plan.height*scale/2})`}>Y → {mm(plan.height)} mm</text>
    </svg><small>Margines 1 mm z każdej strony od całego obszaru frezowania. Siatka Z obejmuje ten sam prostokąt. Wysokości względem automatycznie ustalonego Z=0.</small>
  </figure>;
}

export function ProfilePanel({controller, cnc, ask, operationSelector}) {
  const selected=cnc.calibration_profiles?.selected || defaultProfile;
  const service=cnc.calibration || {};
  const plan=cnc.profile_test_plan;
  const matches=service.mode==='profile_test' && service.profile_identity?.fingerprint===selected.fingerprint;

  const [repeatChecked,setRepeatChecked]=useState(false);
  const [tab,setTab]=useState('settings');
  function tabKey(event){if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'settings':event.key==='End'?'test':tab==='settings'?'test':'settings';setTab(next);document.getElementById(next==='settings'?'profile-settings-tab':'profile-test-tab')?.focus();}
  useEffect(()=>{setRepeatChecked(false);},[service.job?.state,service.repeat?.id,selected.fingerprint]);
  const map=matches ? service.map : null;
  const busy=controller.active.value || !!controller.pending.value;
  const canProbe=controller.manualReady.value && plan && !plan.error && cnc.probe_tested && cnc.probe_triggered===false && Array.isArray(cnc.position);
  const cycle=matches ? service.cycle : null;
  const origin=cycle?.active||service.repeat?.valid ? service.origin : cnc.position;
  const params={profile_id:selected.id,profile_fingerprint:selected.fingerprint,session:service.session || null,position:cnc.position ? [...cnc.position] : null};
  const repeat=service.repeat;
  const inRepeatArea=cnc.position && map?.area && cnc.position[0]>=map.area.X[0]-.002 && cnc.position[0]<=map.area.X[1]+.002 && cnc.position[1]>=map.area.Y[0]-.002 && cnc.position[1]<=map.area.Y[1]+.002 && cnc.position[2]>=0 && cnc.position[2]<=3;
  const selectReady=controller.known.value&&!busy&&(!cnc.connected||controller.manualReady.value);
  return <section class={`service-panel profile-panel ${tab==='settings'?'profile-config-panel':''}`}><header class="profile-panel-heading"><h2>Profile</h2>{operationSelector}
    <AppSelect id="profile-choice" label="Profil frezu V" value={selected.id} disabled={!selectReady} onChange={id=>controller.send({action:'profile_select',profile_id:id})} options={(cnc.calibration_profiles?.profiles||[defaultProfile]).map(profile=>({value:profile.id,label:profile.name}))}/>
    </header><div class="profile-subtabs" role="tablist" aria-label="Widok profilu" onKeyDown={tabKey}><button id="profile-settings-tab" type="button" role="tab" tabIndex={tab==='settings'?0:-1} aria-selected={tab==='settings'} aria-controls="profile-content" onClick={()=>setTab('settings')}>Ustawienia</button><button id="profile-test-tab" type="button" role="tab" tabIndex={tab==='test'?0:-1} aria-selected={tab==='test'} aria-controls="profile-content" onClick={()=>setTab('test')}>Test profilu</button></div>
    <div id="profile-content" role="tabpanel" aria-labelledby={tab==='settings'?'profile-settings-tab':'profile-test-tab'}>
    {tab==='settings'?<ProfileSettings controller={controller} cnc={cnc} ask={ask}/>:<>
    {plan?.settings&&<p class="profile-test-conditions">Z −{plan.settings.depth} mm · frez {plan.settings.tip} / {plan.settings.angle}° · XY {plan.settings.feed} · wejście Z {plan.settings.plunge} mm/min · S{plan.settings.power}</p>}
    {!plan || plan.error ? <p class="field-error">{plan?.error || 'Oczekiwanie na plan testu.'}</p> : <>
      <TestPreview plan={plan} map={matches && (map?.active || cycle || repeat?.valid) ? map : null} origin={origin}/>
      <p class="service-hint">Paski: 10 mm × 0,3 / 0,5 / 1 mm. Ośmiokąty: przekątne 1 i 2 mm między przeciwległymi wierzchołkami. Rowek: {mm(plan.diameter)} mm. Obszar: {mm(plan.width)} × {mm(plan.height)} mm.</p>
      <p class="service-hint">Bieżące X/Y to lokalne 0,0 testu — lewy dolny narożnik pola. Ustaw frez blisko nad świeżą miedzią; pierwszy zjazd szuka styku maksymalnie 1,4 mm. Zero X/Y projektu pozostaje zachowane.</p>
      <p class="service-hint">Jeden cykl: zero Z → mapa 3 × 3 → frezowanie wzoru. Parametry cięcia pochodzą z wybranego profilu. Sonda pozostaje podłączona do obudowy wrzeciona; przewód musi być poza obszarem ruchu.</p>
      {cycle&&<p role="status">{cycle.phase==='probing'?`Pomiar Z · ${map?.samples?.length||0} / 9 punktów`:cycle.phase==='cutting'?'Frezowanie wzoru testowego':cycle.phase==='completed'?'Test profilu zakończony':cycle.phase==='failed'?'Test przerwany błędem':cycle.phase==='stopped'?'Test zatrzymany':''}</p>}
      {cycle?.error&&<p role="alert">{cycle.error}</p>}
      {!busy&&(!cnc.connected?<p class="service-hint" role="status">Połącz CNC przy stanowisku, aby uruchomić test.</p>:!cnc.probe_tested?<p class="service-hint" role="status">Sprawdź styk sondy z miedzią i odsuń frez przed uruchomieniem testu.</p>:cnc.probe_triggered!==false?<p class="service-hint" role="status">Sonda musi być rozwarta przed rozpoczęciem pomiaru.</p>:null)}
      <div class="service-actions">
      <button id="profile-test-start" class="primary" type="button" disabled={!canProbe||busy} onClick={()=>ask('profile_test_start',{...params,fixed_probe:true,...plan.settings})}>Uruchom test profilu</button>
      {busy&&<button class="stop" type="button" onClick={()=>controller.send({action:controller.probing.value?'probe_stop':'job_stop'},true)}>Stop testu</button>}
      </div>
      {matches&&activeStates.includes(service.job?.state)&&<progress max={service.job.total||1} value={service.job.acknowledged||0} aria-label="Postęp frezowania wzoru"/>}
      {matches && repeat?.passes>0 && <section class="profile-finish" aria-labelledby="profile-finish-title"><h3 id="profile-finish-title">Przejazd wykańczający</h3><p>Wykonane przejazdy: {repeat.passes}. Oczyść PCB przy zatrzymanym wrzecionie. Powtórka używa tego samego toru i mapy Z, bez dodatkowego zagłębiania.</p>
        {!repeat.valid ? <p class="field-error" role="status">{repeat.reason || 'Przygotowanie zmieniło się. Wykonaj nowy pomiar i test.'}</p> : <><label class="service-check"><input id="profile-finish-setup" type="checkbox" checked={repeatChecked} disabled={busy} onChange={e=>setRepeatChecked(e.currentTarget.checked)}/>Laminat, mocowanie, frez i zero bez zmian; przewód poza obszarem ruchu</label>{!inRepeatArea && <p class="service-hint">Ustaw frez nad zapisanym obszarem testu, na Z od 0 do 3 mm.</p>}<button id="profile-test-finish" type="button" class="primary" disabled={!controller.manualReady.value || !repeat.available || !inRepeatArea || !repeatChecked || cnc.probe_triggered!==false} onClick={()=>ask('profile_test_finish',{...params,repeat_id:repeat.id,setup_unchanged:true,fixed_probe:true,depth:repeat.depth})}>Powtórz przejazd wykańczający</button></>}
      </section>}
    </>}
    </>}
    </div>
  </section>;
}

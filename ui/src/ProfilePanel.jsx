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
    </svg><small>Margines 1 mm z każdej strony od całego obszaru frezowania. Siatka Z obejmuje ten sam prostokąt. Wysokości względem aktualnego Z=0.</small>
  </figure>;
}

export function ProfilePanel({controller, cnc, ask}) {
  const selected=cnc.calibration_profiles?.selected || defaultProfile;
  const service=cnc.calibration || {};
  const plan=cnc.profile_test_plan;
  const matches=service.mode==='profile_test' && service.profile_identity?.fingerprint===selected.fingerprint;
  const [newSession,setNewSession]=useState(!matches || !service.base);
  const [clip,setClip]=useState(false);
  const [repeatChecked,setRepeatChecked]=useState(false);
  const [tab,setTab]=useState('settings');
  function tabKey(event){if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'settings':event.key==='End'?'test':tab==='settings'?'test':'settings';setTab(next);document.getElementById(next==='settings'?'profile-settings-tab':'profile-test-tab')?.focus();}
  useEffect(()=>{setClip(false);setNewSession(!matches || !service.base);},[selected.fingerprint]);
  useEffect(()=>{setRepeatChecked(false);},[service.job?.state,service.repeat?.id,selected.fingerprint]);
  const map=matches ? service.map : null;
  const ready=map?.valid && !newSession;
  const busy=controller.active.value || !!controller.pending.value;
  const canProbe=controller.manualReady.value && plan && !plan.error && cnc.probe_tested && cnc.probe_triggered===false && cnc.position?.[2]>=0 && cnc.position?.[2]<=3;
  const origin=newSession ? cnc.position : service.origin;
  const params={profile_id:selected.id,profile_fingerprint:selected.fingerprint,session:service.session || null,position:cnc.position ? [...cnc.position] : null};
  const repeat=service.repeat;
  const inRepeatArea=cnc.position && map?.area && cnc.position[0]>=map.area.X[0]-.002 && cnc.position[0]<=map.area.X[1]+.002 && cnc.position[1]>=map.area.Y[0]-.002 && cnc.position[1]<=map.area.Y[1]+.002 && cnc.position[2]>=0 && cnc.position[2]<=3;
  const selectReady=controller.known.value&&!busy&&(!cnc.connected||controller.manualReady.value);
  return <section class="service-panel profile-panel"><div class="service-title"><h2>Profile</h2><span>Serwis działa niezależnie</span></div>
    <AppSelect id="profile-choice" label="Profil frezu V" value={selected.id} disabled={!selectReady} onChange={id=>controller.send({action:'profile_select',profile_id:id})} options={(cnc.calibration_profiles?.profiles||[defaultProfile]).map(profile=>({value:profile.id,label:profile.name}))}/>
    <div class="profile-subtabs" role="tablist" aria-label="Widok profilu" onKeyDown={tabKey}><button id="profile-settings-tab" type="button" role="tab" tabIndex={tab==='settings'?0:-1} aria-selected={tab==='settings'} aria-controls="profile-content" onClick={()=>setTab('settings')}>Ustawienia</button><button id="profile-test-tab" type="button" role="tab" tabIndex={tab==='test'?0:-1} aria-selected={tab==='test'} aria-controls="profile-content" onClick={()=>setTab('test')}>Test profilu</button></div>
    <div id="profile-content" role="tabpanel" aria-labelledby={tab==='settings'?'profile-settings-tab':'profile-test-tab'}>
    {tab==='settings'?<ProfileSettings controller={controller} cnc={cnc} ask={ask}/>:<>
    {plan?.settings&&<p class="profile-test-conditions">Z −{plan.settings.depth} mm · frez {plan.settings.tip} / {plan.settings.angle}° · XY {plan.settings.feed} · wejście Z {plan.settings.plunge} mm/min · S{plan.settings.power}</p>}
    {!plan || plan.error ? <p class="field-error">{plan?.error || 'Oczekiwanie na plan testu.'}</p> : <>
      <TestPreview plan={plan} map={matches && (ready || map?.active || activeStates.includes(service.job?.state) || repeat?.valid) ? map : null} origin={repeat?.valid && !newSession ? service.origin : origin}/>
      <p class="service-hint">Paski: 10 mm × 0,3 / 0,5 / 1 mm. Ośmiokąty: przekątne 1 i 2 mm między przeciwległymi wierzchołkami. Rowek: {mm(plan.diameter)} mm. Obszar: {mm(plan.width)} × {mm(plan.height)} mm.</p>
      <label class="service-check"><input id="profile-test-new" type="checkbox" checked={newSession} disabled={busy} onChange={e=>{setNewSession(e.currentTarget.checked);setClip(false);}}/>Nowy test od aktualnego X/Y</label>
      <p class="service-hint">Z=0 pozostaje bez zmian. Sondowanie 3×3: F20, prześwit 1 mm, maksymalny zjazd 1,4 mm. Cały obszar musi leżeć nad świeżą miedzią.</p>
      <p class="service-hint">Wejście w miedź: szybki pionowy zjazd do 0,5 mm nad lokalną powierzchnią z mapy Z, następnie prędkość wejścia zapisana w profilu. Przejazdy XY pozostają na pełnym prześwicie.</p>
      <div class="service-actions"><button id="profile-test-probe" class="primary" type="button" disabled={!canProbe} onClick={()=>{setClip(false);ask('profile_test_prepare',{...params,new_session:newSession,area_width:plan.width,area_height:plan.height,...plan.settings});setNewSession(false);}}>1. Zmierz 9 punktów Z</button>
      <label class="service-check"><input id="profile-test-clip" type="checkbox" disabled={busy || !ready} checked={ready && clip} onChange={e=>setClip(e.currentTarget.checked)}/>Krokodylek zdjęty z frezu</label>
      <button id="profile-test-cut" class="primary" type="button" disabled={!controller.manualReady.value || !ready || !clip || cnc.probe_triggered!==false} onClick={()=>ask('profile_test_cut',{...params,map_id:map.id,clip_removed:true,...plan.settings})}>2. Frezuj test profilu</button>
      {controller.active.value && <button class="stop" type="button" onClick={()=>controller.send({action:controller.probing.value?'probe_stop':'job_stop'},true)}>Stop</button>}</div>
      {matches && activeStates.includes(service.job?.state) && <progress max={service.job.total || 1} value={service.job.acknowledged || 0} aria-label="Postęp testu profilu"/>}
      {matches && repeat?.passes>0 && <section class="profile-finish" aria-labelledby="profile-finish-title"><h3 id="profile-finish-title">Przejazd wykańczający</h3><p>Wykonane przejazdy: {repeat.passes}. Oczyść PCB przy zatrzymanym wrzecionie. Powtórka używa tego samego toru i mapy Z, bez dodatkowego zagłębiania.</p>
        {!repeat.valid ? <p class="field-error" role="status">{repeat.reason || 'Przygotowanie zmieniło się. Wykonaj nowy pomiar i test.'}</p> : <><label class="service-check"><input id="profile-finish-setup" type="checkbox" checked={repeatChecked} disabled={busy} onChange={e=>setRepeatChecked(e.currentTarget.checked)}/>Laminat, mocowanie, frez i zero bez zmian; przewód sondy zdjęty</label>{!inRepeatArea && <p class="service-hint">Ustaw frez nad zapisanym obszarem testu, na Z od 0 do 3 mm.</p>}<button id="profile-test-finish" type="button" class="primary" disabled={!controller.manualReady.value || !repeat.available || !inRepeatArea || !repeatChecked || cnc.probe_triggered!==false} onClick={()=>ask('profile_test_finish',{...params,repeat_id:repeat.id,setup_unchanged:true,clip_removed:true,depth:repeat.depth})}>Powtórz przejazd wykańczający</button></>}
      </section>}
    </>}
    </>}
    </div>
  </section>;
}

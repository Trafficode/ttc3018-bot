import {useEffect, useState} from 'preact/hooks';
import {IconCheck, IconChevronDown, IconChevronRight, IconPlus} from '@tabler/icons-preact';
import {ProfileSettings, defaultProfile, grooveMm} from './Profiles.jsx';
import {AppSelect} from './AppSelect.jsx';
import {probeDistanceLimit,probeNumber} from './probe-settings.js';
import './profile-test.css';

const size = value => Number(value).toLocaleString('pl-PL',{maximumFractionDigits:2});
const activeStates = ['running','draining','paused','pausing','resuming'];
const cycleLabels = {probing:'Pomiar Z',cutting:'Frezowanie wzoru',completed:'Test zakończony',failed:'Test przerwany błędem',stopped:'Test zatrzymany'};
const overlapChoices = [25,50,75].map(value=>({value:String(value),label:`${value}%`}));

function TestPreview({plan,map,origin}) {
  const scale=176/plan.height;
  const left=54;
  const bottom=12+plan.height*scale;
  const x=value=>left+value*scale;
  const y=value=>bottom-value*scale;
  const points=list=>list.map(([a,b])=>`${x(a)},${y(b)}`).join(' ');
  return <figure class="profile-test-preview"><figcaption><strong>Wzór testowy</strong><span>{map?.samples?.length||0} / 9 punktów Z</span></figcaption>
    <svg viewBox={`0 0 ${x(plan.width)+125} ${bottom+13}`} role="img" aria-label="Dwa paski miedzi 0,3 i 0,5 mm, ośmiokąt 1 mm i siatka pomiaru Z 3 × 3">
      <rect x={x(0)} y={y(plan.height)} width={plan.width*scale} height={plan.height*scale} rx="2" fill="#f0eadb" stroke="#bdb29e"/>
      {plan.shapes.map((shape,index)=><g key={index}>
        {[...(shape.paths||[shape.path])].reverse().map((path,lane)=><polygon key={lane} points={points(path)} fill="none" stroke={lane?'#f6efd8':'#fbf8ed'} stroke-width={plan.diameter*scale} stroke-linejoin="round"/>)}
        <polygon points={points(shape.copper)} fill="#edbb80" stroke="#aa671f" stroke-width="1"/>
        {shape.paths?.[1]&&<polygon points={points(shape.paths[1])} fill="none" stroke="#9b5a1d" stroke-width="1.2" stroke-dasharray="4 3"/>}
        <text x={x(plan.width)+30} y={y(shape.copper.reduce((sum,point)=>sum+point[1],0)/shape.copper.length)}
          dominant-baseline="middle">{shape.kind==='strip'?`Pasek ${size(shape.width)} mm`:`Ośmiokąt ${size(shape.diameter)} mm`}</text>
      </g>)}
      {[0,1,2].flatMap(row=>[0,1,2].map(column=>{
        const a=column*plan.width/2,b=row*plan.height/2;
        const sample=map?.samples?.find(point=>Math.abs(point.x-(origin?.[0]+a))<.001&&Math.abs(point.y-(origin?.[1]+b))<.001);
        return <g key={`${row}-${column}`}><circle cx={x(a)} cy={y(b)} r="3" fill={sample?'#287b5c':'#fff'} stroke="#53616d"/>
          {sample&&<text x={x(a)+(column===0?5:0)} y={y(b)+(row===2?13:-5)} text-anchor={column===0?'start':'middle'}>{`${sample.z>=0?'+':''}${sample.z.toFixed(3)}`}</text>}</g>;
      }))}
    </svg><small>Pole {size(plan.width)} × {size(plan.height)} mm · margines {size(plan.margin_mm)} mm</small>
  </figure>;
}

function ProfileStep({number,title,summary,open,disabled,onToggle,children}) {
  const Icon=open?IconChevronDown:IconChevronRight;
  return <section class={`profile-step ${open?'is-open':''}`}>
    <h3><button id={`profile-step-${number}`} type="button" aria-expanded={open} aria-controls={`profile-stage-${number}`} disabled={disabled} onClick={onToggle}>
      <Icon size={18} aria-hidden="true"/><span class="profile-step-number">{String(number).padStart(2,'0')}</span><span>{title}</span><small>{summary}</small>
    </button></h3>
    <div id={`profile-stage-${number}`} class="profile-step-body" hidden={!open} role="region" aria-labelledby={`profile-step-${number}`}>{open&&children}</div>
  </section>;
}

function TestValue({label,value}) {
  return <div class="profile-from-test"><span>{label}</span><strong>{value}</strong></div>;
}

const methodLabel=method=>method==='groove'?'z rowka':'z paska';
const calibratedTrial=profile=>profile.observations?.findLast(row=>
  row.mode==='profile_test'&&(row.calibration_method||row.groove_measurement));

function CalibrationForm({trial,profile,controller,locked}) {
  const [sample,setSample]=useState(()=>String(trial?.geometry?.strip_widths?.at(-1)??''));
  const [method,setMethod]=useState('groove');
  const [acceptDifference,setAcceptDifference]=useState(false),[continuous,setContinuous]=useState(false);
  const [strip,setStrip]=useState(''),[groove,setGroove]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  const geometry=trial?.geometry;
  if(!geometry){
    const result=profile.model&&profile.depth!=null?profile.model.intercept_mm+profile.model.slope*profile.depth:null;
    const row=calibratedTrial(profile);
    if(row&&result!==null)return <div class="profile-calibrate">
      <div class="profile-calibrate-heading"><strong><IconCheck size={18} aria-hidden="true"/>
        {row.calibration_method?`Kalibracja ${methodLabel(row.calibration_method)}`:'Potwierdzona pomiarem paska i rowka'}</strong></div>
      <div class="profile-measure-pair">
        {row.measured_width!=null&&<section><h4>Pasek miedzi</h4><TestValue label="Nominalny pasek" value={`${grooveMm(row.width)} mm`}/>
          <TestValue label="Zmierzony pasek" value={`${grooveMm(row.measured_width)} mm`}/></section>}
        {row.groove_measurement&&<section><h4>Rowek łącznie</h4><TestValue label="Założony rowek łącznie" value={`${grooveMm(row.geometry.diameter_mm+row.groove_measurement.step_mm)} mm`}/>
          <TestValue label="Zmierzony rowek łącznie" value={`${grooveMm(row.groove_measurement.total_mm)} mm`}/></section>}
      </div>
      <div class="profile-result"><strong>Szerokość skrawania · 1 przejazd: {grooveMm(result)} mm</strong><span>Przy zagłębieniu {grooveMm(profile.depth)} mm</span></div>
    </div>;
    return result===null?<p class="service-hint">Po zakończeniu testu wybierzesz pomiar paska albo rowka.</p>:
      <div class="profile-result"><strong>Szerokość skrawania · 1 przejazd: {grooveMm(result)} mm</strong><span>{profile.groove_verification?'Potwierdzona pomiarem':'Zapisany wynik · bez potwierdzenia pomiarem rowka'}</span></div>;
  }
  const width=Number(sample);
  const validNumber=value=>value!==''&&Number(value)>=.01&&Number(value)<=3&&Math.abs(Number(value)*100-Math.round(Number(value)*100))<1e-7;
  const measured=Number(groove)-geometry.step_mm;
  const inferred=geometry.diameter_mm+width-Number(strip);
  const stripValid=validNumber(strip)&&inferred>0&&inferred<2;
  const grooveValid=validNumber(groove)&&measured>geometry.step_mm+1e-9&&measured<2;
  const fromGroove=method==='groove';
  const needsContinuity=fromGroove&&geometry.step_mm>0;
  const selectedValid=fromGroove?grooveValid:stripValid;
  const selectedInput=fromGroove?groove:strip;
  const otherInvalid=fromGroove?strip!==''&&!stripValid:groove!==''&&!grooveValid;
  const divergent=stripValid&&grooveValid&&Math.abs(measured-inferred)>.020000001;
  const ready=selectedValid&&(!divergent||acceptDifference)&&(!needsContinuity||continuous);
  const disabled=locked||saving;
  function changed(){setAcceptDifference(false);setError('');}
  async function save(event){
    event.preventDefault();
    if(!ready||disabled)return;
    setError('');setSaving(true);
    try{
      if(!await controller.send({action:'profile_update',source:'profile_test',confirmed:true,
        profile_id:profile.id,profile_fingerprint:profile.fingerprint,trial_id:trial.trial_id,
        calibration_method:method,accept_disagreement:divergent&&acceptDifference,
        groove_continuous:needsContinuity&&continuous,
        ...(stripValid?{width,measured_width:Number(strip)}:{}),
        ...(grooveValid?{measured_groove:Number(groove)}:{})})){
        setError(controller.profileError.value||'Nie zapisano kalibracji.');
      }
    }finally{setSaving(false);}
  }
  return <form class="profile-calibrate" noValidate onSubmit={save}>
    <div class="profile-calibrate-heading"><strong><IconCheck size={18} aria-hidden="true"/>Test zakończony</strong>
      <AppSelect id="profile-sample" label="Pasek do pomiaru" value={sample} disabled={disabled}
        options={geometry.strip_widths.map(value=>({value:String(value),label:`Pasek ${grooveMm(value)} mm`}))}
        onChange={value=>{setSample(value);setStrip('');setGroove('');setContinuous(false);changed();}}/></div>
    <fieldset class="profile-methods">
      <legend>Kalibruj na podstawie</legend>
      <div class="profile-measure-pair">
        <section>
          <label class="profile-method"><input type="radio" name="calibration-method" value="strip" checked={!fromGroove} disabled={disabled}
            onChange={()=>{setMethod('strip');changed();}}/><strong>Pasek miedzi</strong><small>{fromGroove?'Opcjonalny':'Wybrany'}</small></label>
          <TestValue label="Nominalny pasek" value={`${grooveMm(width)} mm`}/>
          <label class="parameter-field">Zmierzony pasek · mm<input id="profile-strip-measurement" type="number" inputMode="decimal" min=".01" max="3" step=".01" required={!fromGroove} value={strip} disabled={disabled} onInput={e=>{setStrip(e.currentTarget.value);changed();}}/></label>
        </section>
        <section>
          <label class="profile-method"><input type="radio" name="calibration-method" value="groove" checked={fromGroove} disabled={disabled}
            onChange={()=>{setMethod('groove');changed();}}/><strong>Rowek łącznie</strong><small>{fromGroove?'Wybrany':'Opcjonalny'}</small></label>
          <TestValue label="Założony rowek łącznie" value={`${grooveMm(geometry.diameter_mm+geometry.step_mm)} mm${geometry.passes===2?' · 2 przejazdy':''}`}/>
          <label class="parameter-field">Zmierzony rowek łącznie · mm<input id="profile-groove-measurement" type="number" inputMode="decimal" min=".01" max="3" step=".01" required={fromGroove} value={groove} disabled={disabled} onInput={e=>{setGroove(e.currentTarget.value);setContinuous(false);changed();}}/></label>
        </section>
      </div>
    </fieldset>
    <p class="service-hint">Mierz na prostym odcinku z krokiem 0,01 mm. Drugi pomiar służy tylko do porównania.</p>
    {needsContinuity&&grooveValid&&<label class="profile-confirm-measurement"><input type="checkbox" checked={continuous} disabled={disabled}
      onChange={e=>setContinuous(e.currentTarget.checked)}/>Oba przejazdy utworzyły jeden ciągły rowek.</label>}
    {divergent&&<div class="profile-comparison-warning">
      <p role="status">Różnica {grooveMm(Math.abs(measured-inferred))} mm: z paska {grooveMm(inferred)} mm, z rowka {grooveMm(measured)} mm.</p>
      <label class="profile-confirm-measurement"><input type="checkbox" checked={acceptDifference} disabled={disabled}
        onChange={e=>setAcceptDifference(e.currentTarget.checked)}/>Mimo rozbieżności użyj pomiaru {methodLabel(method)}.</label>
    </div>}
    <div class="profile-result">
      <strong>Szerokość skrawania · 1 przejazd: {selectedValid?`${grooveMm(fromGroove?measured:inferred)} mm`:'—'}</strong>
      <small aria-live="polite">{selectedValid?`Wynik ${methodLabel(method)}`:'Wpisz pomiar dla wybranej metody.'}
        {selectedValid&&fromGroove&&geometry.step_mm>0&&<><br/>{grooveMm(Number(groove))} − {grooveMm(geometry.step_mm)} mm odstępu torów</>}
        {stripValid&&grooveValid&&!divergent&&<><br/>Oba pomiary są zgodne w granicy 0,02 mm.</>}</small>
      <button class="primary" type="submit" disabled={!ready||disabled}>{saving?'Zapisywanie…':'Zapisz kalibrację'}</button>
    </div>
    {selectedInput!==''&&!selectedValid&&<p class="field-error" role="status">
      {fromGroove&&validNumber(groove)&&geometry.step_mm>0&&measured<=geometry.step_mm+1e-9?'Ten pomiar nie potwierdza nakładania przejazdów. Sprawdź, czy rowek jest ciągły.':'Sprawdź pomiar: wynik poza zakresem lub więcej niż dwa miejsca po przecinku.'}</p>}
    {otherInvalid&&<p class="service-hint" role="status">Drugi pomiar jest niepoprawny i nie wpłynie na zapis.</p>}
    {error&&<p class="field-error" role="alert">{error}</p>}
  </form>;
}

export function ProfilePanel({controller,cnc,ask,operationSelector}) {
  const store=cnc.calibration_profiles;
  const selected=store?.selected||defaultProfile;
  const service=cnc.calibration||{};
  const [step,setStep]=useState(1),[creating,setCreating]=useState(false);
  const [dirty,setDirty]=useState(false),[reset,setReset]=useState(0);
  const [passes,setPasses]=useState(1),[overlap,setOverlap]=useState(50);
  const matches=service.mode==='profile_test'&&service.profile_identity?.id===selected.id&&service.profile_identity?.fingerprint===selected.fingerprint;
  const cycle=matches?service.cycle:null;
  const cycleActive=!!cycle?.active;
  const map=matches&&(service.map?.active||cycle)?service.map:null;
  const busy=controller.active.value||!!controller.pending.value;
  const locked=!controller.known.value||!!store?.error||busy||(cnc.connected&&!controller.manualReady.value);
  const base=cnc.profile_test_plan;
  const plan=base?.profile_fingerprint===selected.fingerprint?(passes===1?base:base.variants?.[String(overlap)]):base?.error?base:null;
  const trial=(store?.trials||[]).findLast(row=>row.state==='completed'&&row.mode==='profile_test'&&row.profile?.id===selected.id&&row.profile?.fingerprint===selected.fingerprint&&row.geometry?.strip_widths);
  const savedTrial=calibratedTrial(selected);
  const completed=trial||savedTrial;
  const proof=selected.groove_verification;
  const canProbe=controller.manualReady.value&&!locked&&!cnc.probe_settings?.error&&plan&&!plan.error&&cnc.probe_tested&&cnc.probe_triggered===false&&Array.isArray(cnc.position);
  useEffect(()=>{
    if(cycleActive)setStep(2);
    else if(step===2&&cycle?.phase==='completed'&&trial&&!creating)setStep(3);
  },[cycleActive,cycle?.phase,trial?.trial_id]);
  useEffect(()=>{setPasses(1);setOverlap(50);},[selected.id]);
  function cancel(){setCreating(false);setDirty(false);setReset(value=>value+1);}
  function choose(next){setStep(step===next?0:next);}
  const waitReason=cnc.probe_settings?.error?'Zapisz poprawne ustawienia sondowania przed testem.':!cnc.connected?'Połącz CNC przy stanowisku.':!cnc.probe_tested?'Sprawdź styk sondy i odsuń frez od miedzi.':cnc.probe_triggered!==false?'Przed testem sonda musi być rozwarta.':!controller.manualReady.value?'Test wymaga aktualnej pozycji i bezczynnej frezarki.':'';
  const probePlan=cycleActive&&service.settings?.passes===2?base?.variants?.[String(service.settings.overlap_percent)]:cycleActive?base:plan;
  const passSummary=(count,percent)=>count===2?`2 przejazdy · ${percent}%`:'1 przejazd';
  const testSummary=cycleActive||['failed','stopped'].includes(cycle?.phase)?cycleLabels[cycle.phase]:
    completed?`Wykonany · ${passSummary(completed.geometry.passes,completed.geometry.overlap_percent)}`:
    !plan||plan.error?'Nie wykonano':passSummary(passes,overlap)+' · do wykonania';
  return <section class="service-panel profile-panel profile-workflow">
    <header class="profile-workflow-heading"><h2>Profile</h2>{operationSelector}</header>
    <div class="profile-picker">
      <AppSelect id="profile-choice" label="Profil frezu V" value={creating?'':selected.id} placeholder={creating?'Nowy profil':'Wybierz profil'} disabled={locked||dirty||creating}
        onChange={async id=>{if(await controller.send({action:'profile_select',profile_id:id})){cancel();setStep(1);}}}
        options={(store?.profiles||[defaultProfile]).map(profile=>({value:profile.id,label:`${profile.name}${profile.draft?' · szkic':''}`}))}/>
      <button id="profile-new" class="profile-create" type="button" disabled={locked||creating||dirty} onClick={()=>{setCreating(true);setStep(1);}}><IconPlus size={19} aria-hidden="true"/>Nowy profil</button>
    </div>
    <ProfileStep number={1} title="Ustawienia" open={!cycleActive&&step===1} disabled={cycleActive||creating||dirty} onToggle={()=>choose(1)}
      summary={creating?'Nowy profil · wprowadzanie danych':dirty?'Niezapisane zmiany':`Zapisane · ${selected.name}`}>
      <ProfileSettings key={`${selected.fingerprint}-${creating}-${reset}`} controller={controller} profile={selected} creating={creating}
        locked={locked} ask={ask} onDirty={setDirty} onCancel={cancel} onSaved={()=>{cancel();setStep(2);}}/>
    </ProfileStep>
    <ProfileStep number={2} title="Test" open={cycleActive||step===2} disabled={creating||dirty||cycleActive} onToggle={()=>choose(2)}
      summary={testSummary}>
      <p class="profile-test-lead"><strong>Zero Z → mapa 3 × 3 → frezowanie</strong><span>Bieżące X/Y to zero testu</span></p>
      <div class="profile-test-grid">
        {probePlan&&!probePlan.error?<TestPreview plan={probePlan} map={cycleActive?map:null} origin={service.origin}/>:<p class="field-error" role="status">{probePlan?.error||'Oczekiwanie na plan testu.'}</p>}
        <div class="profile-test-controls">
          <div class="profile-test-options">
            <fieldset class="profile-fieldset"><legend>Przejazdy</legend><div class="profile-pass-buttons">{[1,2].map(value=><button key={value} type="button" aria-pressed={passes===value} disabled={busy} onClick={()=>setPasses(value)}>{value}</button>)}</div></fieldset>
            {passes===2&&<AppSelect id="profile-test-overlap" label="Zakładka" options={overlapChoices} value={String(overlap)} disabled={busy} onChange={value=>setOverlap(Number(value))}/>}
          </div>
          {probePlan&&!probePlan.error&&<div class="profile-test-estimate">
            <strong>Rowek: {grooveMm(probePlan.diameter)} mm{probePlan.passes===2?` → ok. ${grooveMm(probePlan.total_mm)} mm`:''}</strong>
            <small>{probePlan.diameter_source==='calibrated'?'Z modelu kalibracji':'Z geometrii frezu'} · zagłębienie {size(probePlan.settings.depth)} mm</small>
            <small>Posuw XY {size(probePlan.settings.feed)} · wejście Z {size(probePlan.settings.plunge)} mm/min · wrzeciono {size(probePlan.settings.power/10)}%</small>
            {probePlan.settings.corner_feed!=null&&probePlan.settings.corner_feed<probePlan.settings.feed&&
              <small>Posuw na zakrętach {size(probePlan.settings.corner_feed)} mm/min · {size(probePlan.corner_zone_mm)} mm przed i za zakrętem</small>}
            {probePlan.passes===2&&<small>Odstęp torów: {grooveMm(probePlan.step_mm)} mm. Drugi tor na zewnątrz.</small>}</div>}
          {cycle&&<p role="status">{cycleLabels[cycle.phase]}{cycle.phase==='probing'?` · ${map?.samples?.length||0}/9 punktów`:''}</p>}
          {cycle?.error&&<p class="field-error" role="alert">{cycle.error}</p>}
          {!busy&&waitReason&&<p class="service-hint" role="status">{waitReason}</p>}
          {cycleActive&&activeStates.includes(service.job?.state)&&<progress max={service.job.total||1} value={service.job.acknowledged||0} aria-label="Postęp frezowania wzoru"/>}
          <div class="button-row profile-actions">
            {cycleActive?<button class="stop" type="button" onClick={()=>controller.send({action:controller.probing.value?'probe_stop':'job_stop'},true)}>Stop testu</button>:
              <button id="profile-test-start" class="primary" type="button" disabled={!canProbe} onClick={()=>ask('profile_test_start',{
                ...plan.settings,profile_id:selected.id,profile_fingerprint:selected.fingerprint,session:service.session||null,position:[...cnc.position],fixed_probe:true,
                passes,overlap_percent:passes===2?overlap:0})}>Uruchom test</button>}
          </div>
        </div>
      </div>
      <p class="service-hint">Ustaw frez nad świeżą miedzią. Limit zjazdu: {probeNumber(probeDistanceLimit(cnc,1.4))} mm. Poprowadź przewód sondy poza polem ruchu. Zero X/Y projektu pozostaje zachowane.</p>
    </ProfileStep>
    <ProfileStep number={3} title="Kalibracja" open={!cycleActive&&step===3} disabled={creating||dirty||cycleActive} onToggle={()=>choose(3)}
      summary={trial?'Do wpisania pomiar':savedTrial?.calibration_method?`Zapisana · ${methodLabel(savedTrial.calibration_method)}`:proof?'Zapisana · potwierdzona':selected.model?'Zapisana · bez potwierdzenia':'Brak danych'}>
      {selected.id==='default'?<p class="service-hint">Aby zapisać pomiary kalibracyjne, utwórz własny profil.</p>:
        <CalibrationForm key={`${selected.fingerprint}-${trial?.trial_id||''}`} trial={trial} profile={selected} controller={controller} locked={locked}/>}
    </ProfileStep>
  </section>;
}

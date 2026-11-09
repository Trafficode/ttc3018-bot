import {useEffect, useState} from 'preact/hooks';
import {RetentionSelect} from './RetentionSelect.jsx';
import {IconCheck, IconTool, IconArrowRight} from '@tabler/icons-preact';
import './pcb-flow.css';
import {Disclosure,FieldHelp} from './FieldHelp.jsx';
import {PcbNumber} from './PcbField.jsx';
import {pcbFields,friendlyError} from './pcb-fields.js';



export async function flowApi(controller, url, options={}) {
  const response=await fetch(url,{...options,cache:'no-store',headers:{'X-PiloMill-Token':controller.data.value?.control_token || '',...(options.body ? {'Content-Type':'application/json'} : {})},signal:AbortSignal.timeout(15000)});
  if(!response.ok){const value=await response.json();throw new Error(value.error || 'Zlecenie jest niedostępne.');}
  return response;
}

export function FlowSetup({source, controller, api, onPrepared, locked, filename,onOpenProfiles}) {
  const [store,setStore]=useState(null),[profileId,setProfileId]=useState(''),[thickness,setThickness]=useState('');
  const [skin,setSkin]=useState(null),[retention,setRetention]=useState(null);
  const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const profile=store?.profiles.find(value=>value.id===profileId);
  const active=controller.cnc.value.calibration_profiles?.selected;
  const matches=profile?.isolation.id===active?.id && profile?.isolation.fingerprint===active?.fingerprint;
  useEffect(()=>{let alive=true;api('/api/pcb-profiles').then(response=>response.json()).then(value=>{if(alive){setStore(value);setProfileId(value.active || value.profiles[0]?.id || '');}}).catch(cause=>{if(alive)setError(cause.message);});return()=>{alive=false;};},[]);
  const material={thicknessMm:Number(thickness),skinMm:Number(skin ?? profile?.values.skinMm),retention:retention ?? profile?.values.retention};
  const depth=material.retention==='skin' ? material.thicknessMm-material.skinMm : material.thicknessMm+Number(profile?.values.breakthroughMm);
  const valid=!!profile && thickness!=='' && Number.isFinite(material.thicknessMm) && material.thicknessMm>=.3 && material.thicknessMm<=3 && material.skinMm>=.15 && material.skinMm<=.5 && material.skinMm>profile.values.uncertaintyMm && material.thicknessMm>(material.retention==='skin'?material.skinMm:profile.values.tabHeightMm) && depth<=profile.values.cuttingLengthMm;
  async function select(id){setBusy(true);setError('');try{const value=store.profiles.find(item=>item.id===id);await api('/api/pcb-profiles/select',{method:'POST',body:JSON.stringify({id,fingerprint:value.fingerprint})});await controller.refresh(true);setProfileId(id);setSkin(null);setRetention(null);setConfirmed(false);}catch(cause){setError(friendlyError(cause.message));}finally{setBusy(false);}}
  async function prepare(event){event.preventDefault();if(!valid || !confirmed || !matches)return;setBusy(true);setError('');try{const response=await api('/api/cam/prepare',{method:'POST',body:JSON.stringify({packageId:source.id,name:filename,profileFingerprint:active.fingerprint,confirmedDatum:true,confirmedSetup:true,processProfileId:profile.id,processFingerprint:profile.fingerprint,material})});onPrepared(await response.json());}catch(cause){setError(friendlyError(cause.message));}finally{setBusy(false);}}
  if(!store)return <p role="status">{error || 'Wczytywanie profili obróbki…'}</p>;
  if(store.error)return <p role="alert">{store.error}</p>;
  if(!store.profiles.length)return <section class="process-onboarding"><strong>Jeden profil zamiast ustawiania narzędzi przy każdej płytce</strong><p>Zapisz parametry swojego zestawu. Przy zleceniu zostaną profil i zmierzona grubość laminatu.</p><button type="button" onClick={onOpenProfiles}>Ustaw profil obróbki</button>{error && <p role="alert">{error}</p>}</section>;
  return <form class="pcb-setup simple-setup" onSubmit={prepare}>
    <div class="job-basics"><div class="pcb-field"><div class="field-caption"><label for="pcb-process-profile">Profil obróbki</label><FieldHelp id="pcb-process-profile" label="Profil obróbki">Zapisany zestaw kalibracji frezu V, parametrów wierteł, frezu Ø1 mm i mocowania. Posuwów i wrzeciona nie wpisujesz przy każdym PCB.</FieldHelp></div><select id="pcb-process-profile" value={profileId} disabled={locked || busy} onChange={event=>select(event.currentTarget.value)}>{store.profiles.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></div><PcbNumber name="thicknessMm" prefix="pcb" value={thickness} disabled={locked || busy} onChange={value=>{setThickness(value);setConfirmed(false);}}/></div>
    <div class="job-recipe"><small>{profile.isolation.name} · frez Ø1 mm</small><button type="button" class="text-button" disabled={busy} onClick={onOpenProfiles}>Edytuj profile</button></div>
    {thickness && valid && <p class="job-depth" role="status">Obrys <strong>{depth.toFixed(2)} mm</strong> · {material.retention==='skin' ? `zostaje ${material.skinMm} mm` : '4 mostki'}</p>}
    {thickness && !valid && <p role="alert">Sprawdź grubość, pozostawioną warstwę oraz długość ostrzy zapisaną w profilu.</p>}
    <Disclosure title="Materiał i mocowanie"><dl class="setup-facts">{['backingMm','clearanceMm','uncertaintyMm'].map(key=><div key={key}><dt>{pcbFields[key].label}<FieldHelp id={`job-${key}`} label={pcbFields[key].label}>{pcbFields[key].help}</FieldHelp></dt><dd>{profile.values[key]} {pcbFields[key].unit}</dd></div>)}</dl><small>Wartości zapisane w profilu. Inny podkład lub mocowanie? Zaktualizuj profil.</small><RetentionSelect id="job-retention" value={material.retention} disabled={locked || busy} onChange={value=>{setRetention(value);setConfirmed(false);}}/>{material.retention==='skin' && <PcbNumber name="skinMm" prefix="job" value={skin ?? profile.values.skinMm} disabled={busy} onChange={value=>{setSkin(value);setConfirmed(false);}}/>}<p class="pcb-help">{source.project.side} · wspólne zero X/Y przez całe zlecenie. Pomiary Z wymagają ciągłej ramy miedzi co najmniej 2 mm wokół PCB.</p></Disclosure>
    {!matches && <p class="profile-mismatch">Zestaw używa innej kalibracji frezu V. <button type="button" disabled={busy} onClick={()=>select(profile.id)}>Użyj tego zestawu</button></p>}
    <label class="cam-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.currentTarget.checked)}/><span>Sprawdzone mocowanie, prześwit oraz ramka miedzi do pomiaru Z.</span></label>
    {controller.cnc.value.connected && <p>Rozłącz CNC przed obliczeniem programów.</p>}{error && <p role="alert">{error}</p>}
    <button type="submit" class="primary cam-primary" disabled={locked || busy || !valid || !confirmed || !matches || controller.cnc.value.connected}>{busy?'Zapisywanie…':'Przygotuj PCB'}</button>
  </form>;
}

export function FlowRun({item,controller,api,locked,onLoaded,onPrepare,onOpenZero}) {
  const [progress,setProgress]=useState(null),[error,setError]=useState(''),[tool,setTool]=useState(false),[reference,setReference]=useState(false),[busy,setBusy]=useState(false);
  const sequence=item.report?.sequence || [];
  const index=progress?.completed.length || 0, operation=sequence[index];
  useEffect(()=>{setTool(false);setReference(false);},[index]);
  useEffect(()=>{let alive=true;async function update(){try{const response=await api(`/api/cam/flow/${item.id}`);const value=await response.json();if(alive)setProgress(value);}catch(cause){if(alive)setError(cause.message);}}update();const timer=setInterval(update,2000);return()=>{alive=false;clearInterval(timer);};},[item.id]);
  async function load() {
    setBusy(true);setError('');
    try{await api('/api/cam/load-stage',{method:'POST',body:JSON.stringify({id:item.id,index,confirmedTool:tool,confirmedReference:reference})});await controller.refresh(true);onLoaded?.('Etap wczytany. Przygotuj Z; Start pozostaje osobnym potwierdzeniem.');}
    catch(cause){setError(cause.message);}finally{setBusy(false);}
  }
  const loaded=progress?.loaded?.jobId===controller.cnc.value.job?.id && !progress?.requiresReload && !['failed','stopped'].includes(controller.cnc.value.job?.state);
  return <section class="pcb-run" aria-label="Wykonanie PCB">
    <div class="pcb-run-heading"><strong>Wykonanie PCB</strong><span>{index} / {sequence.length} operacji</span></div>
    <ol class="pcb-steps">{['isolation','drilling','outline'].map((kind,phase)=><li key={kind} class={operation?.kind===kind ? 'current' : ''}><b>{phase+1}</b><span>{['Ścieżki','Otwory','Obrys'][phase]}</span></li>)}</ol>
    <p class="pcb-material">Laminat {item.workflow.thicknessMm} mm · {item.workflow.retention==='skin' ? `warstwa ${item.workflow.skinMm} mm` : '4 mostki'} · jedno mocowanie</p>
    {!operation ? <p role="status"><IconCheck size={18}/>Wszystkie operacje zakończone przez sterownik. Oddzielenie i kontrola PCB pozostają ręczne.</p> : <>
      <h3><IconTool size={18}/>{operation.title}</h3><p>{operation.kind==='drilling' ? `${operation.holes} otworów · głębokość ${operation.depthMm.toFixed(2)} mm z uwzględnieniem stożka wiertła` : `Głębokość ${operation.depthMm.toFixed(2)} mm${operation.passes ? ` · ${operation.passes} przejść` : ''}`}</p>
      {loaded ? <div class="pcb-next" role="status"><strong>{controller.cnc.value.job?.state==='running' ? 'Trwa obróbka' : 'Etap wczytany'}</strong><p>{operation.zPreparation==='point' ? 'Wykonaj nowy pomiar Z na ciągłej miedzi ramy. Następnie wróć do Plik i wybierz Frezowanie.' : operation.kind==='outline' ? 'Zmierz 8 punktów ramy miedzi wokół PCB, następnie przejdź do Frezowania.' : 'Wykonaj mapę Z co najmniej 3×3, następnie przejdź do Frezowania.'} Zdejmij krokodylek przed Startem.</p>{(onPrepare || onOpenZero) && <button type="button" disabled={locked} onClick={operation.zPreparation==='point' ? onOpenZero : onPrepare}>{operation.zPreparation==='point' ? 'Przejdź do pomiaru zera Z' : 'Przygotuj mapę Z'}</button>}</div> : <>
        <label class="cam-confirm"><input type="checkbox" checked={tool} onChange={event=>setTool(event.currentTarget.checked)}/><span>Zamontowane narzędzie: {operation.title}. {operation.kind!=='isolation' && 'Użyte będą parametry mechaniczne bez korekty frezu V.'}</span></label>
        <label class="cam-confirm"><input type="checkbox" checked={reference} onChange={event=>setReference(event.currentTarget.checked)}/><span>Zero X/Y i mocowanie zachowane. Miejsce pomiaru Z ma pewny kontakt elektryczny i nie jest otworem ani rowkiem.</span></label>
        <button type="button" class="cam-primary" disabled={locked || busy || !tool || !reference || item.stale || !progress} onClick={load}><IconArrowRight size={17}/>Wczytaj etap i przygotuj Z</button>
      </>}
      {progress?.requiresReload && <p role="alert">Wczytany plik lub sesja serwera zmieniły się. Powtórz przygotowanie bieżącego etapu.</p>}
    </>}
    {error && <p role="alert">{error}</p>}
    <details><summary>Operacje i historia</summary><ol class="pcb-history">{sequence.map((value,position)=><li key={value.file}>{position<index ? <IconCheck size={16}/> : <span>{position+1}</span>}<span>{value.title}<small>{position<index ? 'Zakończono' : position===index ? 'Bieżąca operacja' : 'Oczekuje'}</small></span></li>)}</ol></details>
  </section>;
}

export function ActivePcbFlow({controller,locked,onPrepare,onOpenZero}) {
  const id=controller.cnc.value.job?.pcb_flow?.id;
  const [item,setItem]=useState(null),[error,setError]=useState('');
  const api=(url,options)=>flowApi(controller,url,options);
  useEffect(()=>{setItem(null);if(!id)return;let alive=true;api('/api/cam').then(response=>response.json()).then(value=>{if(alive)setItem(value.programs.find(entry=>entry.id===id));}).catch(cause=>{if(alive)setError(cause.message);});return()=>{alive=false;};},[id]);
  if(!id)return null;
  return <>{error && <p role="alert">{error}</p>}{item && <FlowRun item={item} controller={controller} api={api} locked={locked} onPrepare={onPrepare} onOpenZero={onOpenZero}/>}</>;
}

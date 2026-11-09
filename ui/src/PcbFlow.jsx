import {useEffect, useState} from 'preact/hooks';
import {IconCheck, IconTool, IconArrowRight} from '@tabler/icons-preact';
import './pcb-flow.css';

const numericFields = [
  ['thicknessMm','Grubość laminatu','mm',.3,3],
  ['skinMm','Pozostawiona warstwa','mm',.15,.5],
  ['uncertaintyMm','Budżet błędu grubości i Z','mm',.01,.2],
  ['backingMm','Grubość drewnianego podkładu','mm',1,50],
  ['breakthroughMm','Zapas przejścia w podkład','mm',.05,1],
  ['drillPointAngleDeg','Kąt wierzchołkowy wiertła','°',60,150],
  ['drillFeed','Posuw Z wiercenia','mm/min',1,100],
  ['drillPower','Wrzeciono wiercenia','S',1,1000],
  ['millFeed','Posuw XY frezu Ø1 mm','mm/min',1,300],
  ['millPlunge','Posuw Z frezu Ø1 mm','mm/min',1,100],
  ['millPower','Wrzeciono frezu Ø1 mm','S',1,1000],
  ['stepDownMm','Głębokość jednego przejścia','mm',.02,.5],
  ['cuttingLengthMm','Długość robocza frezu Ø1 mm','mm',.5,15],
  ['tabWidthMm','Szerokość mostka','mm',2,6],
  ['tabHeightMm','Wysokość mostka','mm',.2,.8]
];

export async function flowApi(controller, url, options={}) {
  const response=await fetch(url,{...options,cache:'no-store',headers:{'X-PiloMill-Token':controller.data.value?.control_token || '',...(options.body ? {'Content-Type':'application/json'} : {})},signal:AbortSignal.timeout(15000)});
  if(!response.ok){const value=await response.json();throw new Error(value.error || 'Zlecenie jest niedostępne.');}
  return response;
}

export function FlowSetup({source, controller, api, onPrepared, locked, filename}) {
  const [values,setValues]=useState(()=>{
    const defaults={thicknessMm:'',skinMm:'0.2',uncertaintyMm:'0.05',backingMm:'',breakthroughMm:'0.2',drillPointAngleDeg:'118',drillFeed:'',drillPower:'',millFeed:'',millPlunge:'',millPower:'',stepDownMm:'',cuttingLengthMm:'',tabWidthMm:'3',tabHeightMm:'0.3',retention:'skin',clearanceMm:'3'};
    try{const saved=JSON.parse(localStorage.getItem('bark:pcb-tool-settings') || '{}');for(const key of Object.keys(defaults))if(key!=='thicknessMm' && typeof saved[key]==='string')defaults[key]=saved[key];}catch{}
    return defaults;
  });
  useEffect(()=>{const {thicknessMm,...saved}=values;try{localStorage.setItem('bark:pcb-tool-settings',JSON.stringify(saved));}catch{}},[values]);
  const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const profile=controller.cnc.value.calibration_profiles?.selected;
  const value=key=>Number(String(values[key]).replace(',','.'));
  const depth=values.retention==='skin' ? value('thicknessMm')-value('skinMm') : value('thicknessMm')+value('breakthroughMm');
  const valid=numericFields.every(([key,label,unit,min,max])=>values[key]!=='' && Number.isFinite(value(key)) && value(key)>=min && value(key)<=max) && value('skinMm')>value('uncertaintyMm') && value('thicknessMm')>(values.retention==='skin' ? value('skinMm') : value('tabHeightMm')) && value('cuttingLengthMm')>=depth && value('clearanceMm')>=1 && value('clearanceMm')<=10;
  function field(key) {
    const [,label,unit,min,max]=numericFields.find(item=>item[0]===key) || [key,'Wycofanie Z','mm',1,10];
    return <label class="pcb-field" key={key} for={`pcb-${key}`}><span>{label}</span><div><input id={`pcb-${key}`} type="number" required min={min} max={max} step="any" value={values[key]} disabled={busy} onInput={event=>setValues({...values,[key]:event.currentTarget.value})}/><small>{unit}</small></div></label>;
  }
  async function prepare(event) {
    event.preventDefault();setError('');if(!valid || !confirmed)return;setBusy(true);
    const workflow={...Object.fromEntries(numericFields.map(([key])=>[key,value(key)])),retention:values.retention,millDiameterMm:1,confirmedSetup:true};
    try{const response=await api('/api/cam/prepare',{method:'POST',body:JSON.stringify({packageId:source.id,name:filename,profileFingerprint:profile.fingerprint,clearanceMm:value('clearanceMm'),confirmedDatum:true,workflow})});onPrepared(await response.json());}
    catch(cause){setError(cause.message);}finally{setBusy(false);}
  }
  return <form class="pcb-setup" onSubmit={prepare}>
    <ol class="pcb-steps" aria-label="Etapy wykonania PCB">{['Ścieżki','Otwory','Obrys'].map((text,index)=><li key={text}><b>{index+1}</b><span>{text}</span></li>)}</ol>
    <div class="pcb-form-grid">{field('thicknessMm')}{field('skinMm')}</div>
    <div class="pcb-depth" role="status"><span>Obrys · frez Ø1 mm</span><strong>{values.thicknessMm && depth>0 ? `${depth.toFixed(2)} mm w głąb` : 'Wpisz zmierzoną grubość laminatu'}</strong><small>{values.retention==='skin' ? 'Pozostawiona cienka warstwa do oddzielenia PCB' : 'Pełne cięcie z czterema mostkami'}</small></div>
    <details><summary>Materiał i mocowanie</summary><div class="pcb-form-grid">{field('backingMm')}{field('uncertaintyMm')}{field('clearanceMm')}</div><p>Wspólne G54: lewy dolny narożnik gotowego PCB od strony obróbki. {source.project.side==='B.Cu' ? 'B.Cu: odbicie X.' : 'F.Cu: bez odbicia.'} Zachowaj zero X/Y i mocowanie przez całe zlecenie.</p></details>
    <details><summary>Narzędzia i parametry · wymagane</summary><p>Ścieżki: {profile?.name || 'wybierz profil'} · osobne ustawienia wierteł i frezu płaskiego. Wpisz parametry dla swoich narzędzi; S jest skalą sterownika, nie RPM.</p><div class="pcb-form-grid">{['drillPointAngleDeg','drillFeed','drillPower','breakthroughMm','millFeed','millPlunge','millPower','stepDownMm','cuttingLengthMm'].map(field)}</div></details>
    <details><summary>Sposób oddzielenia i pomiar Z</summary><label>Sposób mocowania obrysu<select value={values.retention} onChange={event=>setValues({...values,retention:event.currentTarget.value})}><option value="skin">Cienka warstwa na całym obwodzie</option><option value="tabs">Cztery mostki</option></select></label>{values.retention==='tabs' && <div class="pcb-form-grid">{field('tabWidthMm')}{field('tabHeightMm')}</div>}<p>Ścieżki: mapa powierzchni. Każde wiertło: nowe zero Z w jednym punkcie. Obrys: osiem pomiarów na nieobrobionej, elektrycznie ciągłej ramie laminatu, poza PCB. Środek nie jest sondowany. Grubość i budżet błędu wymagają własnego pomiaru; mapa Z nie mierzy grubości laminatu.</p></details>
    <label class="cam-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.currentTarget.checked)}/><span>Potwierdzam stronę i zero PCB, stabilny podkład, prześwit nad mocowaniami oraz nieobrobioną ramę miedzi co najmniej 2 mm wokół PCB do pomiarów Z. Narzędzia i wartości odpowiadają mojemu zestawowi.</span></label>
    {!valid && <p class="pcb-help">Uzupełnij grubość, podkład i parametry narzędzi. Zlecenie nie używa domyślnych posuwów frezowania.</p>}
    {controller.cnc.value.connected && <p>Rozłącz CNC przed obliczeniem programów.</p>}
    {error && <p role="alert">{error}</p>}
    <button class="primary cam-primary" type="submit" disabled={locked || busy || !valid || !confirmed || !profile?.model || controller.cnc.value.connected}>{busy ? 'Zapisywanie…' : 'Przygotuj całe PCB na RPi'}</button>
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

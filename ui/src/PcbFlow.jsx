import {useEffect, useState} from 'preact/hooks';
import {IconCheck, IconTool, IconArrowRight} from '@tabler/icons-preact';
import './pcb-flow.css';



export async function flowApi(controller, url, options={}) {
  const response=await fetch(url,{...options,cache:'no-store',headers:{'X-PiloMill-Token':controller.data.value?.control_token || '',...(options.body ? {'Content-Type':'application/json'} : {})},signal:AbortSignal.timeout(15000)});
  if(!response.ok){const value=await response.json();throw new Error(value.error || 'Zlecenie jest niedostępne.');}
  return response;
}

export {FlowSetup} from './FlowSetup.jsx';

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
    <ol class="pcb-steps">{['isolation','drilling','outline'].filter(kind=>sequence.some(value=>value.kind===kind)).map((kind,phase)=><li key={kind} class={operation?.kind===kind ? 'current' : ''}><b>{phase+1}</b><span>{{isolation:'Ścieżki',drilling:'Otwory',outline:'Obrys'}[kind]}</span></li>)}</ol>
    <p class="pcb-material">Laminat {item.workflow.thicknessMm} mm{item.workflow.retention ? ` · ${item.workflow.retention==='skin' ? `warstwa ${item.workflow.skinMm} mm` : item.workflow.retention==='tabs' ? 'mostki' : 'na wylot'}` : ''} · jedno mocowanie</p>
    {!operation ? <p role="status"><IconCheck size={18}/>Wszystkie operacje zakończone przez sterownik. Oddzielenie i kontrola PCB pozostają ręczne.</p> : <>
      <h3><IconTool size={18}/>{operation.title}</h3><p>{operation.kind==='drilling' ? `${operation.holes} otworów · głębokość ${operation.depthMm.toFixed(2)} mm${operation.drillOverrunMm!==undefined ? ` · czubek ${operation.drillOverrunMm} mm w podkładzie` : ' z uwzględnieniem stożka wiertła'}` : `Głębokość ${operation.depthMm.toFixed(2)} mm${operation.passes ? ` · ${operation.passes} przejść` : ''}`}</p>
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

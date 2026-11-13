import {useEffect,useRef,useState} from 'preact/hooks';
import {IconPlayerPause,IconPlayerPlay,IconArrowDown,IconCheck,IconLoader2} from '@tabler/icons-preact';
import {ToolpathPreview} from './CamPanel.jsx';
import {createSurfacePlan,defaultSurfaceSettings,surfaceRequest} from './surface-plan.js';

export function ProjectOperation({controller,ask,api,setupId,stageId,stage,busy,onRun,probeDistance,probeFeed,through}){
  const [geometry,setGeometry]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[measureIntent,setMeasureIntent]=useState(false);
  const requestedJob=useRef(null);
  const cnc=controller.cnc.value, job=cnc.job||{};
  const operation=stage?.operation;
  const loaded=stage?.loaded&&job.pcb_flow?.id===stage.camId;
  const active=loaded&&controller.active.value;
  const probing=loaded&&cnc.z_probe?.active;
  const ready=loaded&&stage.zReady&&!stage.stale;
  const phase=stage?.done||ready||active&&!probing?2:stage?.state==='ready'&&!stage.stale?1:0;
  const manual=controller.manualReady.value;
  const canProbe=manual&&cnc.probe_tested&&cnc.probe_triggered===false;
  const bounds=loaded?job.bounds_mm:operation?.boundsMm||stage?.report?.boundsMm;
  const settings=bounds?{...defaultSurfaceSettings(bounds),perimeterOnly:stageId==='outline'}:null;
  const plan=bounds&&stageId!=='drilling'?createSurfacePlan(bounds,settings):null;
  const points=stageId==='drilling'?(loaded&&cnc.fresh&&Array.isArray(cnc.position)?[{x:cnc.position[0],y:cnc.position[1]}]:[]):plan?.points||[];

  useEffect(()=>{
    let alive=true;setGeometry(null);
    if(stage?.camId&&['ready','blocked'].includes(stage.state))api(`/api/cam/preview/${stage.camId}`).then(response=>response.json()).then(value=>{if(alive)setGeometry(value);}).catch(()=>{});
    return()=>{alive=false;};
  },[stage?.camId,stage?.state]);
  function probe(){
    if(stageId==='drilling')ask('probe_start');
    else{
      if(!job.bounds_mm)return;
      const options=surfaceRequest(job.bounds_mm,{...defaultSurfaceSettings(job.bounds_mm),perimeterOnly:stageId==='outline'});
      if(options.error){setError(options.error);return;}
      ask('surface_start',options);
    }
  }
  useEffect(()=>{
    if(measureIntent&&loaded&&job.id&&job.pcb_flow?.id===requestedJob.current){
      setMeasureIntent(false);probe();
    }
  },[measureIntent,loaded,job.id]);
  async function measure(){
    if(!canProbe||busy||loading)return;
    setError('');
    if(loaded){probe();return;}
    setLoading(true);
    try{
      const value=await(await api('/api/pcb-projects/load',{method:'POST',body:JSON.stringify({setupId,stage:stageId,confirmedTool:true,confirmedThroughCut:through})})).json();
      requestedJob.current=stage.camId;onRun(value);await controller.refresh(true);setMeasureIntent(true);
    }catch(cause){setError(cause.message);}
    finally{setLoading(false);}
  }
  const pending=!stage||stage.state==='running';
  const problem=stage?.error || (stage?.state==='blocked'?stage.report?.checks?.findings?.[0]?.message:null);
  const probeHint=!cnc.connected?'Połącz CNC przy stanowisku.':!cnc.fresh?'Oczekiwanie na aktualny odczyt CNC.':cnc.state!=='Idle'&&!active?'CNC musi być bezczynne.':!cnc.probe_tested?'Zewrzyj i rozewrzyj sondę, aby sprawdzić styk.':cnc.probe_triggered!==false?'Rozewrzyj sondę przed pomiarem.':'';
  return <section class="project-operation" aria-label="Przygotowanie i wykonanie etapu">
    <ol class="operation-phases" aria-label="Fazy etapu">{['Przygotowanie','Pomiar Z','Obróbka'].map((name,index)=><li aria-current={phase===index?'step':undefined} class={phase===index?'current':phase>index?'complete':''}><span>{phase>index?<IconCheck size={14}/>:index+1}</span>{name}</li>)}</ol>
    {geometry&&<ToolpathPreview geometry={geometry} probePoints={points}/>}
    {operation&&<p class="project-tool">{operation.title}{stageId==='drilling'&&` · narzędzie ${(stage.index||0)+1} z ${stage.total}`}</p>}
    {stage?.done?<p class="project-success" role="status"><IconCheck size={19}/>Etap wykonany. Możesz wybrać inny etap.</p>:probing?<>
      <p class="project-measuring" role="status">Pomiar Z · {cnc.z_probe.completed||0} / {cnc.z_probe.total||1}</p>
      <progress max={cnc.z_probe.total||1} value={cnc.z_probe.completed||0} aria-label="Postęp pomiaru Z"/>
      <button type="button" class="stop project-primary" onClick={()=>controller.send({action:'probe_stop'},true)}>Przerwij pomiar</button>
    </>:active?<>
      <p role="status">{job.state==='paused'?'Obróbka wstrzymana':'Trwa obróbka'} · {job.acknowledged||0} / {job.total||0}</p>
      <progress max={job.total||1} value={job.acknowledged||0} aria-label="Postęp obróbki"/>
      <button type="button" class="project-primary" disabled={!cnc.fresh} onClick={()=>job.state==='paused'?ask('job_resume'):controller.send({action:'job_pause',job_id:job.id},true)}>{job.state==='paused'?<IconPlayerPlay size={18}/>:<IconPlayerPause size={18}/>}{job.state==='paused'?'Wznów obróbkę':'Pauza'}</button>
    </>:pending?<p class="project-message" role="status"><IconLoader2 size={18}/>Przygotowanie przejazdów dla etapu…</p>:problem||stage?.stale?<p role="alert">{problem||'Etap wymaga ponownego przeliczenia.'}</p>:ready?<>
      <p class="project-success" role="status"><IconCheck size={19}/>Z zmierzone</p><p class="project-hint">Zdejmij przewód pomiarowy przed obróbką.</p>
      <button type="button" class="primary project-primary" disabled={!manual} onClick={()=>ask('job_start')}><IconPlayerPlay size={19}/>{stageId==='drilling'?'Rozpocznij wiercenie':stageId==='outline'?'Rozpocznij wycinanie':'Rozpocznij frezowanie'}</button>
    </>:stage?.state==='ready'?<>
      <p class="project-message">Nowy pomiar Z wymagany</p>
      <p class="project-hint">Załóż wskazane narzędzie i ustaw je blisko nad ciągłą miedzią. Zachowaj zero X/Y.{stageId==='drilling'?' Pomiar jednego punktu; powtórz po każdej zmianie wiertła.':stageId==='outline'?' Pomiar 8 punktów ramy wokół PCB.':' Pomiar siatki 3 × 3.'}</p>
      {probeHint&&<p class="project-hint" role="status">{probeHint}</p>}
      {!cnc.connected?<button type="button" class="primary project-primary" disabled={controller.data.value?.cam_preparing||busy||!controller.connectReady.value} onClick={()=>ask('connect')}>Połącz CNC</button>:<button type="button" class="primary project-primary" disabled={!canProbe||loading||busy} onClick={measure}><IconArrowDown size={19}/>{loading?'Przygotowanie narzędzia…':stageId==='drilling'?'Zmierz Z dla wiertła':stageId==='outline'?'Zmierz Z dla frezu':'Zmierz powierzchnię Z'}</button>}
      {stageId==='drilling'&&<small class="project-hint">Limit szukania styku: {probeDistance} mm · posuw {probeFeed} mm/min</small>}
    </>:null}
    {error&&<p role="alert">{error}</p>}
  </section>;
}

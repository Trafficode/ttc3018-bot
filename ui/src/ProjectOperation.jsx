import {useEffect,useState} from 'preact/hooks';
import {IconPlayerPlay,IconPlayerPause,IconPlayerStop,IconCheck} from '@tabler/icons-preact';
import {AppSelect} from './AppSelect.jsx';
import {ToolpathPreview} from './CamPanel.jsx';
import {createSurfacePlan,defaultSurfaceSettings} from './surface-plan.js';

const titles={isolation:'Ścieżki',drilling:'Otwory THT',outline:'Obrys'};
export function ProjectOperation({controller,ask,api,setupId,stageId,stage,busy,xyReady,grid,onGrid,probeDistance,probeFeed,through,sourceGeometry,sourceError,profile,thickness,capability,profileError,prepare,onProfile,profiles=[]}){
  const [geometry,setGeometry]=useState(null),[error,setError]=useState('');
  const cnc=controller.cnc.value,job=cnc.job||{},cycle=cnc.project_cycle;
  const current=cycle?.setupId===setupId&&cycle?.stage===stageId?cycle:null;
  const running=current?.active;
  const loaded=stage?.loaded&&job.pcb_flow?.id===stage.camId;
  const visual=geometry||sourceGeometry,box=visual?.bounds;
  const margin=stageId==='outline'?Number(profile?.values?.millDiameterMm||1)/2:0;
  const sourceBounds=box?{X:[box[0]-margin,box[2]+margin],Y:[box[1]-margin,box[3]+margin]}:null;
  const bounds=loaded?job.bounds_mm:stage?.operation?.boundsMm||stage?.report?.boundsMm||sourceBounds;
  const plan=bounds&&stageId!=='drilling'?createSurfacePlan(bounds,{...defaultSurfaceSettings(bounds),...(stageId==='isolation'?grid:{}),perimeterOnly:stageId==='outline'}):null;
  const samples=cnc.surface_map?.samples||[];
  const points=stageId==='drilling'?(Array.isArray(cnc.position)?[{x:cnc.position[0],y:cnc.position[1]}]:[]):(plan?.points||[]).map(p=>({...p,z:running||current?.phase==='measured'?samples.find(s=>Math.abs(s.x-p.x)<.001&&Math.abs(s.y-p.y)<.001)?.z:undefined}));
  useEffect(()=>{let alive=true;setGeometry(null);if(stage?.camId&&['ready','blocked'].includes(stage.state))api(`/api/cam/preview/${stage.camId}`).then(r=>r.json()).then(v=>{if(alive)setGeometry(v);}).catch(()=>{});return()=>{alive=false;};},[stage?.camId,stage?.state]);
  const readyStock=Number.isFinite(Number(thickness))&&Number(thickness)>=.3&&Number(thickness)<=3;
  const canMeasure=xyReady&&controller.manualReady.value&&cnc.probe_tested&&cnc.probe_triggered===false&&!!bounds;
  const blocked=stage?.state==='blocked'&&!stage.stale&&stage.profile?.fingerprint===profile?.fingerprint;
  const canExecute=canMeasure&&readyStock&&!!profile&&!profileError&&capability?.available&&!stage?.done&&!blocked;
  const hint=!cnc.connected?'Połącz CNC w górnym pasku.':!xyReady?'Ustaw zero X/Y powyżej.':!cnc.fresh?'Oczekiwanie na odczyt CNC.':!cnc.probe_tested?'Sprawdź styk sondy z miedzią i odsuń frez.':cnc.probe_triggered!==false?'Rozewrzyj sondę przed pomiarem.':!readyStock?'Podaj grubość laminatu.':profileError||(!capability?.available?capability?.reason:'');
  function execute(measureOnly=false){
    if(measureOnly?!canMeasure:!canExecute)return;
    const body={setupId,stage:stageId,thicknessMm:Number(thickness),profileId:profile?.id,fingerprint:profile?.fingerprint,confirmedThroughCut:through,confirmed:true,fixed_probe:true,columns:grid.columns,rows:grid.rows,distance:Number(probeDistance),feed:Number(probeFeed),position:[...cnc.position]};
    const count=stageId==='drilling'?1:stageId==='outline'?8:grid.columns*grid.rows;
    const description=`${titles[stageId]}${profile?` · ${profile.name}`:''}${measureOnly?'':` · laminat ${thickness} mm`}.\n\n${measureOnly?'Pomiar Z bez frezowania i bez wymagania gotowego CAM.':'Potwierdzasz zamontowane narzędzie i mocowanie. Serwis przygotuje i sprawdzi przejazdy, zmierzy Z, a następnie automatycznie uruchomi wrzeciono i obróbkę.'}\nPomiar: ${count} punktów${stageId==='outline'?' na nieobrobionej ramie miedzi':''}. Pierwszy zjazd do styku: maks. ${stageId==='drilling'?probeDistance:'1,4'} mm. Wyłącz wrzeciono przed pomiarem i ustaw narzędzie blisko nad miedzią. Sprawdź całe pole pomiaru i przewód sondy na obudowie wrzeciona. Pozostań przy wyłączniku.${stageId==='drilling'?' Każda kolejna średnica wymaga wymiany wiertła i osobnego uruchomienia.':''}`;
    ask(measureOnly?'project_measure':'project_execute',{description,execute:async()=>{setError('');try{return await(await api(`/api/pcb-projects/${measureOnly?'measure':'execute'}`,{method:'POST',body:JSON.stringify(body)})).json();}catch(cause){setError(cause.message);throw cause;}}});
  }
  const problem=current?.phase==='failed'?current.error:stage?.error||stage?.report?.checks?.findings?.[0]?.message;
  const phase=running?current.phase:stage?.done?'completed':current?.phase==='measured'?'measured':stage?.state==='running'?'preparing':'ready';
  const text={preparing:'Przygotowanie przejazdów',loading:'Przygotowanie narzędzia',probing:`Pomiar Z · ${cnc.z_probe?.completed||0}/${cnc.z_probe?.total||1}`,cutting:job.state==='paused'?'Obróbka wstrzymana':'Trwa obróbka',completed:'Etap wykonany',measured:'Pomiar Z zakończony · bez obróbki',ready:blocked?'Geometria zablokowana':canExecute?'Gotowe do uruchomienia':'Przygotowanie stanowiska'}[phase]||'Etap zatrzymany';
  return <section class="project-operation stage-workspace" aria-label="Przygotowanie i wykonanie etapu">
    <div class="operation-layout"><div class="operation-visual">
      {visual?<ToolpathPreview geometry={visual} probePoints={points} findings={stage?.report?.checks?.findings||[]} showDatum compactLabel={`${titles[stageId]} · ${box[2]-box[0]} × ${box[3]-box[1]} mm · ${stageId==='drilling'?'punkt Z przy narzędziu':`${points.length} punktów Z`}${geometry?' · przejazdy CAM':' · layout PCB'}`}/>:<p class="preview-placeholder">{sourceError||'Wczytywanie layoutu PCB…'}</p>}
    </div><div class="operation-controls">
      <div class="stage-tool-heading"><h3>{titles[stageId]}</h3><span class="stage-status" role="status">{text}</span></div>
      {profiles.length>1?<AppSelect id={`project-profile-${stageId}`} label="Narzędzie" value={profile?.id||''} disabled={controller.active.value||busy} onChange={onProfile} options={profiles.map(p=>({value:p.id,label:p.name}))}/>:<p class="project-tool">Narzędzie: <strong>{profile?.name||'Brak profilu'}</strong></p>}
      {stage?.operation&&<p class="project-hint">{stage.operation.title}{stageId==='drilling'?` · wiertło ${(stage.index||0)+1}/${stage.total}`:''}</p>}
      {stageId==='isolation'?<div class="project-grid-settings"><div class="grid-counts">{[['columns','Punkty X'],['rows','Punkty Y']].map(([key,label])=><AppSelect id={`project-grid-${key}`} label={label} value={String(grid[key])} disabled={controller.active.value||busy} options={Array.from({length:9},(_,i)=>({value:String(i+3),label:String(i+3)}))} onChange={v=>onGrid({...grid,[key]:Number(v)})}/>)}</div><small>{grid.columns*grid.rows} punktów{plan&&!plan.error?` · rozstaw ${plan.spacingX.toFixed(1)} × ${plan.spacingY.toFixed(1)} mm`:''}</small></div>:<p class="project-hint">{stageId==='outline'?'8 punktów Z na zewnętrznej ramie miedzi.':'Świeży pomiar Z po każdej zmianie wiertła.'}</p>}
      {hint&&!running&&<p class="project-hint" role="status">{hint}</p>}
      {stage?.done?<p class="project-success"><IconCheck size={18}/>Etap wykonany</p>:running?<div class="stage-actions"><button type="button" class="stop" onClick={()=>controller.send({action:'project_cycle_stop'},true)}><IconPlayerStop size={18}/>Stop etapu</button>{phase==='cutting'&&<button type="button" disabled={!cnc.fresh} onClick={()=>job.state==='paused'?ask('job_resume'):controller.send({action:'job_pause',job_id:job.id},true)}>{job.state==='paused'?<IconPlayerPlay size={17}/>:<IconPlayerPause size={17}/>}{job.state==='paused'?'Wznów':'Pauza'}</button>}</div>:<button type="button" class="primary project-primary" disabled={!canExecute||busy} onClick={()=>execute()}><IconPlayerPlay size={18}/>Wykonaj etap</button>}
      {running&&<progress max={phase==='probing'?cnc.z_probe?.total||1:job.total||1} value={phase==='probing'?cnc.z_probe?.completed||0:job.acknowledged||0} aria-label="Postęp etapu"/>}
      {!running&&<div class="stage-secondary"><button type="button" class="text-button" disabled={!canMeasure||busy} onClick={()=>execute(true)}>Tylko pomiar Z</button>{(problem||stage?.stale)&&<button type="button" class="text-button" disabled={controller.active.value||busy||!readyStock||!profile} onClick={prepare}>Ponów przygotowanie</button>}</div>}
      {(problem||error)&&<p class="stage-error" role="alert">{error||problem}</p>}
      {through&&<p class="project-hint">Cięcie na wylot · mocowanie potwierdzone.</p>}
    </div></div>
  </section>;
}

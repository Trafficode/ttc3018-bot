import {useEffect,useRef,useState} from 'preact/hooks';
import {IconCircuitGround,IconGridDots,IconCut,IconChevronLeft,IconRefresh,IconFileImport} from '@tabler/icons-preact';
import {AppSelect} from './AppSelect.jsx';
import {PcbNumber} from './PcbField.jsx';
import {flowApi} from './PcbFlow.jsx';
import {ProjectOperation} from './ProjectOperation.jsx';
import {canEditStock} from './project-setup.js';
import './project-flow.css';

export const projectStages=[{id:'isolation',label:'Ścieżki',title:'Frezowanie izolacyjne',icon:IconCircuitGround},
  {id:'drilling',label:'Otwory',title:'Otwory THT',icon:IconGridDots},
  {id:'outline',label:'Obrys',title:'Wycięcie PCB',icon:IconCut}];
const legacyCapabilities={isolation:{available:true},outline:{available:true},
  drilling:{available:false,reason:'Wyślij ponownie projekt z aktualnego Tractora, aby rozpoznać otwory THT.'}};
const phaseText=stage=>stage?.done?'Wykonano':stage?.stale?'Do przygotowania':stage?.state==='running'?'Przygotowanie':stage?.zReady?'Z gotowe':stage?.state==='ready'?(stage.report?.padTrimReview?.requiresAcceptance?'Zmiana padów':'Pomiar Z'):stage?.state==='failed'||stage?.state==='blocked'?'Problem':'Do wykonania';

export function ProjectPanel({controller,ask,onManual,onPreparing,probeDistance,probeFeed,onMove}){
  const [packages,setPackages]=useState([]),[selected,setSelected]=useState('');
  const [kind,setKind]=useState('isolation'),[thickness,setThickness]=useState('');
  const [stockDraft,setStockDraft]=useState(''),[stockEditing,setStockEditing]=useState(true);
  const stockDraftRef=useRef('');
  const [toolStore,setToolStore]=useState(null),[choices,setChoices]=useState({});
  const [run,setRun]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [settingXY,setSettingXY]=useState(false);
  const setupPromise=useRef(null);
  const [sourceGeometry,setSourceGeometry]=useState(null),[sourceError,setSourceError]=useState('');
  const [grid,setGrid]=useState({columns:5,rows:5});
  const [stageErrors,setStageErrors]=useState({}),[through,setThrough]=useState(false);
  const packageRef=useRef(''),runRef=useRef(null),preparing=useRef(false),epoch=useRef(0),restoreAllowed=useRef(false);
  const api=(url,options)=>flowApi(controller,url,options);
  const cnc=controller.cnc.value;
  const source=packages.find(value=>value.id===selected);
  const cad=source?.files.filter(file=>file.kind==='cad')||[];
  const capabilities=cad[0]?.machining?.stages||legacyCapabilities;
  const vProfiles=(cnc.calibration_profiles?.profiles||[]).filter(profile=>profile.model&&profile.depth!==undefined);
  const available=stage=>stage==='isolation'?vProfiles:(toolStore?.profiles||[]).filter(profile=>!profile.kind||profile.kind===stage);
  const profile=stage=>available(stage).find(value=>value.id===choices[stage]) || available(stage).find(value=>value.id===(stage==='isolation'?cnc.calibration_profiles?.selected?.id:toolStore?.activeByKind?.[stage])) || available(stage)[0];
  const readyStock=thickness!==''&&Number.isFinite(Number(thickness))&&Number(thickness)>=.3&&Number(thickness)<=3;
  const stage=run?.stageStates?.[kind];
  const locked=controller.active.value||busy||settingXY||!!controller.pending.value;
  const stockLocked=!canEditStock({known:controller.known.value,active:controller.active.value,busy:busy||settingXY,pending:controller.pending.value,cnc});

  useEffect(()=>{setSourceGeometry(null);setSourceError('');if(!selected)return;let alive=true;api(`/api/pcb-projects/preview?packageId=${selected}`).then(r=>r.json()).then(v=>{if(alive)setSourceGeometry(v);}).catch(cause=>{if(alive)setSourceError(cause.message);});return()=>{alive=false;};},[selected]);
  async function ensureSetup(){
    if(runRef.current)return runRef.current;
    if(setupPromise.current)return setupPromise.current;
    const version=epoch.current,packageId=packageRef.current;
    const pending=(async()=>{
      const value=await(await api('/api/pcb-projects/setup',{method:'POST',body:JSON.stringify({packageId})})).json();
      if(version!==epoch.current)throw new Error('Projekt zmienił się. Wybierz go ponownie.');
      runRef.current=value.id;restoreAllowed.current=false;setRun(value);return value.id;
    })();
    setupPromise.current=pending;
    try{return await pending;}finally{if(setupPromise.current===pending)setupPromise.current=null;}
  }
  async function confirmXY(){
    if(!controller.manualReady.value||settingXY||!cnc.position?.every(Number.isFinite))return;
    const position=[...cnc.position],version=epoch.current;
    setSettingXY(true);setError('');
    try{
      const setupId=await ensureSetup();
      if(version!==epoch.current)throw new Error('Projekt zmienił się. Sprawdź przygotowanie ponownie.');
      const value=await(await api('/api/pcb-projects/xy',{method:'POST',body:JSON.stringify({setupId,mode:'set',position,confirmed:true})})).json();
      setRun(value);await controller.refresh(true);
    }catch(cause){setError(cause.message);}
    finally{setSettingXY(false);}
  }
  async function refreshSources(){
    try{const value=await (await api('/api/library')).json();setPackages(value.packages.filter(item=>!item.corrupt));setError('');
      const active=controller.cnc.value.job?.pcb_flow;
      if(!packageRef.current&&active?.packageId&&value.packages.some(item=>item.id===active.packageId)){chooseProject(active.packageId);setKind(active.kind);}
    }
    catch(cause){setError(cause.message);}
  }
  useEffect(()=>{if(controller.known.value)refreshSources();},[controller.known.value]);
  useEffect(()=>{let alive=true;async function refresh(){if(!controller.known.value)return;try{const value=await(await api('/api/pcb-profiles')).json();if(alive)setToolStore(value);}catch(cause){if(alive)setError(cause.message);}}refresh();const timer=setInterval(refresh,2500);return()=>{alive=false;clearInterval(timer);};},[]);
  useEffect(()=>{
    if(!selected)return;
    let alive=true;
    async function refresh(){
      try{
        const value=await(await api(`/api/pcb-projects?packageId=${selected}`)).json();
        if(!alive)return;
        const current=runRef.current;
        if(current){const found=value.runs.find(item=>item.id===current);if(found)setRun(found);}
        else if(restoreAllowed.current){
          restoreAllowed.current=false;
          const active=controller.cnc.value.job?.pcb_flow;
          const found=value.runs.find(item=>item.id===active?.projectSetupId);
          if(found){const map=controller.cnc.value.surface_map;if(active.kind==='isolation'&&map?.valid&&map.job_id===controller.cnc.value.job?.id&&map.columns>=3&&map.rows>=3)setGrid({columns:map.columns,rows:map.rows});runRef.current=found.id;setRun(found);setThickness(String(found.thicknessMm));stockDraftRef.current=String(found.thicknessMm);setStockDraft(stockDraftRef.current);setStockEditing(false);setKind(active.kind);setChoices(Object.fromEntries(Object.entries(found.stageStates||{}).filter(([,value])=>value.profile?.id).map(([key,value])=>[key,value.profile.id])));}
        }
      }catch(cause){if(alive)setError(cause.message);}
    }
    refresh();const timer=setInterval(refresh,1500);
    return()=>{alive=false;clearInterval(timer);};
  },[selected]);
  function chooseProject(id){
    epoch.current++;setupPromise.current=null;packageRef.current=id;runRef.current=null;restoreAllowed.current=!!id;
    setSelected(id);setThickness('');setRun(null);setChoices({});setThrough(false);setStageErrors({});setError('');
    stockDraftRef.current='';setStockDraft('');setStockEditing(true);
  }
  function newStock(value){
    const valid=value!==''&&Number.isFinite(Number(value))&&Number(value)>=.3&&Number(value)<=3;
    setStockEditing(!valid);
    if(value===thickness)return;
    if(run?.thicknessMm!==null){epoch.current++;setupPromise.current=null;runRef.current=null;setRun(null);}restoreAllowed.current=false;setThickness(value);setThrough(false);setStageErrors({});setError('');
  }
  function draftStock(value){stockDraftRef.current=value;setStockDraft(value);if(document.activeElement?.tagName!=='INPUT')newStock(value);}
  function changeProfile(stage,id){setChoices({...choices,[stage]:id});setStageErrors({...stageErrors,[stage]:null});setThrough(false);}
  async function prepare(stageId,force=false){
    const chosen=profile(stageId);
    if(!source||!readyStock||!chosen||preparing.current)return;
    preparing.current=true;setBusy(true);
    const version=epoch.current;
    try{
      const setupId=await ensureSetup();
      const response=await api('/api/pcb-projects/prepare',{method:'POST',body:JSON.stringify({
        packageId:source.id,setupId,stage:stageId,thicknessMm:Number(thickness),
        profileId:chosen.id,fingerprint:chosen.fingerprint,confirmedThroughCut:through})});
      const value=await response.json();
      if(version!==epoch.current)return;
      runRef.current=value.id;setRun(value);setStageErrors(errors=>({...errors,[stageId]:null}));setError('');
    }catch(cause){if(version===epoch.current && !/już oblicza|Poczekaj/.test(cause.message))setStageErrors(errors=>({...errors,[stageId]:cause.message}));}
    finally{preparing.current=false;setBusy(false);}
  }
  useEffect(()=>{onPreparing?.(busy||Object.values(run?.stageStates||{}).some(value=>value.state==='running'));},[busy,run]);

  if(!source){
    const latest=new Map();for(const item of packages){const key=item.project.id;if(!latest.has(key))latest.set(key,item);}
    return <section class="pcb-projects"><div class="project-list-heading"><h2>Projekty PCB</h2><button type="button" aria-label="Odśwież projekty" disabled={locked} onClick={refreshSources}><IconRefresh size={18}/></button></div>
      <p class="project-hint">Projekt zawiera ścieżki, otwory THT i obrys.</p>
      <div class="project-list">{[...latest.values()].map(item=><button type="button" key={item.id} disabled={locked} onClick={()=>chooseProject(item.id)}><strong>{item.project.name}</strong><span>{item.project.side} · {new Date(item.receivedAt).toLocaleDateString('pl-PL')}</span></button>)}</div>
      {!packages.length&&<p>Brak projektów. Wyślij projekt PCB z Tractora do kolekcji frezarki.</p>}
      {error&&<p role="alert">{error}</p>}
      <button type="button" class="text-button manual-import" disabled={locked} onClick={onManual}><IconFileImport size={17}/>Import pojedynczego pliku NC</button>
    </section>;
  }
  const chosen=profile(kind),capability=capabilities[kind];
  const profileMatches=!stage?.profile || stage.profile.fingerprint===chosen?.fingerprint;
  const profileError=(kind!=='isolation'&&toolStore?.error) || (!chosen?'Brak przygotowanego profilu dla tego etapu.':kind==='drilling'&&chosen.values?.drillOverrunMm===undefined?'Profil wiercenia wymaga aktualizacji przed użyciem.':'');
  return <section class="pcb-project">
    <button type="button" class="text-button project-back" disabled={locked} onClick={()=>chooseProject('')}><IconChevronLeft size={16}/>Projekty</button>
    <div class="project-heading"><div><h2>{source.project.name}</h2><p>{source.project.side}{readyStock&&` · laminat ${Number(thickness).toLocaleString('pl-PL')} mm`} · wspólne zero X/Y</p></div>
      </div>
    <section class="project-setup project-setup-inline" aria-label="Wspólne przygotowanie PCB">
      <div class="project-stock-editor" onFocusOut={event=>{if(!event.currentTarget.contains(event.relatedTarget))newStock(stockDraftRef.current);}}><PcbNumber name="thicknessMm" prefix="project-stock" value={stockDraft} onChange={draftStock} disabled={stockLocked}/></div>
      <div class="project-xy-inline"><span role="status">{run?.xyReady?'X/Y potwierdzone':'X/Y nieustawione'}</span><button type="button" disabled={!controller.manualReady.value||settingXY} title="Bieżące położenie zostanie zapisane jako X=0 i Y=0, bez ruchu osi." onClick={confirmXY}>{settingXY?'Zapisywanie…':'Ustaw tutaj zero X/Y'}</button></div>
      <p class="project-datum-note">0,0: lewy dolny narożnik gotowej PCB · widok od strony frezowania · {source.project.side}{source.project.side==='B.Cu'?' (odbity)':''}</p>
    </section>
    <nav class="project-stage-tabs" aria-label="Etapy PCB" role="tablist">{projectStages.map(({id,label,icon:Icon},index)=><button type="button" id={`stage-${id}`} role="tab" tabIndex={kind===id?0:-1} aria-selected={kind===id} aria-controls="project-stage-panel" disabled={controller.active.value&&kind!==id} onClick={()=>setKind(id)} onKeyDown={event=>{if(controller.active.value)return;const target=event.key==='Home'?0:event.key==='End'?2:event.key==='ArrowRight'?(index+1)%3:event.key==='ArrowLeft'?(index+2)%3:null;if(target!==null){event.preventDefault();setKind(projectStages[target].id);document.getElementById(`stage-${projectStages[target].id}`)?.focus();}}}><Icon size={20}/><strong>{label}</strong><small>{phaseText(run?.stageStates?.[id])}</small></button>)}</nav>
    <div id="project-stage-panel" role="tabpanel" aria-labelledby={`stage-${kind}`}>
      {kind==='outline'&&chosen?.values?.retention==='through'&&<label class="cam-confirm"><input type="checkbox" checked={through} disabled={locked} onChange={e=>setThrough(e.currentTarget.checked)}/><span>Mocowanie utrzyma PCB po wycięciu na wylot.</span></label>}
      {cad.length!==1&&<p role="alert">Prześlij z Tractora jedną paczkę projektu PCB.</p>}
      <ProjectOperation key={`${selected}-${kind}`} controller={controller} ask={ask} api={api} setupId={run?.id} stageId={kind} stage={stage} busy={busy||settingXY} xyReady={!!run?.xyReady} grid={grid} onGrid={setGrid} probeDistance={probeDistance} probeFeed={probeFeed} through={through} sourceGeometry={sourceGeometry} sourceError={sourceError} profile={chosen} thickness={thickness} capability={capability} profileError={profileError||(kind==='outline'&&chosen?.values?.retention==='through'&&!through?'Potwierdź mocowanie do cięcia na wylot.':'')} prepare={()=>prepare(kind,true)} onProfile={id=>changeProfile(kind,id)} profiles={available(kind)} onMove={onMove}/>
      {stageErrors[kind]&&<p class="stage-error" role="alert">{stageErrors[kind]}</p>}
      {error&&<p role="alert">{error}</p>}
    </div>
  </section>;
}

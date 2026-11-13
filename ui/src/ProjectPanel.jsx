import {useEffect,useRef,useState} from 'preact/hooks';
import {IconCircuitGround,IconGridDots,IconCut,IconChevronLeft,IconRefresh,IconFileImport,IconPencil} from '@tabler/icons-preact';
import {AppSelect} from './AppSelect.jsx';
import {PcbNumber} from './PcbField.jsx';
import {flowApi} from './PcbFlow.jsx';
import {ProjectOperation} from './ProjectOperation.jsx';
import './project-flow.css';

export const projectStages=[{id:'isolation',label:'Ścieżki',title:'Frezowanie izolacyjne',icon:IconCircuitGround},
  {id:'drilling',label:'Otwory',title:'Otwory THT',icon:IconGridDots},
  {id:'outline',label:'Obrys',title:'Wycięcie PCB',icon:IconCut}];
const legacyCapabilities={isolation:{available:true},outline:{available:true},
  drilling:{available:false,reason:'Wyślij ponownie projekt z aktualnego Tractora, aby rozpoznać otwory THT.'}};
const phaseText=stage=>stage?.done?'Wykonano':stage?.stale?'Przelicz':stage?.state==='running'?'Przygotowanie':stage?.zReady?'Z gotowe':stage?.state==='ready'?'Pomiar Z':stage?.state==='failed'||stage?.state==='blocked'?'Problem':'Do wykonania';

export function ProjectPanel({controller,ask,onManual,onPreparing,probeDistance,probeFeed}){
  const [packages,setPackages]=useState([]),[selected,setSelected]=useState('');
  const [kind,setKind]=useState('isolation'),[thickness,setThickness]=useState('');
  const [stockDraft,setStockDraft]=useState(''),[stockEditing,setStockEditing]=useState(true);
  const stockDraftRef=useRef('');
  const [toolStore,setToolStore]=useState(null),[choices,setChoices]=useState({});
  const [run,setRun]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
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
  const locked=controller.active.value||busy;

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
          if(found){runRef.current=found.id;setRun(found);setThickness(String(found.thicknessMm));stockDraftRef.current=String(found.thicknessMm);setStockDraft(stockDraftRef.current);setStockEditing(false);setKind(active.kind);setChoices(Object.fromEntries(Object.entries(found.stageStates||{}).filter(([,value])=>value.profile?.id).map(([key,value])=>[key,value.profile.id])));}
        }
      }catch(cause){if(alive)setError(cause.message);}
    }
    refresh();const timer=setInterval(refresh,1500);
    return()=>{alive=false;clearInterval(timer);};
  },[selected]);
  function chooseProject(id){
    epoch.current++;packageRef.current=id;runRef.current=null;restoreAllowed.current=!!id;
    setSelected(id);setThickness('');setRun(null);setChoices({});setThrough(false);setStageErrors({});setError('');
    stockDraftRef.current='';setStockDraft('');setStockEditing(true);
  }
  function newStock(value){
    const valid=value!==''&&Number.isFinite(Number(value))&&Number(value)>=.3&&Number(value)<=3;
    setStockEditing(!valid);
    if(value===thickness)return;
    epoch.current++;runRef.current=null;restoreAllowed.current=false;setRun(null);setThickness(value);setThrough(false);setStageErrors({});setError('');
  }
  function draftStock(value){stockDraftRef.current=value;setStockDraft(value);if(document.activeElement?.tagName!=='INPUT')newStock(value);}
  function changeProfile(stage,id){setChoices({...choices,[stage]:id});setStageErrors({...stageErrors,[stage]:null});setThrough(false);}
  async function prepare(stageId,force=false){
    const chosen=profile(stageId);
    if(!source||!readyStock||!chosen||preparing.current)return;
    preparing.current=true;setBusy(true);
    const version=epoch.current;
    try{
      const response=await api('/api/pcb-projects/prepare',{method:'POST',body:JSON.stringify({
        packageId:source.id,setupId:runRef.current,stage:stageId,thicknessMm:Number(thickness),
        profileId:chosen.id,fingerprint:chosen.fingerprint,confirmedThroughCut:through})});
      const value=await response.json();
      if(version!==epoch.current)return;
      runRef.current=value.id;setRun(value);setStageErrors(errors=>({...errors,[stageId]:null}));setError('');
    }catch(cause){if(version===epoch.current && !/już oblicza|Poczekaj/.test(cause.message))setStageErrors(errors=>({...errors,[stageId]:cause.message}));}
    finally{preparing.current=false;setBusy(false);}
  }
  // Preparing CAD never moves a machine. Queue ready stages one at a time;
  // a missing tool or failed stage does not prevent preparing the other stages.
  useEffect(()=>{
    if(!source||!readyStock||cad.length!==1||!controller.known.value||cnc.connected||controller.data.value?.cam_preparing||busy||preparing.current)return;
    const next=projectStages.find(({id})=>{
      const chosen=profile(id),current=run?.stageStates?.[id];
      if(!chosen||!capabilities[id]?.available||stageErrors[id])return false;
      if(id==='drilling'&&chosen.values?.drillOverrunMm===undefined)return false;
      if(id==='outline'&&chosen.values?.retention==='through'&&!through)return false;
      return !current || (!['running'].includes(current.state) && current.profile?.fingerprint!==chosen.fingerprint);
    });
    if(next)prepare(next.id);
  },[selected,thickness,choices,toolStore,run,cnc.connected,controller.data.value?.cam_preparing,busy,through]);
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
      {readyStock&&!stockEditing&&<button type="button" class="text-button" aria-label="Zmień grubość laminatu" disabled={locked||cnc.connected} onClick={()=>setStockEditing(true)}><IconPencil size={17}/></button>}</div>
    {(stockEditing||!readyStock)&&<div class="project-stock-editor" onFocusOut={event=>{if(!event.currentTarget.contains(event.relatedTarget))newStock(stockDraftRef.current);}}><PcbNumber name="thicknessMm" prefix="project-stock" value={stockDraft} onChange={draftStock} disabled={locked||cnc.connected}/></div>}
    <nav class="project-stage-tabs" aria-label="Etapy PCB" role="tablist">{projectStages.map(({id,label,icon:Icon},index)=><button type="button" id={`stage-${id}`} role="tab" tabIndex={kind===id?0:-1} aria-selected={kind===id} aria-controls="project-stage-panel" disabled={controller.active.value&&kind!==id} onClick={()=>setKind(id)} onKeyDown={event=>{if(controller.active.value)return;const target=event.key==='Home'?0:event.key==='End'?2:event.key==='ArrowRight'?(index+1)%3:event.key==='ArrowLeft'?(index+2)%3:null;if(target!==null){event.preventDefault();setKind(projectStages[target].id);document.getElementById(`stage-${projectStages[target].id}`)?.focus();}}}><Icon size={20}/><strong>{label}</strong><small>{phaseText(run?.stageStates?.[id])}</small></button>)}</nav>
    <div id="project-stage-panel" role="tabpanel" aria-labelledby={`stage-${kind}`}>
      <h3>{projectStages.find(value=>value.id===kind).title}</h3>
      {available(kind).length>1?<AppSelect id={`project-profile-${kind}`} label="Profil narzędzia" value={chosen?.id||''} disabled={locked} onChange={id=>changeProfile(kind,id)} options={available(kind).map(p=>({value:p.id,label:p.name}))}/>:chosen&&<p class="project-tool">Profil: <strong>{chosen.name}</strong></p>}
      {kind==='drilling'&&capability?.count>0&&<p class="project-hint">{capability.count} otworów THT · {capability.diametersMm?.length} średnice wierteł</p>}
      {profileError&&<p class="project-message" role="status">{profileError}</p>}
      {!capability?.available&&<p class="project-message" role="status">{capability?.reason||'Brak danych tego etapu w projekcie.'}</p>}
      {cad.length!==1&&<p role="alert">Prześlij z Tractora jedną paczkę projektu PCB.</p>}
      {!readyStock&&<p class="project-message">Podaj zmierzoną grubość laminatu, aby przygotować etapy.</p>}
      {kind==='outline'&&chosen?.values?.retention==='through'&&<label class="cam-confirm"><input type="checkbox" checked={through} disabled={locked} onChange={event=>setThrough(event.currentTarget.checked)}/><span>Mocowanie utrzyma PCB po wycięciu na wylot bez mostków.</span></label>}
      {stageErrors[kind]&&<p role="alert">{stageErrors[kind]}</p>}
      {!profileMatches&&<p class="project-message" role="status">{cnc.connected?'Rozłącz CNC, aby przygotować etap dla wybranego profilu.':'Przygotowanie etapu dla wybranego profilu…'}</p>}
      {(stageErrors[kind]||stage?.stale||['failed','blocked'].includes(stage?.state))&&<button type="button" disabled={busy||cnc.connected} onClick={()=>prepare(kind,true)}>Przelicz etap</button>}
      {readyStock&&capability?.available&&!profileError&&!stageErrors[kind]&&profileMatches&&(kind!=='outline'||chosen?.values?.retention!=='through'||through)&&<ProjectOperation key={`${run?.id}-${kind}`} controller={controller} ask={ask} api={api} setupId={run?.id} stageId={kind} stage={stage} busy={busy} onRun={setRun} probeDistance={probeDistance} probeFeed={probeFeed} through={through}/>
      }
      {error&&<p role="alert">{error}</p>}
    </div>
  </section>;
}

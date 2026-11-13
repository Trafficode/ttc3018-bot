import {useEffect, useState} from 'preact/hooks';
import {AppSelect} from './AppSelect.jsx';
import {Disclosure} from './FieldHelp.jsx';
import {PcbNumber} from './PcbField.jsx';
import {friendlyError,profileValuesValid} from './pcb-fields.js';

const scopes=[{value:'all',label:'Ścieżki, wiercenie i obrys'},
  {value:'mechanical',label:'Wiercenie i obrys'},
  {value:'drilling',label:'Tylko wiercenie'},
  {value:'outline',label:'Tylko obrys'},
  {value:'isolation',label:'Tylko ścieżki'}];
const stages={all:['isolation','drilling','outline'],mechanical:['drilling','outline'],
  drilling:['drilling'],outline:['outline'],isolation:['isolation']};
const titles={drilling:'Profil wiercenia',outline:'Profil obrysu'};

export function FlowSetup({source,controller,api,onPrepared,locked,filename,onOpenProfiles}) {
  const [store,setStore]=useState(null),[scope,setScope]=useState('all');
  const [selected,setSelected]=useState({}),[thickness,setThickness]=useState('');
  const [clearance,setClearance]=useState(3),[confirmed,setConfirmed]=useState(false);
  const [through,setThrough]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const operations=stages[scope],mechanical=operations.filter(kind=>kind!=='isolation');
  const active=controller.cnc.value.calibration_profiles?.selected;
  const available=kind=>(store?.profiles||[]).filter(profile=>!profile.kind || profile.kind===kind);
  const profiles=Object.fromEntries(mechanical.map(kind=>[kind,available(kind).find(profile=>profile.id===selected[kind])]));
  const outline=profiles.outline?.values;
  const thicknessValue=Number(thickness);
  const profilesReady=mechanical.every(kind=>profiles[kind] && profileValuesValid(
    {...profiles[kind].values,drillDiameterMm:profiles[kind].values.drillDiameterMm??0},kind));
  const isolationReady=!operations.includes('isolation') || Boolean(active?.model && active.depth!==undefined);
  const stockReady=thickness!=='' && Number.isFinite(thicknessValue) && thicknessValue>=.3 && thicknessValue<=3;
  const simpleOutline=outline?.outlineDepthMode==='remaining';
  const remaining=outline ? Number(simpleOutline ? outline.remainingMm??0 : outline.retention==='skin'?outline.skinMm:outline.tabHeightMm??0) : 0;
  const outlineDepth=outline ? thicknessValue+(outline.retention==='skin'?-remaining:Number(simpleOutline?outline.millOverrunMm:outline.breakthroughMm)) : null;
  const outlineReady=!outline || (outlineDepth>0 && (simpleOutline || outlineDepth<=outline.cuttingLengthMm) &&
    (outline.retention==='through' || thicknessValue>remaining));
  const valid=stockReady && profilesReady && isolationReady && outlineReady &&
    (outline?.retention!=='through' || through);
  useEffect(()=>{
    let alive=true;
    api('/api/pcb-profiles').then(response=>response.json()).then(value=>{
      if(!alive)return;
      setStore(value);
      const choices={};
      for(const kind of ['drilling','outline']) {
        const list=value.profiles.filter(profile=>!profile.kind || profile.kind===kind);
        choices[kind]=list.find(profile=>profile.id===value.activeByKind?.[kind])?.id
          || list.find(profile=>profile.id===value.active)?.id || list[0]?.id || '';
      }
      setSelected(choices);
    }).catch(cause=>{if(alive)setError(cause.message);});
    return()=>{alive=false;};
  },[]);
  async function choose(kind,id) {
    setBusy(true);setError('');
    try {
      const profile=available(kind).find(value=>value.id===id);
      await api('/api/pcb-profiles/select',{method:'POST',body:JSON.stringify({
        id,fingerprint:profile.fingerprint,kind})});
      setSelected({...selected,[kind]:id});setConfirmed(false);setThrough(false);
    } catch(cause) {setError(friendlyError(cause.message));}
    finally {setBusy(false);}
  }
  async function prepare(event) {
    event.preventDefault();
    if(!valid || !confirmed)return;
    setBusy(true);setError('');
    try {
      const response=await api('/api/cam/prepare',{method:'POST',body:JSON.stringify({
        packageId:source.id,name:filename,operations,
        processProfiles:Object.fromEntries(mechanical.map(kind=>[kind,{
          id:profiles[kind].id,fingerprint:profiles[kind].fingerprint}])),
        profileFingerprint:active?.fingerprint,clearanceMm:Number(clearance),
        material:{thicknessMm:thicknessValue,confirmedThroughCut:through},
        confirmedDatum:true,confirmedSetup:true})});
      onPrepared(await response.json());
    } catch(cause) {setError(friendlyError(cause.message));}
    finally {setBusy(false);}
  }
  if(!store)return <p role="status">{error || 'Wczytywanie profili…'}</p>;
  if(store.error)return <p role="alert">{store.error}</p>;
  return <form class="pcb-setup simple-setup" onSubmit={prepare}>
    <div class="job-basics">
      <AppSelect id="pcb-scope" label="Zakres obróbki" value={scope} options={scopes}
        disabled={locked||busy} onChange={value=>{setScope(value);setConfirmed(false);setThrough(false);setError('');}}/>
      <PcbNumber name="thicknessMm" prefix="pcb" value={thickness} disabled={locked||busy}
        onChange={value=>{setThickness(value);setConfirmed(false);}}/>
    </div>
    <Disclosure title="Profile narzędzi" open={!profilesReady || !isolationReady}>
      {operations.includes('isolation') && <div class="job-recipe"><span>Ścieżki: <strong>{active?.name || 'brak profilu'}</strong></span>
        <button type="button" class="text-button" onClick={()=>onOpenProfiles('isolation')}>Zmień profil ścieżek</button></div>}
      {mechanical.map(kind=><div class="job-tool-choice" key={kind}>
        <AppSelect id={`pcb-${kind}-profile`} label={titles[kind]} value={selected[kind]||''}
          disabled={locked||busy||!available(kind).length} onChange={id=>choose(kind,id)}
          options={available(kind).map(profile=>({value:profile.id,label:profile.name}))}/>
        <button type="button" class="text-button" onClick={()=>onOpenProfiles(kind)}>
          {available(kind).length?'Edytuj profile':'Utwórz profil'}</button>
      </div>)}
      {operations.includes('isolation') && <PcbNumber name="clearanceMm" prefix="pcb-isolation"
        value={clearance} onChange={setClearance} disabled={locked||busy}/>}
      {!isolationReady && <p role="alert">Ścieżki wymagają skalibrowanego frezu V. Wiercenie i obrys możesz przygotować osobno.</p>}
    </Disclosure>
    {profilesReady && <p class="pcb-help">{mechanical.map(kind=>profiles[kind].name).join(' · ')}{mechanical.length>0?' · parametry zapisane w profilach':''}</p>}
    {profiles.drilling && profiles.drilling.values.drillOverrunMm===undefined && <p role="alert">Edytuj profil wiercenia: podaj całe zagłębienie czubka w podkładzie i zapisz.</p>}
    {profilesReady && profiles.drilling && stockReady && <p class="job-depth">Wiercenie: <strong>{(thicknessValue+Number(profiles.drilling.values.drillOverrunMm)).toFixed(2)} mm</strong> · czubek {profiles.drilling.values.drillOverrunMm} mm w podkładzie</p>}
    {outline && stockReady && <p class="job-depth">Obrys: <strong>{outlineDepth.toFixed(2)} mm</strong> ·
      {outline.retention==='skin'?` zostaje ${remaining} mm`:outline.retention==='tabs'?` mostki ${remaining} mm`:' na wylot'}</p>}
    {outline && stockReady && !outlineReady && <p role="alert">{simpleOutline?'Pozostawiany laminat musi być cieńszy od PCB.':'Sprawdź grubość laminatu i długość ostrzy frezu.'}</p>}
    {outline?.retention==='through' && <label class="cam-confirm"><input type="checkbox" checked={through}
      disabled={locked||busy} onChange={event=>setThrough(event.currentTarget.checked)}/>
      <span>Mocowanie utrzyma PCB po wycięciu na wylot bez mostków.</span></label>}
    <label class="cam-confirm"><input type="checkbox" checked={confirmed} disabled={locked||busy}
      onChange={event=>setConfirmed(event.currentTarget.checked)}/>
      <span>Sprawdzone narzędzia, podkład, prześwit i miejsce pomiaru Z. Jedno zero X/Y dla całego PCB.</span></label>
    {controller.cnc.value.connected && <p>Rozłącz CNC przed obliczeniem programów.</p>}
    {error && <p role="alert">{error}</p>}
    <button type="submit" class="primary cam-primary" disabled={locked||busy||!valid||!confirmed||controller.cnc.value.connected}>
      {busy?'Przygotowywanie…':'Przygotuj wybrane operacje'}</button>
  </form>;
}

import {useEffect, useState} from 'preact/hooks';
import {IconPlus, IconPencil} from '@tabler/icons-preact';
import {AppSelect} from './AppSelect.jsx';
import {RetentionSelect} from './RetentionSelect.jsx';
import {initialProcessValues, profileValuesValid, friendlyError, toolFieldKeys, outlineEditorValues, outlineDefault} from './pcb-fields.js';
import {flowApi} from './PcbFlow.jsx';
import {ProfilePanel} from './ProfilePanel.jsx';
import {PcbNumber} from './PcbField.jsx';

export const operationChoices = [{value:'isolation',label:'Ścieżki · frez V'},
  {value:'drilling',label:'Wiercenie otworów'}, {value:'outline',label:'Wycinanie obrysu'}];
const names = {drilling:'Wiercenie',outline:'Obrys'};
const basic = {drilling:['drillDiameterMm','drillFeed','drillOverrunMm','clearanceMm'],
  outline:['millDiameterMm','millFeed','millPlunge','stepDownMm','clearanceMm']};

function ProcessEditor({controller, profile, kind, onDone}) {
  const legacy = profile && !profile.kind;
  const [name,setName] = useState(profile ? `${profile.name}${legacy ? ` · ${names[kind]}` : ''}` : '');
  const [values,setValues] = useState(() => kind==='outline' ? outlineEditorValues(profile?.values) : ({...initialProcessValues,drillDiameterMm:0,drillOverrunMm:'',...profile?.values}));
  const [confirmed,setConfirmed] = useState(false), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const locked = busy || !controller.known.value || controller.active.value;
  const complete = profileValuesValid(values,kind) && basic[kind].every(key=>values[key]!=='' && values[key]!==undefined);
  function change(key,value) { setValues({...values,[key]:value}); setConfirmed(false); setError(''); }
  const field = key => <PcbNumber key={key} name={key} value={values[key]} disabled={locked}
    prefix={`profile-${kind}`} onChange={value=>change(key,value)}/>;
  async function save(event) {
    event.preventDefault();
    if (!confirmed || !complete) return;
    setBusy(true); setError('');
    const body = {name,kind,confirmedTools:true,
      values:Object.fromEntries(toolFieldKeys(kind,values).map(key=>[key,Number(values[key])]))};
    if (kind==='outline') Object.assign(body.values,{retention:values.retention,outlineDepthMode:'remaining'});
    if (profile && !legacy) Object.assign(body,{id:profile.id,expectedFingerprint:profile.fingerprint});
    try { await flowApi(controller,'/api/pcb-profiles/save',{method:'POST',body:JSON.stringify(body)}); onDone(); }
    catch(cause) { setError(friendlyError(cause.message)); }
    finally { setBusy(false); }
  }
  return <form class="process-editor simple-process-editor" onSubmit={save}>
    <label>Nazwa profilu<input value={name} maxLength={60} required disabled={locked}
      placeholder={kind==='drilling'?'Np. moje wiertła do PCB':'Np. frez płaski · FR4'}
      onInput={event=>setName(event.currentTarget.value)}/></label>
    <p class="pcb-help">Grubość laminatu podasz raz przy zleceniu. Ten profil działa niezależnie od frezu V.</p>
    {legacy && <p class="pcb-help">Zapis utworzy osobny profil. Starszy zestaw pozostanie dostępny.</p>}
    <div class="pcb-form-grid">{basic[kind].map(field)}</div>
    {kind==='drilling' && <p class="pcb-help">Głębokość = grubość PCB + zagłębienie czubka w podkładzie. Uwzględnij czubek wiertła i zapas na nierówności. Zapewnij odpowiednio gruby podkład. Wrzeciono: stałe 100% sterowania.</p>}
    {kind==='drilling' && profile && profile.values.drillOverrunMm===undefined && <p class="pcb-help">Starszy profil doliczał stożek wiertła. Podaj teraz całe zagłębienie czubka w podkładzie i zapisz profil.</p>}
    {kind==='outline' && <>
      <RetentionSelect id="profile-outline-retention" value={values.retention} disabled={locked}
        onChange={value=>change('retention',value)}/>
      <div class="pcb-form-grid">
        {values.retention!=='through' && field('remainingMm')}
        {values.retention!=='skin' && field('millOverrunMm')}
      </div>
      <p class="pcb-help">Zapewnij odpowiednio długie ostrza frezu i gruby podkład. Wrzeciono: stałe 100% sterowania.</p>
      {values.retention==='tabs' && <p class="pcb-help">Szerokość mostków dobierana automatycznie: {outlineDefault('tabWidthMm',values)} mm.</p>}
      {values.retention==='through' && <p class="pcb-help">Cięcie bez mostków wymaga osobnego potwierdzenia mocowania przy zleceniu.</p>}
    </>}
    <label class="cam-confirm"><input type="checkbox" checked={confirmed} disabled={locked}
      onChange={event=>setConfirmed(event.currentTarget.checked)}/>
      <span>Parametry odpowiadają mojemu narzędziu i mocowaniu.</span></label>
    {!complete && <p class="pcb-help">{kind==='drilling'?'Uzupełnij parametry wiercenia.':'Uzupełnij parametry obrysu.'}</p>}
    {error && <p role="alert">{error}</p>}
    <div class="button-row"><button type="submit" class="primary"
      disabled={locked || !name.trim() || !confirmed || !complete}>Zapisz profil</button>
      <button type="button" disabled={busy} onClick={onDone}>Anuluj</button></div>
  </form>;
}

export function PcbProfiles({controller,kind}) {
  const [store,setStore]=useState(null), [editing,setEditing]=useState(null), [error,setError]=useState('');
  async function refresh() {
    try {setStore(await (await flowApi(controller,'/api/pcb-profiles')).json());}
    catch(cause) {setError(cause.message);}
  }
  useEffect(()=>{refresh();},[]);
  const profiles=(store?.profiles||[]).filter(profile=>!profile.kind || profile.kind===kind);
  return <section class="process-profiles">
    <div class="process-heading"><h2>Profile · {names[kind]}</h2>
      {!editing && <button type="button" disabled={controller.active.value} onClick={()=>setEditing({})}>
        <IconPlus size={17}/>Nowy profil</button>}</div>
    {editing ? <ProcessEditor controller={controller} kind={kind} profile={editing.id?editing:null}
      onDone={()=>{setEditing(null);refresh();}}/> : <>
      {!profiles.length && <p>Zapisz parametry swojego narzędzia. Przy PCB wybierzesz profil i zmierzoną grubość laminatu.</p>}
      <div class="process-list">{profiles.map(profile=><button type="button" key={profile.id}
        disabled={controller.active.value} onClick={()=>setEditing(profile)}>
        <span><strong>{profile.name}</strong><small>{!profile.kind ? 'Starszy zestaw · utwórz osobną kopię' : kind==='drilling'
          ? profile.values.drillDiameterMm ? `Wiertło Ø${profile.values.drillDiameterMm} mm` : 'Średnice według pliku PCB'
          : `Frez Ø${profile.values.millDiameterMm} mm · ${{skin:'cienka warstwa',tabs:'mostki',through:'na wylot'}[profile.values.retention]}`}</small></span>
        <IconPencil size={17}/></button>)}</div>
    </>}
    {(error || store?.error) && <p role="alert">{error || store.error}</p>}
  </section>;
}

export function ProfileHub({controller,cnc,ask,kind='isolation',onKindChange}) {
  const [localKind,setLocalKind]=useState(kind);
  const selected=onKindChange ? kind : localKind;
  return <section class="profile-hub">
    <AppSelect id="profile-operation" label="Rodzaj obróbki" value={selected}
      options={operationChoices} onChange={value=>{setLocalKind(value);onKindChange?.(value);}}/>
    {selected==='isolation' ? <ProfilePanel controller={controller} cnc={cnc} ask={ask}/>
      : <PcbProfiles key={selected} controller={controller} kind={selected}/>}
  </section>;
}

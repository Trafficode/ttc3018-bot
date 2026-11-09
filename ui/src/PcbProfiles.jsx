import {useEffect,useState} from 'preact/hooks';
import {RetentionSelect} from './RetentionSelect.jsx';
import {IconPlus,IconPencil} from '@tabler/icons-preact';
import {FieldHelp,Disclosure} from './FieldHelp.jsx';
import {initialProcessValues,profileValuesValid,friendlyError} from './pcb-fields.js';
import {flowApi} from './PcbFlow.jsx';
import {ProfilePanel} from './ProfilePanel.jsx';
import {PcbNumber} from './PcbField.jsx';

function ProcessEditor({controller,profile,onDone}){
  const [name,setName]=useState(profile?.name || ''),[values,setValues]=useState(()=>{if(profile)return profile.values;const result={...initialProcessValues};try{const saved=JSON.parse(localStorage.getItem('bark:pcb-tool-settings')||'{}');for(const key of Object.keys(result))if(saved[key]!==undefined)result[key]=saved[key];}catch{}return result;});
  const [confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const cnc=controller.cnc.value,calibration=cnc.calibration_profiles?.selected;
  const locked=busy || !controller.known.value || controller.active.value;
  const field=key=><PcbNumber key={key} name={key} value={values[key]} disabled={locked} onChange={value=>setValues({...values,[key]:value})}/>;
  async function save(event){event.preventDefault();if(!confirmed || !profileValuesValid(values))return;setBusy(true);setError('');try{const body={name,values:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,key==='retention'?value:Number(value)])),confirmedTools:true,...(profile?{id:profile.id,expectedFingerprint:profile.fingerprint}:{})};await flowApi(controller,'/api/pcb-profiles/save',{method:'POST',body:JSON.stringify(body)});onDone();}catch(cause){setError(friendlyError(cause.message));}finally{setBusy(false);}}
  return <form class="process-editor" onSubmit={save}><label>Nazwa profilu<input value={name} maxLength={60} required disabled={locked} placeholder="Np. FR4 · mój zestaw Ø1 mm" onInput={event=>setName(event.currentTarget.value)}/></label><p class="profile-binding">Frez V: <strong>{calibration?.name || 'brak kalibracji'}</strong><FieldHelp id="process-isolation" label="Powiązanie z frezem V">Profil obróbki zapamięta aktualnie wybraną kalibrację frezu V. Kalibrację zmienisz w karcie Frez V. Wiertła i frez płaski mają osobne parametry.</FieldHelp></p>
    <h3>Wiercenie</h3><div class="pcb-form-grid">{field('drillFeed')}{field('drillPower')}</div>
    <h3>Obrys · frez Ø1 mm</h3><div class="pcb-form-grid">{['millFeed','millPlunge','millPower','stepDownMm','cuttingLengthMm'].map(field)}</div>
    <Disclosure title="Podkład i przejazdy"><div class="pcb-form-grid">{field('backingMm')}{field('clearanceMm')}</div></Disclosure>
    <Disclosure title="Zaawansowane · geometria i zapasy"><div class="pcb-form-grid">{['drillPointAngleDeg','breakthroughMm','uncertaintyMm'].map(field)}</div></Disclosure>
    <Disclosure title="Domyślny sposób oddzielenia"><RetentionSelect id="process-retention" label="Sposób oddzielenia" value={values.retention} disabled={locked} onChange={value=>{setValues({...values,retention:value});setConfirmed(false);}}/><div class="pcb-form-grid">{field('skinMm')}{field('tabWidthMm')}{field('tabHeightMm')}</div></Disclosure>
    <label class="cam-confirm"><input type="checkbox" checked={confirmed} disabled={locked} onChange={event=>setConfirmed(event.currentTarget.checked)}/><span>Parametry odpowiadają moim narzędziom i mocowaniu. Grubość laminatu podam przy zleceniu.</span></label>
    {!profileValuesValid(values) && <p class="pcb-help">Uzupełnij narzędzia oraz grubość podkładu. Posuwy i wrzeciono wymagają ustawienia dla Twojego zestawu.</p>}
    {!calibration?.model && <p role="alert">W karcie Frez V wybierz skalibrowany frez przed zapisem.</p>}
    {error && <p role="alert">{error}</p>}<div class="button-row"><button type="submit" class="primary" disabled={locked || !name.trim() || !confirmed || !profileValuesValid(values) || !calibration?.model}>Zapisz profil</button><button type="button" disabled={busy} onClick={onDone}>Anuluj</button></div>
  </form>;
}

export function PcbProfiles({controller}){
  const [store,setStore]=useState(null),[editing,setEditing]=useState(null),[error,setError]=useState('');
  async function refresh(){try{setStore(await (await flowApi(controller,'/api/pcb-profiles')).json());}catch(cause){setError(cause.message);}}
  useEffect(()=>{refresh();},[]);
  return <section class="process-profiles"><div class="process-heading"><h2>Profile obróbki PCB</h2>{!editing && <button type="button" disabled={controller.active.value} onClick={()=>setEditing({})}><IconPlus size={17}/>Nowy profil</button>}</div>
    {editing ? <ProcessEditor key={editing.id || 'new'} controller={controller} profile={editing.id?editing:null} onDone={()=>{setEditing(null);refresh();}}/> : <>{store?.profiles?.length ? <div class="process-list">{store.profiles.map(profile=><button type="button" key={profile.id} disabled={controller.active.value} onClick={()=>setEditing(profile)}><span><strong>{profile.name}</strong><small>{profile.isolation.name} · frez Ø1 mm · {profile.values.retention==='skin'?`warstwa ${profile.values.skinMm} mm`:'mostki'}</small></span><IconPencil size={17}/></button>)}</div> : <p>Ustaw raz parametry swojego zestawu. Przy płytce wybierzesz profil i wpiszesz tylko zmierzoną grubość.</p>}</>}
    {(error || store?.error) && <p role="alert">{error || store.error}</p>}
  </section>;
}

export function ProfileHub({controller,cnc,ask}){
  const [view,setView]=useState('pcb');
  return <><div class="profile-hub-tabs" role="group" aria-label="Rodzaj profilu"><button type="button" aria-pressed={view==='pcb'} onClick={()=>setView('pcb')}>Obróbka PCB</button><button type="button" aria-pressed={view==='v'} onClick={()=>setView('v')}>Frez V · kalibracja</button></div>{view==='pcb'?<PcbProfiles controller={controller}/>:<ProfilePanel controller={controller} cnc={cnc} ask={ask}/>}</>;
}

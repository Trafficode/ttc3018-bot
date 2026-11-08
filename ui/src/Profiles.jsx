import {useLayoutEffect,useState} from 'preact/hooks';
import {ParameterField} from './ParameterField.jsx';
import {toolDiameter} from './service-geometry.js';
import './profiles.css';

const mm=v=>Number(v).toLocaleString('pl-PL',{maximumFractionDigits:4});
export const defaultProfile={id:'default',name:'Domyślny',model:null,fingerprint:'default',depth:.05,conditions:{tip:.1,angle:30,feed:100,plunge:20,power:300}};
export function ProfileBar({controller,cnc}) {
  const store=cnc.calibration_profiles, selected=store?.selected||defaultProfile;
  const ready=controller.known.value&&!controller.pending.value&&!controller.active.value&&(!cnc.connected||controller.manualReady.value);
  return <div id="geometry-status" class="profile-bar"><label for="active-profile">Profil<select id="active-profile" value={selected.id} disabled={!store||!ready||!!store.error} onChange={e=>controller.send({action:'profile_select',profile_id:e.currentTarget.value})}>{(store?.profiles||[defaultProfile]).map(p=><option key={p.id} value={p.id}>{p.name}{p.depth!=null?` · Z −${p.depth}`:' · ustaw głębokość'}</option>)}</select></label><span>{selected.model?`D = ${mm(selected.model.intercept_mm)} + ${mm(selected.model.slope)} × h${selected.model.offset_mm!=null?` · ΔD ${selected.model.offset_mm>=0?'+':''}${mm(selected.model.offset_mm)} mm`:''}`:'Korekta: brak'}</span></div>;
}

function exportProfile(profile) {
  const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,profile},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`bark-beetle-profile-${profile.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const fields=[
  ['depth','Zagłębienie w miedź · mm',[.01,.02,.03,.04,.05,.06,.08,.1,.12,.15,.2,.25,.3],.01,.3,.001,'Głębokość cięcia poniżej zmierzonej powierzchni PCB. Ta sama wartość jest używana w teście i przy przygotowaniu CAM.'],
  ['tip','Końcówka frezu · mm',[.05,.1,.15,.2,.3,.4,.5],.01,.5,.01,'Szerokość czubka frezu V z oznaczenia narzędzia, np. 0,1 mm.'],
  ['angle','Kąt frezu · °',[10,15,20,30,45,60,90],10,90,1,'Pełny kąt ostrza, np. 30°. Wraz z zagłębieniem określa szerokość rowka.'],
  ['feed','Prędkość frezowania XY · mm/min',[10,20,30,50,75,100,150,200,250,300],10,300,1,'Prędkość przesuwania frezu po ścieżkach w poziomie. Niższa wartość oznacza wolniejsze frezowanie.'],
  ['plunge','Wejście w materiał Z · mm/min',[1,5,10,15,20,30,40,50,75,100],1,100,1,'Prędkość pionowego opuszczania frezu przy rozpoczynaniu cięcia. Przy 20 mm/min frez pokonuje 1 mm w 3 sekundy. Sondowanie ma osobny posuw.'],
  ['power','Wrzeciono · S',[100,200,300,400,500,600,700,800,900,1000],1,1000,1,'Ustawienie sterownika wrzeciona: S1000 to pełna skala, S300 to 30%. To nie jest pomiar obrotów RPM.'],
];

export function ProfileSettings({controller,cnc,ask}) {
  const profile=cnc.calibration_profiles?.selected||defaultProfile;
  const [creating,setCreating]=useState(false),[name,setName]=useState(''),[tool,setTool]=useState({}),[rows,setRows]=useState([]),[error,setError]=useState(''),[saved,setSaved]=useState('');
  function load(p) {
    setName(p.name);setTool(Object.fromEntries(Object.entries({...p.conditions,depth:p.depth??p.observations?.[0]?.depth??.05}).map(([k,v])=>[k,String(v)])));
    setRows((p.observations||[{depth:.05,width:.5,measured_width:.5,geometry:{diameter_mm:null}}]).map(r=>({depth:String(r.depth),width:String(r.width),measured_width:String(r.measured_width),used_diameter:r.geometry.diameter_mm==null?null:String(r.geometry.diameter_mm)})));
    setError('');setSaved('');
  }
  useLayoutEffect(()=>{setCreating(false);load(profile);},[profile.fingerprint]);
  const readonly=!creating&&profile.id==='default';
  const locked=!!controller.pending.value||controller.active.value;
  function updateRow(index,key,value){setRows(rows.map((r,i)=>i===index?{...r,[key]:value}:r));setError('');}
  function diameter(row){return row.used_diameter??toolDiameter(Number(tool.tip),Number(tool.angle),Number(row.depth));}
  async function save(event) {
    event.preventDefault();setError('');setSaved('');
    if(!name.trim()||Object.values(tool).some(v=>!String(v).trim())||rows.some(r=>!r.depth.trim()||!r.width.trim()||!r.measured_width.trim()||r.used_diameter==='')){setError('Uzupełnij nazwę, parametry i pomiar kalibracyjny.');return;}
    const payload={action:creating?'profile_create':'profile_update',source:'manual',name:name.trim(),profile_id:profile.id,profile_fingerprint:profile.fingerprint,...Object.fromEntries(Object.entries(tool).map(([k,v])=>[k,Number(v)])),samples:rows.map(r=>({depth:Number(r.depth),width:Number(r.width),measured_width:Number(r.measured_width),used_diameter:Number(diameter(r))}))};
    if(!await controller.send(payload)){setError(controller.profileError.value||'Nie zapisano profilu. Sprawdź połączenie i wartości.');return;}
    if(creating){const id=controller.createdProfile.value?.id;if(id)await controller.send({action:'profile_select',profile_id:id});setCreating(false);}
    setSaved('Profil zapisany. Test jest dostępny w zakładce Test. Zmiana parametrów wymaga ponownego przygotowania plików CAM.');
  }
  return <section class="profile-settings"><div class="profile-toolbar"><button id="profile-new" type="button" disabled={locked} onClick={()=>{setCreating(true);load({...defaultProfile,name:''});}}>Nowy profil</button>{!creating&&profile.id!=='default'&&<button id="profile-delete" type="button" disabled={locked} onClick={()=>ask('profile_delete',{profile_id:profile.id,profile_fingerprint:profile.fingerprint,name:profile.name})}>Usuń profil</button>}{!creating&&profile.model&&<button type="button" disabled={locked} onClick={()=>exportProfile(profile)}>Eksport do CAM</button>}</div>
    {readonly&&<p class="service-hint">Profil Domyślny ma stałe parametry. Wybierz zapisany profil z listy, aby go edytować, albo utwórz nowy.</p>}
    <form class="profile-form" noValidate onSubmit={save}><label class="parameter-field">Nazwa profilu<input id="profile-name" value={name} maxLength="40" disabled={readonly||locked} onInput={e=>setName(e.currentTarget.value)}/></label>
    <div class="profile-parameter-grid">{fields.map(([key,label,options,min,max,step,help])=><ParameterField key={key} id={`profile-${key}`} label={label} value={tool[key]??''} options={options} min={min} max={max} step={step} help={help} disabled={readonly||locked} onChange={v=>{setTool({...tool,[key]:v});setError('');}} format={key==='power'?v=>`S${v} · ${v/10}%`:undefined}/>)}</div>
    {!readonly&&<fieldset class="service-module"><legend>Pomiar kalibracyjny</legend><p class="service-hint">Wystarczy jeden pomiar z próbki wykonanej w Serwisie. Nominalny pasek to ustawiona wtedy szerokość; zmierzony pasek to szerokość pozostałej miedzi.</p>{rows.map((row,index)=><div class="profile-parameter-grid" key={index}>
      <ParameterField id={`profile-row-${index}-depth`} label="Zagłębienie próbki · mm" value={row.depth} options={fields[0][2]} min={.01} max={.3} step={.001} help="Głębokość użyta przy wykonywaniu mierzonej próbki." disabled={locked} onChange={v=>updateRow(index,'depth',v)}/>
      <ParameterField id={`profile-row-${index}-width`} label="Nominalny pasek · mm" value={row.width} options={[.2,.3,.5,.7,1,1.5,2]} min={.2} max={2} step={.01} help="Wartość szerokości ustawiona dla tej próbki w Serwisie." disabled={locked} onChange={v=>updateRow(index,'width',v)}/>
      <ParameterField id={`profile-row-${index}-measured_width`} label="Zmierzony pasek · mm" value={row.measured_width} options={[.2,.3,.5,.7,1,1.5,2]} min={.01} max={3} step={.01} help="Rzeczywista szerokość miedzi po frezowaniu. Przy kalibracji do 1 mm wybierz 1." disabled={locked} onChange={v=>updateRow(index,'measured_width',v)}/>
      <label class="parameter-field">Rowek użyty w programie · mm<input id={`profile-row-${index}-diameter`} type="number" min="0.001" max="1.999" step="0.0001" value={row.used_diameter??(Number.isFinite(diameter(row))?Number(diameter(row).toFixed(6)):'')} disabled={locked} onInput={e=>updateRow(index,'used_diameter',e.currentTarget.value)}/><small>Średnica przyjęta przy generowaniu próbki. Dla Serwisu wynika z frezu i zagłębienia.</small><button class="text-button" type="button" disabled={locked} onClick={()=>updateRow(index,'used_diameter',null)}>Oblicz z frezu</button></label>
    </div>)}</fieldset>}
    {error&&<p class="field-error" role="alert">{error}</p>}{saved&&<p class="profile-saved" role="status">{saved}</p>}
    {!readonly&&<div class="profile-toolbar"><button id="profile-save" class="primary" type="submit" disabled={locked}>{creating?'Utwórz i wybierz profil':'Zapisz zmiany'}</button><button type="button" disabled={locked} onClick={()=>{setCreating(false);load(profile);}}>Anuluj zmiany</button></div>}
    </form></section>;
}

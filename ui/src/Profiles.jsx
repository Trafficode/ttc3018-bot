import {useLayoutEffect,useState} from 'preact/hooks';
import {ParameterField} from './ParameterField.jsx';
import {toolDiameter} from './service-geometry.js';
import {calibrationPreview} from './profile-calibration.js';
import './profiles.css';
import {FieldHelp} from './FieldHelp.jsx';
import {AppSelect} from './AppSelect.jsx';

const mm=v=>Number(v).toLocaleString('pl-PL',{maximumFractionDigits:4});
const grooveMm=v=>Number(v).toLocaleString('pl-PL',{minimumFractionDigits:3,maximumFractionDigits:3});
export const defaultProfile={id:'default',name:'Domyślny',model:null,fingerprint:'default',depth:.05,conditions:{tip:.1,angle:30,feed:100,plunge:20,power:300}};
export function ProfileBar({controller,cnc}) {
  const store=cnc.calibration_profiles, selected=store?.selected||defaultProfile;
  const ready=controller.known.value&&!controller.pending.value&&!store?.error&&(!cnc.connected||controller.manualReady.value);
  const operation=cnc.job?.pcb_flow;
  if(operation && operation.kind!=='isolation')return <div id="geometry-status" class="profile-bar"><strong>{operation.title}</strong><span>Głębokość −{mm(operation.depthMm)} mm · parametry zlecenia CAM</span>{selected.id!=='default' && <span role="alert">Profil jest inny — wczytaj etap ponownie.</span>}</div>;
  return <div id="geometry-status" class="profile-bar"><AppSelect id="active-profile" label="Frez V" value={selected.id} disabled={!store||!ready} onChange={id=>controller.send({action:'profile_select',profile_id:id})} options={(store?.profiles||[defaultProfile]).map(p=>({value:p.id,label:p.name}))}/><FieldHelp id="active-v-model" label="Kalibracja frezu V">{selected.model?`Wyliczona szerokość skrawania: ${mm(selected.model.intercept_mm+selected.model.slope*selected.depth)} mm przy głębokości ${mm(selected.depth)} mm. ${selected.groove_verification?'Zgodność potwierdzona pomiarem przez operatora.':'Bez potwierdzenia pomiarem rowka.'}`:'Wybrany profil nie ma zmierzonego modelu szerokości frezu V.'}</FieldHelp></div>;
}

function exportProfile(profile) {
  const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,profile},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`bark-beetle-profile-${profile.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const fields=[
  ['depth','Zagłębienie w miedź · mm',[.01,.02,.03,.04,.05,.06,.08,.1,.12,.15,.2,.25,.3],.01,.3,.001,'Głębokość cięcia poniżej zmierzonej powierzchni PCB. Ta sama wartość jest używana w teście i przy przygotowaniu CAM.'],
  ['tip','Końcówka frezu · mm',[.05,.1,.15,.2,.3,.4,.5],.01,.5,.01,'Szerokość czubka frezu V z oznaczenia narzędzia, np. 0,1 mm.'],
  ['angle','Kąt frezu · °',[10,15,20,30,45,60,90],10,90,1,'Pełny kąt ostrza, np. 30°. Wraz z zagłębieniem określa szerokość rowka.'],
  ['feed','Posuw XY · mm/min',[10,20,30,50,75,100,150,200,250,300],10,300,1,'Prędkość poziomego ruchu frezu podczas cięcia.'],
  ['plunge','Wejście Z · mm/min',[1,5,10,15,20,30,40,50,75,100],1,100,1,'Prędkość opuszczania frezu przy rozpoczęciu cięcia. Sondowanie ma osobny posuw.'],
  ['power','Wrzeciono · %',[100,200,300,400,500,600,700,800,900,1000],1,1000,1,'S1000 to pełna skala. To ustawienie sterownika, nie pomiar obrotów RPM.'],
];

export function ProfileSettings({controller,cnc,ask}) {
  const profile=cnc.calibration_profiles?.selected||defaultProfile;
  const [creating,setCreating]=useState(false),[name,setName]=useState(''),[tool,setTool]=useState({}),[rows,setRows]=useState([]),[error,setError]=useState(''),[saved,setSaved]=useState(''),[acceptedKey,setAcceptedKey]=useState(''),[dirty,setDirty]=useState(false);
  function load(p) {
    const nextTool=Object.fromEntries(Object.entries({...p.conditions,depth:p.depth??p.observations?.[0]?.depth??.05}).map(([k,v])=>[k,String(v)]));
    const nextRows=(p.observations||[{depth:.05,width:.5,measured_width:.5,geometry:{diameter_mm:null}}]).map(r=>({depth:String(r.depth),width:String(r.width),measured_width:String(r.measured_width),used_diameter:r.geometry.diameter_mm==null?null:String(r.geometry.diameter_mm)}));
    setName(p.name);setTool(nextTool);setRows(nextRows);
    setAcceptedKey(p.groove_verification?calibrationPreview(nextTool,nextRows).key||'':'');setError('');setSaved('');setDirty(false);
  }
  useLayoutEffect(()=>{setCreating(false);load(profile);},[profile.fingerprint]);
  const readonly=!creating&&profile.id==='default';
  const locked=!!controller.pending.value||controller.active.value||!controller.known.value;
  const preview=calibrationPreview(tool,rows),verified=!!preview.key&&acceptedKey===preview.key;
  function changed(){setAcceptedKey('');setError('');setSaved('');setDirty(true);}
  function updateRow(index,key,value){setRows(rows.map((r,i)=>i===index?{...r,[key]:value}:r));changed();}
  function diameter(row){return row.used_diameter??toolDiameter(Number(tool.tip),Number(tool.angle),Number(row.depth));}
  async function save(event) {
    event.preventDefault();setError('');setSaved('');
    if(!name.trim()||preview.error){setError(preview.error||'Podaj nazwę profilu.');return;}
    const payload={action:creating?'profile_create':'profile_update',source:'manual',name:name.trim(),profile_id:profile.id,profile_fingerprint:profile.fingerprint,...preview.evidence.conditions,depth:preview.depth,samples:preview.samples,
      groove_confirmation:verified?{evidence:preview.evidence,diameter_mm:preview.width}:null};
    if(!await controller.send(payload)){setError(controller.profileError.value||'Nie zapisano profilu. Sprawdź połączenie i wartości.');return;}
    if(creating){const id=controller.createdProfile.value?.id;if(id)await controller.send({action:'profile_select',profile_id:id});setCreating(false);}
    setSaved(verified?'Zapisano profil z potwierdzeniem. Przygotuj ponownie CAM.':'Zapisano bez potwierdzenia pomiaru. Przygotuj ponownie CAM.');
  }
  return <section class="profile-settings">
    {readonly&&<p class="service-hint">Profil Domyślny ma stałe parametry. Wybierz zapisany profil albo utwórz nowy.</p>}
    <form class={`profile-form profile-configuration ${readonly?'profile-configuration-readonly':''}`} noValidate onSubmit={save}>
      <div class="profile-edit-fields">
        <div class="profile-identification"><label class="parameter-field">Nazwa profilu<input id="profile-name" value={name} maxLength="40" disabled={readonly||locked} onInput={e=>{setName(e.currentTarget.value);setSaved('');setDirty(true);}}/></label>
          <div class="profile-toolbar"><button id="profile-new" type="button" disabled={locked} onClick={()=>{setCreating(true);load({...defaultProfile,name:''});}}>Nowy profil</button>{!creating&&profile.id!=='default'&&<button id="profile-delete" type="button" disabled={locked} onClick={()=>ask('profile_delete',{profile_id:profile.id,profile_fingerprint:profile.fingerprint,name:profile.name})}>Usuń profil</button>}{!creating&&profile.model&&<button type="button" disabled={locked||dirty} title={dirty?'Zapisz zmiany przed eksportem profilu.':undefined} onClick={()=>exportProfile(profile)}>Eksport do CAM</button>}</div>
        </div>
        <fieldset class="service-module profile-cutting-settings"><legend>Parametry frezowania</legend><div class="profile-parameter-grid profile-tool-grid">{fields.map(([key,label,options,min,max,step,help])=><ParameterField key={key} id={`profile-${key}`} label={label} value={tool[key]??''} options={options} min={min} max={max} step={step} help={help} disabled={readonly||locked} onChange={v=>{setTool({...tool,[key]:v});changed();}} scale={key==='power'?.1:1} format={key==='power'?v=>`${v/10}%`:undefined}/>)}</div></fieldset>
        {!readonly&&<fieldset class="service-module profile-measurements"><legend>Pomiar kalibracyjny</legend>{rows.map((row,index)=><div class="profile-observation" key={index}><div class="profile-parameter-grid profile-measurement-grid">
          <ParameterField id={`profile-row-${index}-depth`} label="Zagłębienie próbki · mm" value={row.depth} options={fields[0][2]} min={.01} max={.3} step={.001} help="Głębokość użyta przy wykonywaniu mierzonej próbki." disabled={locked} onChange={v=>updateRow(index,'depth',v)}/>
          <ParameterField id={`profile-row-${index}-width`} label="Nominalny pasek · mm" value={row.width} options={[.2,.3,.5,.7,1,1.5,2]} min={.2} max={2} step={.01} help="Szerokość paska ustawiona przy wykonywaniu próbki." disabled={locked} onChange={v=>updateRow(index,'width',v)}/>
          <ParameterField id={`profile-row-${index}-measured_width`} label="Zmierzony pasek · mm" value={row.measured_width} options={[.2,.3,.5,.7,1,1.5,2]} min={.01} max={3} step={.01} help="Zmierzona szerokość pozostałej miedzi, poza narożnikami." disabled={locked} onChange={v=>updateRow(index,'measured_width',v)}/>
          <ParameterField id={`profile-row-${index}-diameter`} label="Rowek założony w próbce · mm" value={row.used_diameter??(Number.isFinite(diameter(row))?Number(diameter(row).toFixed(6)):'')} options={[.1,.15,.2,.3,.4,.5,.6,.8,1]} min={.001} max={1.999} step={.0001} help="Historyczne założenie generatora próbki. To nie jest zmierzona szerokość rowka ani docelowy wynik kalibracji." disabled={locked} onChange={v=>updateRow(index,'used_diameter',v)}/>
        </div><div class="profile-observation-footer"><small>Założenie próbki to wartość historyczna.</small><button class="text-button profile-recalculate" type="button" disabled={locked} onClick={()=>updateRow(index,'used_diameter',null)}>Oblicz z frezu</button></div></div>)}</fieldset>}
      </div>
      {!readonly&&<aside class="profile-verification" aria-labelledby="groove-verification-title">
        <div class="profile-verification-heading"><h3 id="groove-verification-title">Weryfikacja rowka</h3><span class={`groove-status ${verified?'verified':''}`} role="status">{verified?'Potwierdzony pomiarem':'Niezweryfikowany'}</span></div>
        <div class="profile-assumed-width"><span>Założenie próbki</span><strong>{preview.samples?.map(r=>`${grooveMm(r.used_diameter)} mm`).join(' · ')||'—'}</strong></div>
        <output class="profile-width-result" aria-label="Wyliczona szerokość skrawania" aria-live="polite"><span>Wyliczona szerokość skrawania</span><strong>{preview.error?'—':`${grooveMm(preview.width)} mm`}</strong><span>{preview.error?'Uzupełnij poprawne pomiary.':`przy zagłębieniu ${mm(preview.depth)} mm`}</span></output>
        {!preview.error&&<p class="profile-calculation">{preview.atSample?`${grooveMm(preview.samples[0].used_diameter)} + ${mm(preview.samples[0].width)} − ${mm(preview.samples[0].measured_width)} = ${grooveMm(preview.width)} mm`:`Model z ${preview.samples.length} ${preview.samples.length===1?'pomiaru':'pomiarów'} · wynik dla aktualnego zagłębienia`}</p>}
        <label class="groove-confirmation"><input id="profile-groove-confirmed" type="checkbox" checked={verified} disabled={locked||!!preview.error} onChange={e=>{setAcceptedKey(e.currentTarget.checked?preview.key:'');setSaved('');setDirty(true);}}/><span>Zmierzyłem rowek i potwierdzam zgodność z wartością <strong>{preview.error?'—':`${grooveMm(preview.width)} mm`}</strong>.</span></label>
        <p class="profile-verification-help">Zmierz prosty fragment rowka wokół próbki, poza narożnikami. To szerokość jednego przejazdu.</p>
        {preview.error&&<p class="field-error" role="status">{preview.error}</p>}
        <div class="profile-verification-footer"><p class={error?'field-error':''} role={error?'alert':saved||dirty?'status':undefined}>{error||saved||(dirty?'Niezapisane zmiany — wynik dotyczy edytowanych ustawień.':'Zmiana kalibracji lub parametrów frezowania wymaga ponownego potwierdzenia.')}</p>
          <div class="profile-toolbar"><button id="profile-save" class="primary" type="submit" disabled={locked||!!preview.error}>{creating?'Utwórz profil':'Zapisz zmiany'}</button><button type="button" disabled={locked} onClick={()=>{setCreating(false);load(profile);}}>Anuluj</button></div>
        </div>
      </aside>}
    </form>
  </section>;
}

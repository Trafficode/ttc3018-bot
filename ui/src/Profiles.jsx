import {useState} from 'preact/hooks';
import {IconTrash} from '@tabler/icons-preact';
import {ParameterField} from './ParameterField.jsx';
import {AppSelect} from './AppSelect.jsx';
import './profiles.css';

export const defaultProfile={id:'default',name:'Domyślny',model:null,fingerprint:'default',depth:.05,conditions:{tip:.1,angle:30,feed:100,plunge:20,power:300}};
export const grooveMm=value=>Number(value).toLocaleString('pl-PL',{minimumFractionDigits:2,maximumFractionDigits:2});

export function ProfileBar({controller,cnc}) {
  const store=cnc.calibration_profiles;
  const selected=store?.selected||defaultProfile;
  const ready=controller.known.value&&!controller.active.value&&!controller.pending.value&&!store?.error&&(!cnc.connected||controller.manualReady.value);
  const operation=cnc.job?.pcb_flow;
  if(operation && operation.kind!=='isolation')return <div class="profile-bar"><strong>{operation.title}</strong><span>Głębokość −{operation.depthMm} mm · parametry zlecenia CAM</span>{selected.id!=='default'&&<span role="alert">Profil jest inny — wczytaj etap ponownie.</span>}</div>;
  const profiles=(store?.profiles||[defaultProfile]).filter(profile=>!profile.draft);
  return <div class="profile-bar"><AppSelect id="active-profile" label="Profil pliku NC" value={selected.draft?'':selected.id} disabled={!store||!ready} onChange={id=>controller.send({action:'profile_select',profile_id:id})} options={profiles.map(profile=>({value:profile.id,label:profile.name}))}/>
    {selected.draft&&<span role="status">Wybierz gotowy profil do pliku NC.</span>}</div>;
}

function exportProfile(profile) {
  const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,profile},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`bark-beetle-profile-${profile.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

const fields=[
  ['depth','Zagłębienie w miedź · mm',[.01,.02,.03,.04,.05,.06,.08,.1,.12,.15,.2,.25,.3],.01,.3,.001,'Głębokość cięcia poniżej zmierzonej powierzchni PCB.'],
  ['tip','Końcówka frezu · mm',[.05,.1,.15,.2,.3,.4,.5],.01,.5,.01,'Szerokość czubka frezu V z oznaczenia narzędzia.'],
  ['angle','Kąt frezu · °',[10,15,20,30,45,60,90],10,90,1,'Pełny kąt ostrza.'],
  ['feed','Posuw XY · mm/min',[10,20,30,50,75,100,150,200,250,300],10,300,1,'Prędkość ruchu poziomego podczas cięcia.'],
  ['plunge','Wejście Z · mm/min',[1,5,10,15,20,30,40,50,75,100],1,100,1,'Prędkość opuszczania frezu. Sondowanie ma osobny posuw.'],
  ['power','Prędkość obrotowa wrzeciona · %',[100,200,300,400,500,600,700,800,900,1000],1,1000,1,'Prędkość zadana na skali panelu: 100% odpowiada S1000. Panel nie mierzy rzeczywistych obrotów.'],
];

export function ProfileSettings({controller,profile,creating,locked,ask,onSaved,onCancel,onDirty}) {
  const base=creating?defaultProfile:profile;
  const readonly=!creating&&profile.id==='default';
  const [name,setName]=useState(creating?'':profile.name);
  const [tool,setTool]=useState({...base.conditions,depth:base.depth??base.observations?.[0]?.depth??.05});
  const [cornerFeed,setCornerFeed]=useState(base.corner_feed??'');
  const [dirty,setDirty]=useState(false),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  const cornerValid=cornerFeed===''||(Number(cornerFeed)>=1&&Number(cornerFeed)<=Number(tool.feed));
  const valid=name.trim()&&cornerValid&&fields.every(([key,,,min,max])=>tool[key]!==''&&Number(tool[key])>=min&&Number(tool[key])<=max);
  const disabled=locked||saving;
  const toolChanged=fields.some(([key])=>Number(tool[key])!==Number(key==='depth'?base.depth:base.conditions[key]));
  function change(){setDirty(true);onDirty(true);setError('');}
  async function save(event) {
    event.preventDefault();
    if(readonly){onSaved();return;}
    if(!valid||disabled)return;
    setError('');setSaving(true);
    try {
      const payload={action:creating?'profile_create':'profile_update',source:'settings',name:name.trim(),
        profile_id:profile.id,profile_fingerprint:profile.fingerprint,
        corner_feed:cornerFeed===''?null:Number(cornerFeed),
        ...Object.fromEntries(fields.map(([key])=>[key,Number(tool[key])]))};
      if(!await controller.send(payload)){
        setError(controller.profileError.value||'Nie zapisano ustawień.');return;
      }
      if(creating){
        const id=controller.createdProfile.value?.id;
        if(!id||!await controller.send({action:'profile_select',profile_id:id})){
          setError('Zapisano szkic. Wybierz go z listy profili.');onCancel();return;
        }
      }
      onSaved();
    }finally{setSaving(false);}
  }
  return <form class="profile-setup" onSubmit={save}>
    <label class="parameter-field profile-name-field">Nazwa profilu<input id="profile-name" autoComplete="off" value={name} maxLength="40" disabled={readonly||disabled}
      placeholder="Np. V30-015" onInput={e=>{setName(e.currentTarget.value);change();}}/></label>
    <fieldset class="profile-fieldset"><legend>Parametry frezowania</legend><div class="profile-tool-grid">{fields.map(([key,label,options,min,max,step,help])=>
      <ParameterField key={key} id={`profile-${key}`} label={label} value={tool[key]??''} options={options} min={min} max={max} step={step} help={help}
        disabled={readonly||disabled} onChange={value=>{setTool({...tool,[key]:value});change();}} scale={key==='power'?.1:1}
        format={key==='power'?value=>`${value/10}%`:undefined}/>)}
      <div class="parameter-field">
        <label for="profile-corner-feed">Posuw na zakrętach · mm/min</label>
        <input id="profile-corner-feed" type="number" min="1" max={tool.feed} step="any" value={cornerFeed}
          placeholder="Jak posuw XY" disabled={readonly||disabled} aria-describedby="profile-corner-help"
          onInput={e=>{setCornerFeed(e.currentTarget.value);change();}}/>
        <small id="profile-corner-help">{cornerValid?'Tylko test profilu. Zwolnienie 0,5 mm przed i za zakrętem.':'Wpisz wartość od 1 mm/min do posuwu XY.'}</small>
      </div>
    </div></fieldset>
    {readonly&&<p class="service-hint">Profil domyślny ma stałe parametry. Aby zapisać kalibrację, wybierz „Nowy profil”.</p>}
    {profile.model&&!creating&&toolChanged&&<p class="service-hint" role="status">Zmiana parametrów wymaga świeżego testu. Do czasu kalibracji profil nie będzie dostępny w projektach.</p>}
    {error&&<p class="field-error" role="alert">{error}</p>}
    <div class="button-row profile-actions"><button class="primary" type="submit" disabled={disabled||(!readonly&&!valid)}>
      {readonly?'Przejdź do testu':saving?'Zapisywanie…':'Zapisz i przejdź do testu'}</button>
      {(creating||dirty)&&<button type="button" disabled={disabled} onClick={onCancel}>Anuluj</button>}</div>
    {!creating&&!readonly&&<div class="profile-management">
      {profile.model&&<button type="button" disabled={disabled||dirty} onClick={()=>exportProfile(profile)}>Eksport do CAM</button>}
      <button id="profile-delete" class="profile-delete" type="button" disabled={disabled||dirty}
        onClick={()=>ask('profile_delete',{profile_id:profile.id,profile_fingerprint:profile.fingerprint,name:profile.name})}><IconTrash size={17} aria-hidden="true"/>Usuń profil</button>
    </div>}
  </form>;
}

import {useEffect, useState} from 'preact/hooks';
import {probeSettings} from './probe-settings.js';
import './probe-settings.css';

const groups = [
  ['Sondowanie Z', [
    ['max_descent_mm','max','Maksymalny zjazd Z','mm',.1,10,'any',
      'Limit szukania zera Z, także w teście profilu. Pomiar pojedynczego punktu siatki jest ograniczony do 1,4 mm.'],
    ['z_feed_mm_min','z-feed','Posuw sondowania Z','mm/min',10,60,1,
      'Opuszczanie sondy przy pomiarze zera i punktów siatki.'],
  ]],
  ['Przejazdy nad materiałem', [
    ['travel_clearance_mm','height','Wysokość przejazdu','mm',1,10,'any',
      'Wspólny prześwit sondy, frezu i wiertła. Plik NC może przewidywać większą wysokość.'],
    ['xy_feed_mm_min','travel','Posuw przejazdu XY','mm/min',25,300,1,
      'Wspólny posuw między punktami pomiaru, ścieżkami i otworami.'],
  ]],
];
const fields = groups.flatMap(([,items]) => items);
const formValues = settings => Object.fromEntries(fields.map(([key]) => [key,String(settings[key])]));

export function ProbeSettingsPanel({controller,cnc}) {
  const settings=probeSettings(cnc);
  const [draft,setDraft]=useState(()=>formValues(settings));
  const [saving,setSaving]=useState(false);
  useEffect(()=>setDraft(formValues(settings)),[settings.revision]);
  const values=Object.fromEntries(fields.map(([key])=>[key,Number(draft[key])]));
  const valid=fields.every(([key,,,,min,max,step])=>
    values[key]>=min&&values[key]<=max&&(step==='any'||Number.isInteger(values[key])));
  const dirty=fields.some(([key])=>values[key]!==settings[key]);
  const locked=saving||!settings.revision||!controller.connectReady.value;
  async function save(event){
    event.preventDefault();
    if(locked||!valid||(!dirty&&!settings.error))return;
    setSaving(true);
    try{
      await controller.send({action:'probe_settings_save',revision:settings.revision,...values});
    }finally{setSaving(false);}
  }
  return <div class="probe-settings-panel">
    <h2>Ustawienia stanowiska</h2>
    <form onSubmit={save}>
      {groups.map(([title,items])=><fieldset key={title} disabled={locked}>
        <legend>{title}</legend>
        <div class="probe-settings-fields">
          {items.map(([key,id,label,unit,min,max,step,help])=><div class="probe-setting" key={key}>
            <label for={`probe-setting-${id}`}>{label}</label>
            <div class="probe-setting-input"><input id={`probe-setting-${id}`} type="number"
              inputMode={step==='any'?'decimal':'numeric'} min={min} max={max} step={step}
              required value={draft[key]} aria-describedby={`probe-setting-${id}-hint`}
              onInput={event=>{
                controller.probeSettingsError.value='';
                setDraft({...draft,[key]:event.currentTarget.value});
              }}/><span>{unit}</span></div>
            <small id={`probe-setting-${id}-hint`}>{help}</small>
          </div>)}
        </div>
      </fieldset>)}
      {valid&&values.max_descent_mm<1&&<p class="probe-settings-note">Przy limicie poniżej 1 mm sonda może nie dosięgnąć miedzi w punktach siatki.</p>}
      {settings.error&&<p class="field-error" role="alert">Nie udało się odczytać ustawień. Sprawdź wartości i zapisz je ponownie.</p>}
      {controller.probeSettingsError.value&&<p class="field-error" role="alert">{controller.probeSettingsError.value}</p>}
      <div class="probe-settings-actions">
        <button class="primary" type="submit" disabled={locked||!valid||(!dirty&&!settings.error)}>{saving?'Zapisywanie…':'Zapisz ustawienia'}</button>
        <small role="status">{locked&&!saving?'Zmiany można zapisać, gdy frezarka jest bezczynna.':dirty?'Masz niezapisane zmiany.':''}</small>
      </div>
    </form>
  </div>;
}

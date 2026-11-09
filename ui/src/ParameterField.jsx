import {useState} from 'preact/hooks';
import {FieldHelp} from './FieldHelp.jsx';

export function ParameterField({id,label,value,onChange,options,min,max,step=1,help,disabled=false,format=v=>String(v).replace('.',',')}) {
  const [custom,setCustom]=useState(false);
  const values=[...new Set([...options, ...(String(value).trim() && Number.isFinite(Number(value)) ? [Number(value)] : [])])].sort((a,b)=>a-b);
  return <div class="parameter-field"><div class="field-caption"><label for={id}>{label}</label>{help && <FieldHelp id={id} label={label}>{help}</FieldHelp>}</div><select id={id} aria-describedby={help?`${id}-help`:undefined} value={custom?'custom':String(value)} disabled={disabled} onChange={e=>{if(e.currentTarget.value==='custom')setCustom(true);else {setCustom(false);onChange(e.currentTarget.value);}}}>{!String(value).trim()&&<option value="">Wybierz wartość</option>}{values.map(v=><option key={v} value={String(v)}>{format(v)}</option>)}<option value="custom">Własna wartość…</option></select>{custom&&<input id={`${id}-custom`} type="number" aria-label={`${label} — własna wartość`} aria-describedby={help?`${id}-help`:undefined} min={min} max={max} step={step} value={value} disabled={disabled} onInput={e=>onChange(e.currentTarget.value)}/>}</div>;
}

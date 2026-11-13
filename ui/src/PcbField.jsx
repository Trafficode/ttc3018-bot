import {ParameterField} from './ParameterField.jsx';
import {pcbFields,pcbPresets} from './pcb-fields.js';
export function PcbNumber({name,value,onChange,disabled=false,prefix='process'}){
  const field=pcbFields[name],id=`${prefix}-${name}`;
  return <ParameterField id={id} label={field.label} value={value??''}
    onChange={onChange} disabled={disabled} min={field.min} max={field.max}
    step={field.unit==='mm'? .01 : 1} help={field.help} scale={field.scale||1}
    options={pcbPresets[name]||[]} format={number=>name==='drillDiameterMm' && number===0
      ? 'Według pliku PCB' : `${String(Number((number*(field.scale||1)).toFixed(6))).replace('.',',')} ${field.unit}`}/>;
}

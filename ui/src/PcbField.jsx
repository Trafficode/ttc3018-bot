import {FieldHelp} from './FieldHelp.jsx';
import {pcbFields} from './pcb-fields.js';
export function PcbNumber({name,value,onChange,disabled=false,prefix='process'}){
  const field=pcbFields[name],id=`${prefix}-${name}`;
  return <div class="pcb-field"><div class="field-caption"><label for={id}>{field.label}</label><FieldHelp id={id} label={field.label}>{field.help}</FieldHelp></div><div class="field-value"><input id={id} type="number" required step="any" min={field.min} max={field.max} value={value} disabled={disabled} aria-describedby={`${id}-help`} onInput={event=>onChange(event.currentTarget.value)}/><small>{field.unit}</small></div></div>;
}

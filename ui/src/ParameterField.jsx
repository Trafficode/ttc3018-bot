import {useEffect, useRef, useState} from 'preact/hooks';
import {AppSelect} from './AppSelect.jsx';
import {FieldHelp} from './FieldHelp.jsx';

export function ParameterField({id, label, value, onChange, options, min, max,
  step = 1, help, disabled = false, scale = 1,
  format = v => String(v * scale).replace('.', ',')}) {
  const [custom, setCustom] = useState(false);
  const input = useRef();
  const values = [...new Set([...options,
    ...(String(value).trim() && Number.isFinite(Number(value)) ? [Number(value)] : [])])].sort((a, b) => a - b);
  useEffect(() => { if (custom) input.current?.focus(); }, [custom]);
  const display = value === '' ? '' : Number((Number(value) * scale).toFixed(6));
  return <div class="parameter-field">
    <div class="field-caption"><label id={`${id}-label`} for={id}>{label}</label>
      {help && <FieldHelp id={id} label={label}>{help}</FieldHelp>}</div>
    <AppSelect id={id} labelledBy={`${id}-label`} value={custom ? 'custom' : String(value)}
      disabled={disabled} onChange={next => {
        if (next === 'custom') setCustom(true);
        else { setCustom(false); onChange(String(next)); }
      }} options={[...values.map(number => ({value: String(number), label: format(number)})),
        {value: 'custom', label: 'Własna wartość…'}]}/>
    {custom && <input ref={input} id={`${id}-custom`} type="number"
      aria-label={`${label} — własna wartość`} aria-describedby={help ? `${id}-help` : undefined}
      min={min * scale} max={max * scale} step={step * scale} value={display}
      disabled={disabled} onInput={event => {
        const next = event.currentTarget.value;
        onChange(next === '' ? '' : String(Number((Number(next) / scale).toFixed(6))));
      }}/>}
  </div>;
}

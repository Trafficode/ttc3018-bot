import {AppSelect} from './AppSelect.jsx';

export function RetentionSelect({id, value, onChange, disabled = false,
  label = 'Sposób oddzielenia', allowThrough = true}) {
  const options = [{value: 'tabs', label: 'Mostki'},
    {value: 'skin', label: 'Cienka warstwa'}];
  if (allowThrough) options.push({value: 'through', label: 'Na wylot'});
  return <AppSelect id={id} label={label} value={value} options={options}
    onChange={onChange} disabled={disabled}/>;
}

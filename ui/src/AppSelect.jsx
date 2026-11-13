import {useEffect, useRef, useState} from 'preact/hooks';
import {IconCheck, IconChevronDown} from '@tabler/icons-preact';
import './retention-select.css';

export function AppSelect({id, label, labelledBy, value, options, onChange,
  disabled = false, placeholder = 'Wybierz…'}) {
  const root = useRef(), trigger = useRef(), menu = useRef();
  const [open, setOpen] = useState(false), [active, setActive] = useState(0);
  const [position, setPosition] = useState({});
  const selected = options.findIndex(option => String(option.value) === String(value));
  const labelId = labelledBy || `${id}-label`;

  function show(index = Math.max(0, selected)) {
    if (disabled || !options.length) return;
    const rect = trigger.current.getBoundingClientRect();
    const below = innerHeight - rect.bottom - 18, above = rect.top - 18;
    const height = Math.min(320, options.length * 46 + 10, Math.max(below, above));
    setPosition({width: Math.min(rect.width, innerWidth - 24),
      left: Math.max(12, Math.min(rect.left, innerWidth - rect.width - 12)),
      top: below >= height ? rect.bottom + 6 : Math.max(12, rect.top - height - 6),
      maxHeight: height});
    setActive(index); setOpen(true);
  }

  function choose(index) {
    const option = options[index];
    if (!option || disabled) return;
    setOpen(false); trigger.current?.focus();
    if (String(option.value) !== String(value)) onChange(option.value);
  }

  function keyDown(event) {
    if (disabled || !options.length) return;
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) event.preventDefault();
    if (event.key === 'Escape') { setOpen(false); event.stopPropagation(); }
    else if (event.key === 'Tab') setOpen(false);
    else if (['Enter', ' '].includes(event.key)) open ? choose(active) : show();
    else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1
        : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      if (!open) show(['Home', 'End'].includes(event.key) ? index : Math.max(0, selected));
      else setActive(index);
    }
  }

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (open) menu.current?.querySelector(`#${id}-option-${active}`)?.scrollIntoView({block: 'nearest'});
  }, [open, active]);
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const scroll = event => { if (!menu.current?.contains(event.target)) setOpen(false); };
    const close = () => setOpen(false);
    document.addEventListener('pointerdown', outside);
    window.addEventListener('scroll', scroll, true); window.addEventListener('resize', close);
    return () => { document.removeEventListener('pointerdown', outside);
      window.removeEventListener('scroll', scroll, true); window.removeEventListener('resize', close); };
  }, [open]);

  return <div class="retention-choice app-select" ref={root}>
    {label && <label id={labelId} for={id}>{label}</label>}
    <button ref={trigger} id={id} type="button" role="combobox"
      aria-labelledby={`${labelId} ${id}-value`} aria-haspopup="listbox"
      aria-expanded={open} aria-controls={open ? `${id}-options` : undefined}
      aria-activedescendant={open ? `${id}-option-${active}` : undefined}
      disabled={disabled} onClick={() => open ? setOpen(false) : show()} onKeyDown={keyDown}
      onBlur={event => { if (!root.current?.contains(event.relatedTarget)) setOpen(false); }}>
      <span id={`${id}-value`}>{selected < 0 ? placeholder : options[selected].label}</span>
      <IconChevronDown size={17} class="select-chevron"/>
    </button>
    {open && <div ref={menu} id={`${id}-options`} role="listbox" aria-labelledby={labelId}
      class="app-select-menu" style={position}>
      {options.map((option, index) => <div key={option.value} id={`${id}-option-${index}`}
        role="option" aria-selected={String(option.value) === String(value)}
        class={`select-option ${index === active ? 'active' : ''}`}
        onPointerMove={() => setActive(index)} onPointerDown={event => event.preventDefault()}
        onClick={() => choose(index)}><span>{option.label}</span>
        {String(option.value) === String(value) && <IconCheck size={17}/>}</div>)}
    </div>}
  </div>;
}

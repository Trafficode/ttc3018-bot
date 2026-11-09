import {useEffect,useRef,useState} from 'preact/hooks';
import {IconCheck,IconChevronDown} from '@tabler/icons-preact';
import './retention-select.css';

const choices=[
  {value:'skin',label:'Cienka warstwa'},
  {value:'tabs',label:'Cztery mostki'}
];

export function RetentionSelect({id,value,onChange,disabled=false,label='Oddzielenie PCB'}) {
  const root=useRef(),trigger=useRef();
  const [open,setOpen]=useState(false),[active,setActive]=useState(0);
  const [position,setPosition]=useState({});
  const selected=Math.max(0,choices.findIndex(choice=>choice.value===value));

  function show(index=selected) {
    if(disabled)return;
    const rect=trigger.current.getBoundingClientRect();
    const width=Math.min(rect.width,innerWidth-24),height=100;
    setPosition({width,left:Math.max(12,Math.min(rect.left,innerWidth-width-12)),
      top:rect.bottom+height+6<=innerHeight?rect.bottom+6:Math.max(12,rect.top-height-6)});
    setActive(index);
    setOpen(true);
  }

  function choose(index) {
    if(disabled)return;
    setOpen(false);
    trigger.current?.focus();
    if(choices[index].value!==value)onChange(choices[index].value);
  }

  function keyDown(event) {
    if(disabled)return;
    if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'].includes(event.key))event.preventDefault();
    if(event.key==='Escape'){setOpen(false);event.stopPropagation();return;}
    if(event.key==='Tab'){setOpen(false);return;}
    if(event.key==='ArrowDown' || event.key==='ArrowUp'){
      const step=event.key==='ArrowDown'?1:-1;
      if(!open)show();else setActive((active+step+choices.length)%choices.length);
    }else if(event.key==='Home' || event.key==='End'){
      const index=event.key==='Home'?0:choices.length-1;
      if(!open)show(index);else setActive(index);
    }else if(event.key==='Enter' || event.key===' '){
      if(open)choose(active);else show();
    }
  }

  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  useEffect(()=>{
    if(!open)return;
    const outside=event=>{if(!root.current?.contains(event.target))setOpen(false);};
    const close=()=>setOpen(false);
    document.addEventListener('pointerdown',outside);
    window.addEventListener('scroll',close,true);
    window.addEventListener('resize',close);
    return()=>{
      document.removeEventListener('pointerdown',outside);
      window.removeEventListener('scroll',close,true);
      window.removeEventListener('resize',close);
    };
  },[open]);

  return <div class="retention-choice app-select" ref={root}>
    <label id={`${id}-label`} for={id}>{label}</label>
    <button ref={trigger} id={id} type="button" role="combobox"
      aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="listbox"
      aria-expanded={open} aria-controls={`${id}-options`} disabled={disabled}
      aria-activedescendant={open?`${id}-option-${active}`:undefined}
      onClick={()=>open?setOpen(false):show()} onKeyDown={keyDown}
      onBlur={event=>{if(!root.current?.contains(event.relatedTarget))setOpen(false);}}>
      <span id={`${id}-value`}>{choices[selected].label}</span>
      <IconChevronDown size={17} class="select-chevron"/>
    </button>
    {open && <div id={`${id}-options`} role="listbox" aria-labelledby={`${id}-label`}
      class="app-select-menu" style={position}>
      {choices.map((choice,index)=><div key={choice.value} id={`${id}-option-${index}`}
        role="option" aria-selected={choice.value===value}
        class={index===active?'select-option active':'select-option'}
        onPointerMove={()=>setActive(index)} onPointerDown={event=>event.preventDefault()}
        onClick={()=>choose(index)}>
        <span>{choice.label}</span>{choice.value===value && <IconCheck size={17}/>}
      </div>)}
    </div>}
  </div>;
}

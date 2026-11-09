import {useEffect,useLayoutEffect,useRef,useState} from 'preact/hooks';
import {IconInfoCircle,IconChevronDown} from '@tabler/icons-preact';
import './simplify.css';

export function FieldHelp({id,label,children}) {
  const [open,setOpen]=useState(false),[position,setPosition]=useState({});
  const root=useRef(),button=useRef(),tip=useRef();
  useLayoutEffect(()=>{if(!open)return;const rect=button.current.getBoundingClientRect(),width=Math.min(280,innerWidth-24),height=tip.current.getBoundingClientRect().height;setPosition({width,left:Math.max(12,Math.min(rect.left,innerWidth-width-12)),top:rect.bottom+height+10<innerHeight?rect.bottom+7:Math.max(12,rect.top-height-7)});},[open,position.width]);
  useEffect(()=>{if(!open)return;const close=event=>{if(!root.current?.contains(event.target))setOpen(false);};const key=event=>{if(event.key==='Escape'){event.stopPropagation();setOpen(false);button.current?.focus();}};const scroll=()=>setOpen(false);document.addEventListener('pointerdown',close);document.addEventListener('keydown',key);window.addEventListener('scroll',scroll,true);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',key);window.removeEventListener('scroll',scroll,true);};},[open]);
  return <span class="field-help" ref={root}><button ref={button} type="button" class="info-button" aria-label={`Informacja: ${label}`} aria-expanded={open} aria-controls={`${id}-help`} onClick={()=>setOpen(!open)}><IconInfoCircle size={16}/></button><span ref={tip} id={`${id}-help`} role="tooltip" class="help-popover" hidden={!open} style={position}>{children}</span></span>;
}

export function Disclosure({title,children,open=false,className=''}) {
  return <details class={`clear-disclosure ${className}`} open={open}><summary><span>{title}</span><IconChevronDown class="disclosure-chevron" size={17}/></summary><div class="disclosure-body">{children}</div></details>;
}

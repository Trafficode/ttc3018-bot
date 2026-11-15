import {useEffect, useRef, useState} from 'preact/hooks';
import {IconChevronLeft, IconRefresh, IconTool, IconAlertTriangle} from '@tabler/icons-preact';
import {FlowSetup, FlowRun} from './PcbFlow.jsx';
import {AppSelect} from './AppSelect.jsx';
import {formatProbeDelta} from './probe-readings.js';
import './probe-readings.css';

const stateNames = {running:'Obliczanie na RPi', ready:'Izolacja gotowa', blocked:'Geometria zablokowana', failed:'Błąd obliczeń', cancelled:'Anulowano', interrupted:'Przerwano', corrupt:'Uszkodzony wynik'};

export function CamPreparation({source, controller, api, onPrepared, locked,onOpenProfiles}) {
  const cad = source.files.filter(file => file.kind === 'cad');
  const [filename, setFilename] = useState(cad[0]?.name || '');
  return <section class="cam-preparation" aria-label="Przygotowanie CAM">
    <h3><IconTool size={18}/>Wykonaj PCB · {source.project.side}</h3>
    {cad.length > 1 && <AppSelect id="cam-archive" label="Archiwum CAD" value={filename} disabled={locked} onChange={setFilename} options={cad.map(file=>({value:file.name,label:file.name}))}/>}
    <FlowSetup source={source} controller={controller} api={api} onPrepared={onPrepared} locked={locked} filename={filename} onOpenProfiles={onOpenProfiles}/>
  </section>;
}

export function ToolpathPreview({geometry, findings=[], probePoints=[], showDatum=false, compactLabel, probeReadingsHistorical=false}) {
  const canvas = useRef(null);
  const measured=probePoints.filter(point=>Number.isFinite(point.z));
  const columns=new Set(probePoints.map(point=>point.x.toFixed(4))).size;
  const rows=new Set(probePoints.map(point=>point.y.toFixed(4))).size;
  const aspect=geometry?(geometry.bounds[2]-geometry.bounds[0])/(geometry.bounds[3]-geometry.bounds[1]||1):2;
  const minWidth=probePoints.length?Math.ceil(Math.max(280,(columns-1)*66+80,(rows-1)*25*aspect+80)):0;
  useEffect(()=>{
    if (!geometry || !canvas.current) return;
    const target=canvas.current;
    function draw(){
    const context=target.getContext('2d');
    const pixel=target.width/Math.max(target.clientWidth,1);
    const [gx0,gy0,gx1,gy1]=geometry.bounds;
    const [x0,y0,x1,y1]=showDatum?[Math.min(0,gx0,...probePoints.map(p=>p.x)),Math.min(0,gy0,...probePoints.map(p=>p.y)),Math.max(gx1,...probePoints.map(p=>p.x)),Math.max(gy1,...probePoints.map(p=>p.y))]:geometry.bounds;
    const padding=probePoints.length?Math.max(18,30*pixel):18, scale=Math.min((target.width-padding*2)/(x1-x0),(target.height-padding*2)/(y1-y0));
    const offsetX=(target.width-(x1-x0)*scale)/2,offsetY=(target.height-(y1-y0)*scale)/2;
    const point=([x,y])=>[offsetX+(x-x0)*scale,target.height-offsetY-(y-y0)*scale];
    context.clearRect(0,0,target.width,target.height);
    function trace(path){path.forEach((value,index)=>{const [x,y]=point(value);if(index===0)context.moveTo(x,y);else context.lineTo(x,y);});}
    if(showDatum){const [bx,by]=point([gx0,gy1]);context.strokeStyle='#c8c4ba';context.lineWidth=1;context.strokeRect(bx,by,(gx1-gx0)*scale,(gy1-gy0)*scale);}
    context.fillStyle='#b98b54';
    geometry.copper.forEach(rings=>{context.beginPath();rings.forEach(ring=>{trace(ring);context.closePath();});context.fill('evenodd');});
    context.fillStyle='rgba(187,37,37,.72)';
    (geometry.removedCopper||[]).forEach(rings=>{context.beginPath();rings.forEach(ring=>{trace(ring);context.closePath();});context.fill('evenodd');});
    context.strokeStyle='#087f8c';context.lineWidth=.8;
    geometry.paths.forEach(path=>{context.beginPath();trace(path);context.stroke();});
    (geometry.holes||[]).forEach(hole=>{const[x,y]=point(hole.point);context.beginPath();context.arc(x,y,hole.diameterMm*scale/2,0,Math.PI*2);context.stroke();});
    probePoints.forEach(value=>{const[x,y]=point([value.x,value.y]);context.beginPath();context.arc(x,y,4*pixel,0,Math.PI*2);context.fillStyle=Number.isFinite(value.z)?'#287b5c':'#fff';context.fill();context.strokeStyle='#28323c';context.stroke();});
    if(showDatum){
      const [x,y]=point([0,0]);context.strokeStyle='#9b5600';context.lineWidth=2;
      context.beginPath();context.moveTo(x,y-12);context.lineTo(x,y);context.lineTo(x+12,y);context.stroke();
      context.fillStyle='#28323c';context.font='14px sans-serif';context.fillText('X/Y 0,0',x+8,y-8);
    }
    context.fillStyle='#bb2525';
    findings.forEach(item=>{const[x,y]=point([item.x,item.y]);context.beginPath();context.arc(x,y,4,0,Math.PI*2);context.fill();});
    context.save();
    context.font=`600 ${12*pixel}px ui-monospace,monospace`;
    context.textAlign='center';context.textBaseline='middle';
    measured.forEach(value=>{
      const [x,y]=point([value.x,value.y]),text=formatProbeDelta(value.z);
      const width=context.measureText(text).width+8*pixel,height=19*pixel;
      const left=Math.max(3*pixel,Math.min(target.width-width-3*pixel,x-width/2));
      const top=y-height-7*pixel<3*pixel?y+7*pixel:y-height-7*pixel;
      context.fillStyle='#fffdf6';context.fillRect(left,top,width,height);
      context.strokeStyle=probeReadingsHistorical?'#806c4b':'#287b5c';
      context.lineWidth=pixel;context.strokeRect(left,top,width,height);
      context.fillStyle='#202a30';context.fillText(text,left+width/2,top+height/2);
    });
    context.restore();
    }
    draw();
    const observer=new ResizeObserver(draw);observer.observe(target);
    return()=>observer.disconnect();
  },[geometry,findings,probePoints,showDatum,compactLabel,probeReadingsHistorical]);
  return <figure class="cam-preview"><div class="probe-map-scroll"><canvas ref={canvas} width="720" height={compactLabel?360:520} style={probePoints.length?{minWidth:`${minWidth}px`,maxHeight:'none',height:'auto',display:'block'}:undefined} role="img" aria-label="Podgląd od strony frezowania. Miedź brązowa, środek ścieżki frezu niebieski, problemy czerwone. Etykiety ΔZ w mm względem pierwszego styku bazowego."/></div><figcaption>{geometry.removedCopper?.length>0&&<strong class="pad-trim-legend">Czerwone pola: usuwana miedź · </strong>}{compactLabel||<>Miedź · ścieżka frezu · {findings.length ? 'problemy zaznaczone na czerwono' : 'widok od strony obróbki'}<small>G54: lewy dolny narożnik · +X w prawo · +Y w górę</small></>}</figcaption>{measured.length>0&&<details class="probe-delta-readings"><summary>ΔZ [mm] od pierwszego styku bazowego · {measured.length}/{probePoints.length}{probeReadingsHistorical?' · odczyty archiwalne':''}</summary><ol>{measured.map((point,index)=><li key={point.number||index} title={`X ${point.x.toFixed(3)} mm · Y ${point.y.toFixed(3)} mm`}><span>Punkt {point.number||index+1}</span><strong>{formatProbeDelta(point.z)} mm</strong></li>)}</ol></details>}</figure>;
}

export function CamPrograms({controller, api, locked, initial, onLoaded, onSource}) {
  const [items,setItems]=useState([]), [selected,setSelected]=useState(initial?.id || null);
  const [geometry,setGeometry]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const heading=useRef(null);
  const item=items.find(value=>value.id===selected);
  const findings=item?.report?.checks?.findings || [];
  async function refresh() {
    try {const result=await (await api('/api/cam')).json();setItems(result.programs);setError('');}
    catch(cause){setError(cause.message);}
  }
  useEffect(()=>{let active=true; async function update(){if(active)await refresh();}update();const timer=setInterval(update,2500);return()=>{active=false;clearInterval(timer);};},[]);
  useEffect(()=>{if(initial?.id)setSelected(initial.id);},[initial?.id]);
  useEffect(()=>{
    setGeometry(null); heading.current?.focus();
    if(!item?.artifacts?.['preview.json'])return;
    let active=true;
    api(`/api/cam/preview/${item.id}`).then(response=>response.json()).then(value=>{if(active)setGeometry(value);}).catch(cause=>{if(active)setError(cause.message);});
    return()=>{active=false;};
  },[selected,item?.state]);
  async function action(route) {
    setBusy(true);setError('');
    try {await api(`/api/cam/${route}`,{method:'POST',body:JSON.stringify({id:item.id})});if(route==='select'){await controller.refresh(true);onLoaded(`Wczytano izolację ${item.project.name}. Wiercenie i obrys pozostają nieprzygotowane. Start wymaga przygotowania.`);}else await refresh();}
    catch(cause){setError(cause.message);}
    finally{setBusy(false);}
  }
  return <section class="cam-programs" aria-label="Programy obróbki">
    <div class="library-heading">{selected ? <button type="button" onClick={()=>setSelected(null)}><IconChevronLeft size={18}/>Wszystkie programy</button> : <strong>Programy obróbki</strong>}<button type="button" aria-label="Odśwież programy" onClick={refresh}><IconRefresh size={18}/></button></div>
    {error && <p role="alert">{error}</p>}
    {!selected ? <div class="library-list">{!items.length && <p>Brak programów. Wybierz paczkę z Tractor i przygotuj operacje na RPi.</p>}{items.map(value=><button type="button" key={value.id} onClick={()=>setSelected(value.id)}><span><strong>{value.project?.name || 'Nieczytelny wynik'}</strong><small>{value.processProfile?.name || value.profile?.name} · {value.createdAt ? new Date(value.createdAt).toLocaleString('pl-PL') : ''}</small></span><span>{value.stale && value.state==='ready' ? 'Profil zmieniony' : stateNames[value.state]}</span></button>)}</div> : !item ? <p role="status">Wczytywanie wyniku…</p> : <>
      <div class="library-project" ref={heading} tabIndex={-1}><strong>{item.project?.name}</strong><small>{item.processProfile?.name || item.profile?.name} · PCB {item.project?.boardHash.slice(0,12)} · {item.project?.side}</small></div>
      <p class="cam-result-state" role="status">{item.state==='blocked' && <IconAlertTriangle size={18}/>}<strong>{item.workflow && item.state==='ready' ? 'Programy PCB gotowe' : stateNames[item.state]}</strong>{item.durationSeconds != null && <small>{item.durationSeconds} s obliczeń</small>}</p>
      {item.state==='running' && <><progress aria-label="Obliczanie izolacji"/><p>RPi oblicza ścieżki i sprawdza przejazd frezu. Możesz zamknąć kolekcję.</p><button type="button" disabled={busy} onClick={()=>action('cancel')}>Anuluj obliczenia</button></>}
      {item.error && <p role="alert">{item.error}</p>}
      {item.packageId && item.state!=='running' && <button type="button" onClick={()=>onSource(item.packageId)}>Wróć do paczki · oblicz ponownie</button>}
      {item.stale && <p role="alert">Profil, kalibracja lub silnik CAM zmieniły się. Oblicz izolację ponownie z paczki źródłowej.</p>}
      {item.report && <>
        <div class="cam-operation-status"><strong>{item.workflow ? 'Wybrane operacje PCB' : 'Izolacja'} · {item.state==='ready' ? 'gotowe' : 'zablokowane'}</strong><span>{item.workflow ? (item.report.sequence||[]).map(operation=>operation.title).join(' · ') : 'Wiercenie i obrys · nieprzygotowane'}</span></div>
        {Number.isFinite(item.report.diameterMm) && <dl class="cam-facts"><div><dt>Rowek / głębokość</dt><dd>{item.report.diameterMm.toFixed(3)} / {item.report.depthMm} mm</dd></div><div><dt>Program</dt><dd>{item.report.commands} poleceń</dd></div></dl>}
        {geometry && <ToolpathPreview geometry={geometry} findings={findings}/>}
        {findings.length > 0 && <details open><summary>Problemy geometrii ({findings.length})</summary><ul class="cam-findings">{findings.map((value,index)=><li key={index}>{value.message} <strong>X {value.x.toFixed(2)} · Y {value.y.toFixed(2)} mm</strong></li>)}</ul><p>Źródłowe PCB i średnica frezu pozostają bez zmian.</p></details>}
        <details><summary>Co sprawdzono i czego wynik nie potwierdza</summary><p>Składnia GRBL, profil, parametry, ruchy po wycofaniu Z, przejazd frezu, chroniona miedź i rozdzielenie {item.report.checks.protectedIslands} obszarów miedzi. Model płaski 2D; bez kontroli zacisków, rzeczywistej powierzchni i próbnego frezowania.</p><p>{item.report.transform.datum}. {item.report.transform.mirrorX ? 'Odbicie X dla B.Cu.' : 'Bez odbicia.'} Wycofanie Z {item.report.clearanceMm} mm.</p><small>Pakiet {item.packageId.slice(0,12)} · profil {item.profile.fingerprint.slice(0,12)} · {item.report.engine}</small></details>
      </>}
      {item.state==='ready' && (item.workflow ? <FlowRun item={item} controller={controller} api={api} locked={locked} onLoaded={onLoaded}/> : <button type="button" class="cam-primary" disabled={locked || busy || item.stale} onClick={()=>action('select')}>Wczytaj izolację do przygotowania</button>)}
    </>}
  </section>;
}

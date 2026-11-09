import {useEffect, useRef, useState} from 'preact/hooks';
import {IconChevronLeft, IconRefresh, IconTool, IconAlertTriangle} from '@tabler/icons-preact';
import {FlowSetup, FlowRun} from './PcbFlow.jsx';

const stateNames = {running:'Obliczanie na RPi', ready:'Izolacja gotowa', blocked:'Geometria zablokowana', failed:'Błąd obliczeń', cancelled:'Anulowano', interrupted:'Przerwano', corrupt:'Uszkodzony wynik'};

export function CamPreparation({source, controller, api, onPrepared, locked}) {
  const profile = controller.cnc.value.calibration_profiles?.selected;
  const cad = source.files.filter(file => file.kind === 'cad');
  const [filename, setFilename] = useState(cad[0]?.name || '');
  const diameter = profile?.model ? profile.model.intercept_mm + profile.model.slope * profile.depth : NaN;
  return <section class="cam-preparation" aria-label="Przygotowanie CAM">
    <h3><IconTool size={18}/>Wykonaj PCB · {source.project.side}</h3>
    <p>Jeden plan, trzy etapy. Po każdej zmianie narzędzia nowy pomiar Z i osobny Start.</p>
    {cad.length > 1 && <label>Archiwum CAD<select disabled={locked} value={filename} onChange={event => setFilename(event.currentTarget.value)}>{cad.map(file=><option key={file.name}>{file.name}</option>)}</select></label>}
    <details><summary>Profil ścieżek: {profile?.name || 'wybierz skalibrowany profil'}</summary><dl class="cam-facts"><div><dt>Rowek z kalibracji</dt><dd>{Number.isFinite(diameter) ? `${diameter.toFixed(3)} mm` : 'Brak kalibracji'}</dd></div><div><dt>Głębokość</dt><dd>{Number.isFinite(profile?.depth) ? `${profile.depth} mm` : '—'}</dd></div><div><dt>Posuw XY / Z</dt><dd>{profile?.conditions?.feed} / {profile?.conditions?.plunge} mm/min</dd></div></dl><small>Profil wybierzesz w pasku nad panelem. Nowa kalibracja wymaga ponownego obliczenia.</small></details>
    <FlowSetup source={source} controller={controller} api={api} onPrepared={onPrepared} locked={locked} filename={filename}/>
  </section>;
}

function ToolpathPreview({geometry, findings}) {
  const canvas = useRef(null);
  useEffect(()=>{
    if (!geometry || !canvas.current) return;
    const target=canvas.current, context=target.getContext('2d');
    const [x0,y0,x1,y1]=geometry.bounds;
    const padding=18, scale=Math.min((target.width-padding*2)/(x1-x0),(target.height-padding*2)/(y1-y0));
    const point=([x,y])=>[padding+(x-x0)*scale,target.height-padding-(y-y0)*scale];
    context.clearRect(0,0,target.width,target.height);
    function trace(path){path.forEach((value,index)=>{const [x,y]=point(value);if(index===0)context.moveTo(x,y);else context.lineTo(x,y);});}
    context.fillStyle='#b98b54';
    geometry.copper.forEach(rings=>{context.beginPath();rings.forEach(ring=>{trace(ring);context.closePath();});context.fill('evenodd');});
    context.strokeStyle='#087f8c';context.lineWidth=.8;
    geometry.paths.forEach(path=>{context.beginPath();trace(path);context.stroke();});
    context.fillStyle='#bb2525';
    findings.forEach(item=>{const[x,y]=point([item.x,item.y]);context.beginPath();context.arc(x,y,4,0,Math.PI*2);context.fill();});
  },[geometry,findings]);
  return <figure class="cam-preview"><canvas ref={canvas} width="720" height="520" role="img" aria-label="Podgląd od strony frezowania. Miedź brązowa, środek ścieżki frezu niebieski, problemy czerwone."/><figcaption>Miedź · ścieżka frezu · {findings.length ? 'problemy zaznaczone na czerwono' : 'widok od strony obróbki'}<small>G54: lewy dolny narożnik · +X w prawo · +Y w górę</small></figcaption></figure>;
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
    {!selected ? <div class="library-list">{!items.length && <p>Brak programów. Wybierz paczkę z Tractor i przygotuj izolację na RPi.</p>}{items.map(value=><button type="button" key={value.id} onClick={()=>setSelected(value.id)}><span><strong>{value.project?.name || 'Nieczytelny wynik'}</strong><small>{value.profile?.name} · {value.createdAt ? new Date(value.createdAt).toLocaleString('pl-PL') : ''}</small></span><span>{value.stale && value.state==='ready' ? 'Profil zmieniony' : stateNames[value.state]}</span></button>)}</div> : !item ? <p role="status">Wczytywanie wyniku…</p> : <>
      <div class="library-project" ref={heading} tabIndex={-1}><strong>{item.project?.name}</strong><small>{item.profile?.name} · PCB {item.project?.boardHash.slice(0,12)} · {item.project?.side}</small></div>
      <p class="cam-result-state" role="status">{item.state==='blocked' && <IconAlertTriangle size={18}/>}<strong>{item.workflow && item.state==='ready' ? 'Programy PCB gotowe' : stateNames[item.state]}</strong>{item.durationSeconds != null && <small>{item.durationSeconds} s obliczeń</small>}</p>
      {item.state==='running' && <><progress aria-label="Obliczanie izolacji"/><p>RPi oblicza ścieżki i sprawdza przejazd frezu. Możesz zamknąć kolekcję.</p><button type="button" disabled={busy} onClick={()=>action('cancel')}>Anuluj obliczenia</button></>}
      {item.error && <p role="alert">{item.error}</p>}
      {item.packageId && item.state!=='running' && <button type="button" onClick={()=>onSource(item.packageId)}>Wróć do paczki · oblicz ponownie</button>}
      {item.stale && <p role="alert">Profil, kalibracja lub silnik CAM zmieniły się. Oblicz izolację ponownie z paczki źródłowej.</p>}
      {item.report && <>
        <div class="cam-operation-status"><strong>Izolacja · {item.state==='ready' ? 'gotowa' : 'zablokowana'}</strong><span>{item.workflow ? item.state==='ready' ? 'Wiercenie i obrys · programy gotowe' : 'Zlecenie zablokowane · żaden etap nie zostanie wczytany' : 'Wiercenie i obrys · nieprzygotowane'}</span></div>
        <dl class="cam-facts"><div><dt>Rowek / głębokość</dt><dd>{item.report.diameterMm.toFixed(3)} / {item.report.depthMm} mm</dd></div><div><dt>Program</dt><dd>{item.report.commands} poleceń</dd></div></dl>
        {geometry && <ToolpathPreview geometry={geometry} findings={findings}/>}
        {findings.length > 0 && <details open><summary>Problemy geometrii ({findings.length})</summary><ul class="cam-findings">{findings.map((value,index)=><li key={index}>{value.message} <strong>X {value.x.toFixed(2)} · Y {value.y.toFixed(2)} mm</strong></li>)}</ul><p>Źródłowe PCB i średnica frezu pozostają bez zmian.</p></details>}
        <details><summary>Co sprawdzono i czego wynik nie potwierdza</summary><p>Składnia GRBL, profil, parametry, ruchy po wycofaniu Z, przejazd frezu, chroniona miedź i rozdzielenie {item.report.checks.protectedIslands} obszarów miedzi. Model płaski 2D; bez kontroli zacisków, rzeczywistej powierzchni i próbnego frezowania.</p><p>{item.report.transform.datum}. {item.report.transform.mirrorX ? 'Odbicie X dla B.Cu.' : 'Bez odbicia.'} Wycofanie Z {item.report.clearanceMm} mm.</p><small>Pakiet {item.packageId.slice(0,12)} · profil {item.profile.fingerprint.slice(0,12)} · {item.report.engine}</small></details>
      </>}
      {item.state==='ready' && (item.workflow ? <FlowRun item={item} controller={controller} api={api} locked={locked} onLoaded={onLoaded}/> : <button type="button" class="cam-primary" disabled={locked || busy || item.stale} onClick={()=>action('select')}>Wczytaj izolację do przygotowania</button>)}
    </>}
  </section>;
}

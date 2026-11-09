import {useEffect, useRef, useState} from 'preact/hooks';
import {IconBooks, IconChevronLeft, IconFileCode, IconDownload, IconRefresh} from '@tabler/icons-preact';
import './library.css';
import {CamPreparation, CamPrograms} from './CamPanel.jsx';

export function LibraryPicker({controller, locked,onOpenProfiles}) {
  const [open, setOpen] = useState(false);
  const [packages, setPackages] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const heading = useRef(null);
  const [collection, setCollection] = useState('sources');
  const [prepared, setPrepared] = useState(null);
  useEffect(() => {if (selected) heading.current?.focus();}, [selected]);
  const profile = controller.cnc.value.calibration_profiles?.selected;
  const matches = file => profile?.model ? file.cam_profile?.id === profile.id && file.cam_profile?.fingerprint === profile.fingerprint : !file.cam_profile;
  async function api(url, options = {}) {
    const response = await fetch(url, {...options, cache:'no-store', headers:{'X-PiloMill-Token':controller.data.value?.control_token || '', ...(options.body ? {'Content-Type':'application/json'} : {})}, signal:AbortSignal.timeout(15000)});
    if (!response.ok) {const value = await response.json(); throw new Error(value.error || 'Kolekcja jest niedostępna.');}
    return response;
  }
  async function refresh() {
    setBusy(true); setError('');
    try {const value = await (await api('/api/library')).json(); setPackages(value.packages);}
    catch (cause) {setError(cause.message);}
    finally {setBusy(false);}
  }
  async function showSource(id) {
    setCollection('sources'); setBusy(true); setError('');
    try {const value = await (await api('/api/library')).json(); setPackages(value.packages); const source=value.packages.find(item=>item.id===id && !item.corrupt); if(!source)throw new Error('Paczka źródłowa jest niedostępna.');setSelected(source);}
    catch(cause){setError(cause.message);setSelected(null);}
    finally{setBusy(false);}
  }
  async function load(file) {
    setBusy(true); setError('');
    try {
      await api('/api/library/select', {method:'POST', body:JSON.stringify({packageId:selected.id, name:file.name})});
      await controller.refresh(true); setOpen(false); setSelected(null); setNotice(`Wczytano ${file.name}. Start wymaga przygotowania i potwierdzenia.`);
    } catch (cause) {setError(cause.message);}
    finally {setBusy(false);}
  }
  async function download(file) {
    setBusy(true); setError('');
    try {
      const response = await api(`/api/library/files/${selected.id}/${encodeURIComponent(file.name)}`);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = file.name; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {setError(cause.message);}
    finally {setBusy(false);}
  }
  return <div class="library-picker">
    <button type="button" disabled={locked} aria-expanded={open} onClick={() => {setOpen(!open); setNotice(''); if(!open) refresh();}}><IconBooks size={18}/>Z kolekcji</button>
    {notice && <p role="status">{notice}</p>}
    {open && <section class="library-browser" aria-label="Lokalna kolekcja plików" aria-busy={busy}>
      <div class="cam-collections" role="group" aria-label="Kolekcje stanowiska"><button type="button" aria-pressed={collection==='sources'} onClick={()=>{setCollection('sources');setSelected(null);}}>Paczki z Tractor</button><button type="button" aria-pressed={collection==='programs'} onClick={()=>setCollection('programs')}>Programy obróbki</button></div>
      {collection==='programs' ? <CamPrograms controller={controller} api={api} locked={locked} initial={prepared} onSource={showSource} onLoaded={message=>{setOpen(false);setNotice(message);}}/> : <>
      <div class="library-heading">{selected ? <button type="button" disabled={busy} onClick={() => setSelected(null)}><IconChevronLeft size={18}/>Kolekcja</button> : <strong>Kolekcja stanowiska</strong>}<button type="button" aria-label="Odśwież kolekcję" disabled={busy} onClick={refresh}><IconRefresh size={18}/></button></div>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Oczekiwanie na kolekcję…</p>}
      {!selected ? <div class="library-list">{packages.length === 0 && !busy && <p>Brak zestawów. Wyślij pierwszy z Tractor: Pobierz pliki → Wyślij do frezarki.</p>}{packages.map(item => item.corrupt ? <p key={item.id}>Uszkodzony pakiet · {item.id.slice(0,8)}</p> : <button type="button" key={item.id} disabled={busy} onClick={() => setSelected(item)}><span><strong>{item.project.name}</strong><small>{new Date(item.receivedAt).toLocaleString('pl-PL')} · {item.project.side} · {item.project.boardHash.slice(0,8)}</small></span><span>{item.files.some(file => file.kind === 'program') ? `${item.files.filter(file=>file.kind==='program').length} programów` : 'Wymaga CAM'}</span></button>)}</div> : <>
        <div class="library-project" ref={heading} tabIndex={-1}><strong>{selected.project.name}</strong><small>PCB {selected.project.boardHash.slice(0,12)} · {selected.project.side}</small></div>
        {selected.files.some(file=>file.kind==='cad') && <CamPreparation key={selected.id} source={selected} controller={controller} api={api} locked={locked} onPrepared={item=>{setPrepared(item);setCollection('programs');}} onOpenProfiles={onOpenProfiles}/>}
        <details><summary>Oryginalne pliki paczki</summary><p>Wczytanie programu zastępuje bieżący plik i unieważnia poprzednią mapę powierzchni.</p>
        <div class="library-files">{selected.files.map(file => <div key={file.name}><IconFileCode size={19}/><span><strong>{file.name}</strong><small>{file.kind==='program' ? `${file.commands} poleceń · ${matches(file) ? 'Profil zgodny' : 'Niezgodny profil — Start zablokowany'}` : 'CAD · Gerbery i wiercenia'}</small></span><button type="button" disabled={busy || locked} onClick={() => file.kind==='program' ? load(file) : download(file)}>{file.kind==='program' ? 'Wczytaj' : <><IconDownload size={16}/>Pobierz</>}</button></div>)}</div>
        </details>
      </>}
      </>}
    </section>}
  </div>;
}

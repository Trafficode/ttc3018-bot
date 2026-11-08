export function probeBlockReason({cnc,known,pending,active,distance,feed}) {
  if(!known)return 'Brak aktualnego połączenia z aplikacją.';
  if(!cnc.connected)return 'Połącz CNC, aby ustawić zero sondą.';
  if(!cnc.fresh)return 'Oczekiwanie na świeży odczyt sterownika.';
  if(pending)return 'Trwa obsługa poprzedniego polecenia.';
  if(active)return 'Najpierw zakończ aktywny program lub sondowanie.';
  if(cnc.state!=='Idle')return `CNC musi stać. Aktualny stan: ${cnc.state||'brak odczytu'}.`;
  if(cnc.probe_triggered===true)return 'Wykryto STYK. Rozewrzyj krokodylki lub odsuń frez od miedzi — dopiero wtedy można rozpocząć szukanie powierzchni.';
  if(!cnc.probe_tested)return 'Zewrzyj krokodylki i przytrzymaj do wskazania STYK, potem je rozewrzyj. Test jest wymagany po połączeniu CNC.';
  if(cnc.probe_triggered!==false)return 'Brak potwierdzonego odczytu wejścia sondy.';
  if(String(distance).trim()===''||!Number.isFinite(Number(distance))||Number(distance)<.1||Number(distance)>10)return 'Maksymalny zjazd musi wynosić od 0,1 do 10 mm.';
  if(String(feed).trim()===''||!Number.isFinite(Number(feed))||Number(feed)<10||Number(feed)>60)return 'Prędkość sondowania musi wynosić od 10 do 60 mm/min.';
  if(!Array.isArray(cnc.position)||cnc.position.length!==3||!cnc.position.every(Number.isFinite))return 'Brak kompletnych współrzędnych X/Y/Z. Zaczekaj na odczyt pozycji.';
  return '';
}

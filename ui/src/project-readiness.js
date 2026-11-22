// One source for disabled buttons and the reasons shown beside them.
export function projectReadiness({cnc={},known,pending,active,busy,xyReady,bounds,
  thickness,profile,profileError,capability,done,blocked,geometryError,
  reviewRequired,reviewAccepted,previewMatches,stageId,referenceDistance,referenceFeed}) {
  const base=[];
  const add=(list,id,text)=>list.push({id,text});
  if(!known)add(base,'connection','Brak aktualnego połączenia z panelem. Poczekaj na odczyt.');
  else if(!cnc.connected)add(base,'connection','Połącz CNC przyciskiem w górnym pasku.');
  else if(!cnc.fresh)add(base,'connection','Brak świeżego odczytu CNC — poczekaj na aktualny stan i pozycję.');
  else {
    if(active)add(base,'machine','Trwa program lub pomiar. Poczekaj na zakończenie albo użyj Stop.');
    else if(cnc.state!=='Idle')add(base,'machine',`CNC nie jest bezczynne: ${cnc.state||'stan nieznany'}. Sprawdź sterownik przed kolejną próbą.`);
    if(!Array.isArray(cnc.position)||cnc.position.length!==3||!cnc.position.every(Number.isFinite))add(base,'position','Brak kompletnych współrzędnych X/Y/Z. Poczekaj na odczyt.');
    if(!cnc.probe_tested)add(base,'probe-test','Powtórz test sondy: potwierdź STYK przy zamkniętym obwodzie, potem BRAK STYKU po rozwarciu. Test jest wymagany po ponownym połączeniu.');
    if(cnc.probe_triggered===true)add(base,'probe-contact','Sonda nadal pokazuje STYK. Odsuń frez lub rozewrzyj obwód przed szukaniem powierzchni.');
    else if(cnc.probe_triggered!==false)add(base,'probe-reading','Brak odczytu wejścia sondy. Poczekaj na STYK/BRAK STYKU.');
  }
  if(pending)add(base,'pending','Trwa potwierdzanie poprzedniego polecenia.');
  if(cnc.probe_settings?.error)add(base,'probe-settings','Zapisz poprawne ustawienia sondowania przed pomiarem.');
  if(busy)add(base,'busy','Trwa przygotowanie projektu lub zapis X/Y.');
  if(!xyReady)add(base,'xy','Ustaw frez w punkcie odniesienia i naciśnij „Ustaw tutaj zero X/Y”.');
  if(!bounds)add(base,'bounds','Brak obszaru pomiaru PCB. Poczekaj na podgląd lub przygotuj go ponownie.');
  if(!Number.isFinite(Number(referenceDistance))||Number(referenceDistance)<.1||Number(referenceDistance)>10)add(base,'distance','Niepoprawny maksymalny zjazd pierwszego pomiaru Z.');
  if(!Number.isFinite(Number(referenceFeed))||Number(referenceFeed)<10||Number(referenceFeed)>60)add(base,'feed','Prędkość sondowania musi wynosić 10–60 mm/min.');
  if(stageId==='outline'&&!profile)add(base,'frame','Wybierz profil frezu obrysu, aby wyznaczyć ramę pomiaru.');
  const execute=[...base];
  if(String(thickness).trim()===''||!Number.isFinite(Number(thickness))||Number(thickness)<.3||Number(thickness)>3)add(execute,'stock','Podaj grubość laminatu: 0,3–3 mm.');
  if(!profile)add(execute,'tool','Wybierz przygotowany profil narzędzia dla tego etapu.');
  if(profileError)add(execute,'profile',profileError);
  if(!capability?.available)add(execute,'capability',capability?.reason||'Brak danych potrzebnych do wykonania tego etapu.');
  if(done)add(execute,'done','Ten etap został już wykonany. Wybierz kolejny etap lub nową płytkę.');
  if(blocked)add(execute,'geometry',geometryError||'Przejazdy nie przeszły sprawdzenia geometrii. Przygotuj podgląd i sprawdź wskazane miejsca.');
  if(reviewRequired&&!previewMatches)add(execute,'preview','Trwa wczytywanie podglądu zwężenia padów. Poczekaj na czerwone obszary.');
  else if(reviewRequired&&!reviewAccepted)add(execute,'consent','Sprawdź czerwone obszary i zaznacz akceptację zwężenia padów i ścieżek.');
  return {measure:base,execute};
}

export function firstProbePlan(cnc,distance,feed) {
  if(!Array.isArray(cnc.position)||cnc.position.length!==3||!cnc.position.every(Number.isFinite))return null;
  const travel=Number(distance);
  return {phase:'reference',start:[...cnc.position],targetZ:cnc.position[2]-travel,
    distanceMm:travel,feedMmMin:Number(feed)};
}

export function projectProbeFailure(cnc,setupId) {
  const cycle=cnc.project_cycle,probe=cnc.z_probe;
  if(cycle?.setupId!==setupId||cycle?.phase!=='failed'||!/(ALARM:5|PROBE_NO_CONTACT)/.test(String(probe?.error||cycle.error)))return null;
  // Older servers did not retain travel; only their fixed surface reference
  // can be reconstructed, not an arbitrary manual/drilling probe distance.
  const legacy=probe?.kind==='surface'&&probe.completed===0&&Array.isArray(cycle.position)
    ?firstProbePlan({position:cycle.position},1.4,20):null;
  return {error:probe?.error||cycle.error,code:String(probe?.error||cycle.error).includes('PROBE_NO_CONTACT')?'NO_CONTACT':'ALARM:5',attempt:probe?.attempt||legacy,
    reference:(probe?.attempt||legacy)?.phase==='reference'};
}

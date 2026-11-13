export const pcbFields={
  thicknessMm:{label:'Grubość laminatu',unit:'mm',min:.3,max:3,help:'Zmierz grubość tej płytki. Z niej obliczamy głębokość wiercenia i obrysu. Wpisujesz przy każdym zleceniu; pomiar Z nie mierzy grubości.'},
  skinMm:{label:'Warstwa do oddzielenia',unit:'mm',min:.15,max:.5,help:'Tyle laminatu ma pozostać pod rowkiem obrysu. Dla 1 mm laminatu i warstwy 0,2 mm frez zagłębi się na 0,8 mm. To planowana wartość, zależna od dokładności grubości i Z.'},
  uncertaintyMm:{label:'Rezerwa dokładności',unit:'mm',min:.01,max:.2,help:'Przyjęty budżet błędu grubości i ustawienia Z. Nie jest pomiarem dokładności maszyny. Musi być mniejszy od pozostawionej warstwy; wpływa też na wymagany zapas wiercenia.'},
  backingMm:{label:'Grubość podkładu',unit:'mm',min:1,max:50,help:'Zmierz drewniany podkład pod laminatem. Wiertło wejdzie w niego częściowo. Program sprawdza, czy nie przebije podkładu; nie uwzględnia metalowych mocowań w jego wnętrzu.'},
  clearanceMm:{label:'Wysokość przejazdów',unit:'mm',min:1,max:10,help:'Na tę wysokość ponad materiał podnosi się narzędzie między miejscami obróbki. Musi minąć mocowania na trasie. Wysokość sondowania ma osobne ograniczenia.'},
  breakthroughMm:{label:'Zapas przewiercenia',unit:'mm',min:.05,max:1,help:'Dodatkowe wejście w podkład, żeby otwór przeszedł całym przekrojem. Program osobno dolicza długość stożka czubka wiertła. Zapas musi pokryć nierówność powierzchni i rezerwę dokładności.'},
  drillPointAngleDeg:{label:'Kąt czubka wiertła',unit:'°',min:60,max:150,help:'Kąt ostrza z danych Twoich wierteł. Wartość 118° jest początkowym ustawieniem do sprawdzenia, nie pomiarem. Kąt służy do obliczenia głębokości pełnego przejścia otworu.'},
  drillFeed:{label:'Zagłębianie wiertła',unit:'mm/min',min:1,max:100,help:'Prędkość opuszczania wiertła w materiał. Dobierz ją dla wierteł i laminatu; zapisujesz raz w profilu.'},
  drillOverrunMm:{label:'Zagłębienie w podkładzie',unit:'mm',min:.05,max:5,help:'Odległość czubka wiertła poniżej spodu PCB. Obejmuje stożek czubka i zapas na nierówności. Program nie dolicza nic więcej. Dobierz ją tak, żeby cały otwór przeszedł przez PCB, a czubek pozostał w podkładzie.'},
  drillPower:{label:'Poziom wrzeciona · wiercenie',unit:'%',scale:.1,min:1,max:1000,help:'Procent zakresu sterowania: 100% odpowiada S1000. To nie jest pomiar obrotów RPM ani procent rzeczywistej mocy. Ustaw dla swojego wiertła i laminatu.'},
  drillDiameterMm:{label:'Średnica wiertła',unit:'mm',min:0,max:4,help:'Według pliku PCB zachowuje źródłowe średnice i tworzy osobny etap dla każdego wiertła. Konkretna średnica wymaga zgodnych otworów; program nie powiększa ani nie pomija innych otworów.'},
  millDiameterMm:{label:'Średnica frezu',unit:'mm',min:.5,max:3,help:'Rzeczywista średnica frezu płaskiego. Z niej wyliczamy odsunięcie ścieżki od obrysu PCB. Nie jest to frez V ani szerokość rowka izolacji.'},
  remainingMm:{label:'Pozostawiany laminat',unit:'mm',min:.05,max:3,help:'Grubość laminatu, który ma pozostać: na całym obwodzie dla cienkiej warstwy albo tylko w miejscach mostków. Musi być mniejsza od grubości PCB.'},
  millOverrunMm:{label:'Wejście w podkład',unit:'mm',min:.05,max:5,help:'Tyle poniżej spodu PCB schodzi frez przy cięciu na wylot. Przy mostkach dotyczy odcinków między mostkami. Cienka warstwa nie używa tego parametru.'},
  millFeed:{label:'Posuw wycinania obrysu',unit:'mm/min',min:1,max:300,help:'Prędkość poziomego ruchu frezu płaskiego. Wiercenie ma osobny posuw zagłębiania, a frez V własną kalibrację.'},
  millPlunge:{label:'Zagłębianie frezu',unit:'mm/min',min:1,max:100,help:'Prędkość pionowego wejścia frezu płaskiego w laminat. Jest oddzielna od ruchu w poziomie i od prędkości sondowania.'},
  millPower:{label:'Poziom wrzeciona · obrys',unit:'%',scale:.1,min:1,max:1000,help:'Procent sterowania wrzecionem przy wycinaniu obrysu. 100% odpowiada S1000, nie 1000 obr./min. Ustaw raz w sprawdzonym profilu narzędzia.'},
  stepDownMm:{label:'Warstwa jednego przejścia',unit:'mm',min:.02,max:.5,help:'Maksymalne pogłębienie rowka w jednym obiegu. Program sam wyliczy liczbę obiegów i ostatnie, płytsze przejście.'},
  cuttingLengthMm:{label:'Długość ostrzy frezu',unit:'mm',min:.5,max:15,help:'Długość części roboczej frezu płaskiego, nie całego narzędzia. Musi wystarczyć na docelową głębokość, żeby trzpień nie tarł o laminat.'},
  tabWidthMm:{label:'Szerokość mostka',unit:'mm',min:2,max:6,help:'Szerokość zaprogramowanej przerwy w głębokim cięciu. Średnica frezu zmniejsza rzeczywistą szerokość pozostającego połączenia przy jego końcach.'},
  tabHeightMm:{label:'Wysokość mostka',unit:'mm',min:.2,max:.8,help:'Tyle laminatu pozostaje w czterech miejscach, żeby płytka nie odpadła podczas wycinania. Mostki odcinasz po obróbce.'}
};
export const initialProcessValues={skinMm:.2,uncertaintyMm:.05,backingMm:'',breakthroughMm:.2,drillPointAngleDeg:118,drillFeed:'',drillPower:'',millFeed:'',millPlunge:'',millPower:'',stepDownMm:'',cuttingLengthMm:'',tabWidthMm:3,tabHeightMm:.3,retention:'skin',clearanceMm:3,millDiameterMm:1};
export const pcbPresets={
  thicknessMm:[.6,.8,1,1.2,1.5,1.6,2,2.4], skinMm:[.15,.2,.25,.3,.4,.5],
  uncertaintyMm:[.02,.03,.05,.08,.1,.15,.2], backingMm:[2,3,5,8,10,15,20],
  clearanceMm:[1,2,3,4,5,6,8,10], breakthroughMm:[.1,.15,.2,.25,.3,.4,.5],
  drillPointAngleDeg:[90,118,120,130,135,140],
  drillFeed:[5,10,15,20,30,40,50,60,80,100],
  drillOverrunMm:[.2,.3,.5,.8,1,1.5,2,3,4,5],
  millFeed:[10,20,30,50,60,75,100,150,200,250,300],
  millPlunge:[1,5,10,15,20,30,40,50,75,100],
  remainingMm:[.1,.15,.2,.3,.4,.5,.8,1,1.5,2],
  millOverrunMm:[.1,.2,.3,.5,.8,1,1.5,2,3,4,5],
  drillPower:[100,200,300,400,500,600,700,800,900,1000],
  millPower:[100,200,300,400,500,600,700,800,900,1000],
  drillDiameterMm:[0,.3,.4,.5,.6,.7,.8,.9,1,1.1,1.2,1.5,2,2.5,3,4],
  millDiameterMm:[.5,.6,.8,1,1.2,1.5,2,2.5,3],
  stepDownMm:[.02,.05,.1,.15,.2,.25,.3,.4,.5],
  cuttingLengthMm:[1,1.5,2,3,4,5,6,8,10,12,15],
  tabWidthMm:[2,2.5,3,4,5,6], tabHeightMm:[.2,.25,.3,.4,.5,.6,.8]
};
export function outlineEditorValues(profile={}){
  return {...initialProcessValues,...profile,outlineDepthMode:'remaining',
    remainingMm:profile.remainingMm??(profile.retention==='tabs'?profile.tabHeightMm:profile.skinMm)??.2,
    millOverrunMm:profile.millOverrunMm??profile.breakthroughMm??.2,
    stepDownMm:profile.stepDownMm??.2,tabWidthMm:''};
}
export function outlineDefault(key,values){
  return key==='stepDownMm' ? .2 : Math.max(3,Number(values.millDiameterMm)+2);
}
export function toolFieldKeys(kind,values){
  if(kind==='drilling')return ['drillDiameterMm','drillFeed','drillOverrunMm','clearanceMm'];
  if(kind==='outline' && values.outlineDepthMode==='remaining')return ['millDiameterMm','millFeed','millPlunge','clearanceMm',
    ...(values.retention!=='through'?['remainingMm']:[]),...(values.retention!=='skin'?['millOverrunMm']:[]),
    ...['stepDownMm',...(values.retention==='tabs'?['tabWidthMm']:[])].filter(key=>values[key]!=='' && values[key]!==undefined)];
  if(kind==='outline')return ['millDiameterMm','millFeed','millPlunge','millPower','stepDownMm','cuttingLengthMm','backingMm','clearanceMm','breakthroughMm','uncertaintyMm',...(values.retention==='skin'?['skinMm']:values.retention==='tabs'?['tabWidthMm','tabHeightMm']:[])];
  return Object.keys(pcbFields).filter(key=>!['thicknessMm','drillDiameterMm','drillOverrunMm','remainingMm','millOverrunMm'].includes(key));
}
export function profileValuesValid(values,kind='legacy'){
  if(!toolFieldKeys(kind,values).every(key=>{const field=pcbFields[key];return values[key]!=='' && values[key]!==undefined && Number.isFinite(Number(values[key])) && Number(values[key])>=field.min && Number(values[key])<=field.max;}))return false;
  if(kind==='drilling')return Number(values.drillDiameterMm)===0 || Number(values.drillDiameterMm)>=.3;
  if(!['skin','tabs',...(kind==='outline'?['through']:[])].includes(values.retention))return false;
  if(kind==='outline' && values.outlineDepthMode==='remaining')return values.retention!=='tabs' ||
    Number(values.tabWidthMm==='' || values.tabWidthMm===undefined ? outlineDefault('tabWidthMm',values) : values.tabWidthMm)>Number(values.millDiameterMm);
  if(values.retention==='skin' && Number(values.skinMm)<=Number(values.uncertaintyMm))return false;
  return values.retention!=='tabs' || Number(values.tabWidthMm)>Number(values.millDiameterMm);
}
export function friendlyError(message){return Object.entries(pcbFields).reduce((text,[key,field])=>text.replaceAll(key,field.label),message);}

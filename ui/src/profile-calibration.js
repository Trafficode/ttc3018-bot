import {toolDiameter} from './service-geometry.js';

const limits={tip:[.01,.5],angle:[10,90],feed:[10,300],plunge:[1,100],power:[1,1000]};
const number=value=>String(value??'').trim()!=='' && Number.isFinite(Number(value)) ? Number(value) : NaN;
const within=(value,low,high)=>Number.isFinite(value)&&value>=low&&value<=high;

// The same single-offset / least-squares model as monitor.profiles.fit_profile.
// This preview never changes a saved profile or authorizes machine work.
export function calibrationPreview(tool,rows) {
  const conditions=Object.fromEntries(Object.keys(limits).map(key=>[key,number(tool[key])]));
  const depth=number(tool.depth);
  if(!within(depth,.01,.3)||Object.entries(limits).some(([key,[low,high]])=>!within(conditions[key],low,high)))return {error:'Uzupełnij poprawne parametry frezowania.'};
  if(!rows.length||rows.length>8)return {error:'Uzupełnij pomiar kalibracyjny.'};
  const samples=rows.map(row=>({depth:number(row.depth),width:number(row.width),measured_width:number(row.measured_width),
    used_diameter:row.used_diameter==null?toolDiameter(conditions.tip,conditions.angle,number(row.depth)):number(row.used_diameter)}));
  const points=samples.map(row=>[row.depth,row.used_diameter+row.width-row.measured_width]);
  if(samples.some((row,i)=>!within(row.depth,.01,.3)||!within(row.width,.2,2)||!within(row.measured_width,.01,3)||
    !within(row.used_diameter,.001,1.999999999)||!Number.isFinite(points[i][1])||points[i][1]<=0||points[i][1]>=2))return {error:'Sprawdź wymiary próbki i zmierzony pasek. Wyliczony rowek musi mieć dodatnią szerokość poniżej 2 mm.'};
  let slope,intercept;
  if(points.length===1){slope=2*Math.tan(conditions.angle*Math.PI/360);intercept=points[0][1]-slope*points[0][0];}
  else {
    const depths=points.map(p=>p[0]),min=Math.min(...depths),max=Math.max(...depths);
    if(max-min<.01-1e-9)return {error:'Przy kilku pomiarach potrzebne są różne zagłębienia (różnica ≥0,01 mm).'};
    if(depth<min-1e-9||depth>max+1e-9)return {error:'Zagłębienie frezowania jest poza zakresem pomiarów.'};
    const mx=depths.reduce((a,b)=>a+b,0)/points.length,my=points.reduce((a,p)=>a+p[1],0)/points.length;
    slope=points.reduce((a,p)=>a+(p[0]-mx)*(p[1]-my),0)/points.reduce((a,p)=>a+(p[0]-mx)**2,0);intercept=my-slope*mx;
    if(slope<=0)return {error:'Rowek nie rośnie z głębokością. Sprawdź pomiary.'};
  }
  const width=intercept+slope*depth;
  if(!Number.isFinite(width)||width<=0)return {error:'Profil przewiduje niedodatnią szerokość rowka.'};
  const evidence={depth,conditions,samples};
  return {width,depth,samples,evidence,key:JSON.stringify(evidence),atSample:points.length===1&&Math.abs(depth-points[0][0])<1e-9};
}

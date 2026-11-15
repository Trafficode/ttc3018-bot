// Surface samples already contain contact Z minus the initial reference touch.
export function formatProbeDelta(value) {
  if(!Number.isFinite(value))return '—';
  const rounded=Math.round(value*1000)/1000;
  return (rounded>0?'+':rounded<0?'−':'')+Math.abs(rounded).toFixed(3).replace('.',',');
}

export function projectProbeReadings(points,cnc,setupId,stageId) {
  const map=cnc.surface_map,cycle=cnc.project_cycle;
  const sameCycle=cycle?.setupId===setupId&&cycle?.stage===stageId&&
    ['probing','cutting','completed','measured','failed','stopped'].includes(cycle.phase);
  const sameJob=cycle?.measureOnly?map?.job_id===null:
    !!cycle?.jobId&&map?.job_id===cycle.jobId&&cnc.job?.id===cycle.jobId;
  const near=(a,b)=>Math.abs(a-b)<.001;
  const sameGrid=map?.points?.length===points.length&&points.every(p=>
    map.points.some(q=>near(p.x,q.x)&&near(p.y,q.y)));
  const show=!!map?.id&&map.kind==='surface'&&sameCycle&&sameJob&&sameGrid;
  return points.map(point=>{
    const sample=show?map.samples?.find(s=>near(s.x,point.x)&&near(s.y,point.y)):null;
    return {...point,z:Number.isFinite(sample?.z)?sample.z:undefined};
  });
}

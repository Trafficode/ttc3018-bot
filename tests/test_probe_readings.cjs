const assert=require('node:assert/strict');
(async()=>{
 const {formatProbeDelta,projectProbeReadings}=await import('../ui/src/probe-readings.js');
 assert.equal(formatProbeDelta(.14000000001),'+0,140');
 assert.equal(formatProbeDelta(-.025),'−0,025');
 assert.equal(formatProbeDelta(-.0001),'0,000');
 assert.equal(formatProbeDelta(undefined),'—');
 const points=[{number:1,x:1,y:2},{number:2,x:3,y:2}];
 const cnc={job:{id:'job'},project_cycle:{setupId:'setup',stage:'isolation',jobId:'job',phase:'probing'},
  surface_map:{id:'map',kind:'surface',job_id:'job',points,samples:[{...points[0],z:.14}]}};
 let result=projectProbeReadings(points,cnc,'setup','isolation');
 assert.equal(result[0].z,.14,'first grid point keeps offset from initial touch, not from itself');
 assert.equal(result[1].z,undefined,'unmeasured point has no invented zero');
 cnc.project_cycle.phase='completed';assert.equal(projectProbeReadings(points,cnc,'setup','isolation')[0].z,.14);
 for(const change of [
  {project_cycle:{...cnc.project_cycle,phase:'preparing'}},
  {project_cycle:{...cnc.project_cycle,setupId:'other'}},
  {project_cycle:{...cnc.project_cycle,stage:'outline'}},
  {job:{id:'other'}},
  {surface_map:{...cnc.surface_map,job_id:'other'}},
  {surface_map:{...cnc.surface_map,points:[{x:8,y:9}]}}
 ])assert.ok(projectProbeReadings(points,{...cnc,...change},'setup','isolation').every(p=>p.z===undefined));
 cnc.project_cycle={...cnc.project_cycle,phase:'measured',measureOnly:true};
 cnc.surface_map.job_id=null;
 assert.equal(projectProbeReadings(points,cnc,'setup','isolation')[0].z,.14);
 assert.equal(cnc.surface_map.samples[0].z,.14,'display does not alter probe data');
 console.log('Probe labels: reference offsets, signs, partial maps and setup/job/grid binding PASS');
})().catch(e=>{console.error(e);process.exitCode=1});

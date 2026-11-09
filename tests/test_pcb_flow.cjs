const assert = require('node:assert/strict');
(async()=>{
  const {createSurfacePlan,surfaceRequest,surfaceMatches,surfaceHeights}=await import('../ui/src/surface-plan.js');
  const bounds={X:[-.5,100.5],Y:[-.5,115.5]};
  const settings={columns:3,rows:3,area:bounds,perimeterOnly:true};
  const plan=createSurfacePlan(bounds,settings);
  assert.equal(plan.points.length,8);
  assert.equal(plan.points.some(point=>point.x===50 && point.y===57.5),false);
  assert.equal(surfaceRequest(bounds,settings).perimeterOnly,true);
  const map={id:'fixture',job_id:'current',columns:3,rows:3,area:bounds,perimeterOnly:true,valid:true,samples:plan.points.map(point=>({...point,z:.01}))};
  assert.equal(surfaceMatches(map,'current',settings,bounds),true);
  assert.equal(surfaceMatches(map,'other',settings,bounds),false);
  assert.equal(surfaceMatches(map,'current',{...settings,perimeterOnly:false},bounds),false);
  assert.equal(surfaceHeights(map).source,'reference');
  assert.equal(createSurfacePlan(bounds,{...settings,columns:5}).error!=null,true);
  console.log('PCB flow: exact eight-point frame map, reference heights and job binding PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});

const assert = require('node:assert/strict');

(async () => {
  const {createSurfacePlan, defaultSurfaceSettings} = await import('../ui/src/surface-plan.js');
  const {surfaceRequest, surfaceMatches} = await import('../ui/src/surface-plan.js');
  const bounds = {X: [-2, 8], Y: [5, 15]};
  const settings = defaultSurfaceSettings(bounds);
  const plan = createSurfacePlan(bounds, settings);
  assert.equal(plan.points.length, 9);
  assert.deepEqual(plan.points[0], {number: 1, x: -2, y: 5});
  assert.deepEqual(plan.points[3], {number: 4, x: 8, y: 10});
  assert.deepEqual(plan.points[8], {number: 9, x: 8, y: 15});
  assert.equal(plan.spacingX, 5);
  assert.equal(plan.spacingY, 5);
  assert.equal(new Set(plan.points.map(point => `${point.x},${point.y}`)).size, 9);
  assert.equal(createSurfacePlan(bounds, {...settings, columns: 5, rows: 5}).points.length, 25);
  assert.equal(createSurfacePlan(bounds, {...settings, columns: 11, rows: 11}).points.length, 121);
  for (const invalid of [0, 1, 12, 2.5, '', 'NaN', Infinity]) {
    assert(createSurfacePlan(bounds, {...settings, columns: invalid}).error);
  }
  for (const area of [
    {X: [0, 8], Y: [5, 15]}, {X: [-2, 8], Y: [5, 14]},
    {X: [8, -2], Y: [5, 15]}, {X: [-301, 8], Y: [5, 15]},
    {X: ['', 8], Y: [5, 15]}, {X: [NaN, 8], Y: [5, 15]}
  ]) assert(createSurfacePlan(bounds, {...settings, area}).error);
  const expanded = createSurfacePlan(bounds, {...settings, area: {X: [-5, 10], Y: [0, 20]}});
  assert.equal(expanded.error, undefined);
  assert.deepEqual(bounds, {X: [-2, 8], Y: [5, 15]}, 'Planning cannot mutate uploaded bounds');
  assert.deepEqual(settings.area, bounds);
  assert.equal(surfaceRequest(bounds, settings).clearance, 2);
  assert.equal(surfaceRequest(bounds, settings).distance, 1.5);
  assert.equal(surfaceRequest(bounds, {...settings,distance:1}).distance,1,
    'An explicitly selected search limit must never be extended silently');
  assert.equal(1 - surfaceRequest(bounds, settings).distance, -0.5,
    'A reference starting at the single-probe Z=1 retract must search past nominal Z=0');
  assert.equal(surfaceRequest(bounds, {...settings, clearance:0}).error !== undefined, true);
  assert.equal(surfaceRequest(bounds, {...settings, below:3}).error !== undefined, true);
  const map = {id:'map', job_id:'file', columns:3, rows:3, area:bounds};
  assert.equal(surfaceMatches(map,'file',settings,bounds),true);
  assert.equal(surfaceMatches(map,'other',settings,bounds),false);
  assert.equal(surfaceMatches(map,'file',{...settings,columns:5},bounds),false);
  const {surfaceHeights} = await import('../ui/src/surface-plan.js');
  const centered = createSurfacePlan({X:[-5,5],Y:[-5,5]}, {columns:2,rows:2,area:{X:[-5,5],Y:[-5,5]}});
  const measured = {...centered, samples:centered.points.map(point => ({...point,z:0.2+point.x*0.01+point.y*0.02}))};
  assert.equal(surfaceHeights({...measured,samples:measured.samples.slice(0,3)}).source,null);
  const heights = surfaceHeights(measured);
  assert.equal(heights.source,'interpolated');
  assert(Math.abs(heights.min + 0.15) < 1e-9);
  assert(Math.abs(heights.max - 0.15) < 1e-9);
  assert.equal(surfaceHeights({...map,samples:[{number:1,x:-2,y:5,z:0.02}]}).source,null,'Never extrapolate to an origin outside the map');
  assert.equal(surfaceHeights({...map,reference_xy:[0,0],samples:[{number:1,x:-2,y:5,z:0.02}]}).values[0].delta,0.02);
  const direct = surfaceHeights({reference_xy:[0,0],samples:[{number:1,x:0,y:0,z:0.01},{number:2,x:5,y:0,z:0.03}]});
  assert.equal(direct.source,'measured');
  assert(Math.abs(direct.values[1].delta - 0.02) < 1e-9,'Prefer the sampled origin over the preliminary reference');
  assert.equal(surfaceHeights(null).min,null);
  console.log('Surface grid: absolute work coordinates, serpentine order, density, coverage and finite limits: PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});

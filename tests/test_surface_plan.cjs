const assert = require('node:assert/strict');

(async () => {
  const {createSurfacePlan, defaultSurfaceSettings} = await import('../ui/src/surface-plan.js');
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
  console.log('Surface grid: absolute work coordinates, serpentine order, density, coverage and finite limits: PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});

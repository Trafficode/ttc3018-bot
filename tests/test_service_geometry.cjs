// Pure UI calculations; no browser, serial or physical machine access.
const assert = require('node:assert/strict');
(async () => {
  const {toolDiameter, serviceGeometry} = await import('../ui/src/service-geometry.js');
  assert.ok(Math.abs(toolDiameter(.1,30,.05)-.126794919243) < 1e-10);
  assert.ok(Math.abs(toolDiameter(.1,60,.1)-.215470053838) < 1e-10);
  assert.ok(toolDiameter(.1,30,.1) > toolDiameter(.1,30,.05));
  for (const args of [[0,30,.05],[.1,NaN,.05],[.1,91,.05],[.1,30,.31]]) assert.ok(Number.isNaN(toolDiameter(...args)));
  const config = {tip:.1,angle:30,depth:.05,width:.5};
  const base = serviceGeometry(config);
  assert.equal(base.strip, .5);
  for (const depth of [.025,.05,.1,.2,.3]) assert.equal(serviceGeometry({...config,depth}).strip, .5);
  assert.equal(serviceGeometry({...config,width:1.5}).strip, 1.5);
  assert.ok(serviceGeometry({...config,width:2,tip:.5,angle:90,depth:.3}).error);
  assert.ok(serviceGeometry({...config,width:0}).error);
  const calibration = {model:{intercept_mm:.1,slope:2,min_depth:.05,max_depth:.15}};
  assert.equal(serviceGeometry({...config,depth:.1,calibration}).diameter,.30000000000000004);
  assert.equal(serviceGeometry({...config,depth:.1,calibration}).strip,.5);
  assert.ok(serviceGeometry({...config,depth:.2,calibration}).error);
  assert.ok(serviceGeometry({...config,calibration:{model:{intercept_mm:-.2,slope:.5,min_depth:.01,max_depth:.3}}}).error);
  console.log('Service geometry: full-angle V formula, live depth estimate, nominal strip and footprint limits: PASS');
})().catch(error => {console.error(error);process.exitCode=1;});

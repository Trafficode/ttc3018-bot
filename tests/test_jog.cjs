// Pure distance parsing, no serial or physical machine access.
const assert = require('node:assert/strict');
(async () => {
  const {jogStep,jogAllowed} = await import('../ui/src/jog.js');
  assert.equal(jogStep(.1,''),.1);
  assert.equal(jogStep('custom','2,5'),2.5);
  assert.equal(jogStep('custom',' 25.25 '),25.25);
  for (const value of ['', 'abc','0','-1','Infinity','301','0.001']) assert.equal(jogStep('custom',value),null);
  const limits = {X:300,Y:180,Z:10};
  assert.equal(jogAllowed(25,'X',limits),true);
  assert.equal(jogAllowed(25,'Z',limits),false);
  assert.equal(jogAllowed(null,'X',limits),false);
  console.log('Custom jog: decimals, comma, invalid values and per-axis limits: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});

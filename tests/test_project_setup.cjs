const assert = require('node:assert/strict');
(async () => {
  const {canEditStock} = await import('../ui/src/project-setup.js');
  const ready = {known:true, active:false, busy:false, pending:null,
    cnc:{connected:true, fresh:true, state:'Idle'}};
  assert.equal(canEditStock(ready), true, 'connected idle CNC allows measured thickness');
  assert.equal(canEditStock({...ready, cnc:{connected:false}}), true);
  for (const change of [{known:false}, {active:true}, {busy:true}, {pending:'probe'},
    {cnc:{...ready.cnc, fresh:false}}, ...['Run','Hold','Alarm','Jog','Home','Unknown']
      .map(state => ({cnc:{...ready.cnc, state}}))]) {
    assert.equal(canEditStock({...ready, ...change}), false, JSON.stringify(change));
  }
  console.log('PCB stock: connected idle editing, active/unknown/probing locks PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });

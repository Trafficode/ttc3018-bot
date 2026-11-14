const assert=require('node:assert/strict');
(async()=>{
  const {createController}=await import('../ui/src/controller.js');
  const timers=new Map();let id=0;
  const clock={setTimeout(callback,delay){timers.set(++id,{callback,delay});return id;},clearTimeout(id){timers.delete(id);}};
  const actions=[];
  const status={control_token:'fixture',cnc:{connected:true,fresh:true,state:'Idle',position:[0,0,1],job:{state:'empty'},z_probe:{active:false},project_cycle:null}};
  const fetcher=async(url,options={})=>{if(options.body){actions.push(JSON.parse(options.body));return {ok:true,json:async()=>({})};}return {ok:true,json:async()=>structuredClone(status)};};
  const c=createController(fetcher,clock);c.start();await new Promise(setImmediate);
  await c.confirmedSend({action:'project_execute'},c.snapshot(),()=>c.manualReady.value,async()=>{
    status.cnc.project_cycle={active:true,phase:'preparing'};return {project_cycle_lease:'owner'};
  });
  assert.equal(c.active.value,true);assert.equal(c.manualReady.value,false);
  async function beat(){const [id,t]=[...timers].find(([,v])=>v.delay===2000);timers.delete(id);await t.callback();}
  await beat();assert.deepEqual(actions.at(-1),{action:'project_cycle_heartbeat',lease:'owner'});
  status.cnc.project_cycle.phase='probing';status.cnc.z_probe={active:true,state:'starting'};await c.refresh();await beat();
  assert.equal(actions.at(-1).action,'project_cycle_heartbeat');
  await c.send({action:'probe_stop'},true);assert.equal(actions.at(-1).action,'project_cycle_stop');
  status.cnc.project_cycle.phase='cutting';status.cnc.z_probe={active:false,state:'completed'};status.cnc.job={id:'cut',state:'running'};
  await c.refresh();await beat();assert.equal(actions.at(-1).lease,'owner');
  assert.ok(c.events.value.some(e=>e.text==='Pomiar Z zakończony. Cykl przechodzi do obróbki etapu.'));
  assert.equal(c.events.value.some(e=>e.text.includes('zdejmij krokodylek')),false);
  c.stop();timers.clear();const observer=createController(fetcher,clock);observer.start();await new Promise(setImmediate);
  const before=actions.length;await beat();assert.equal(actions.length,before);observer.stop();
  assert.equal(actions.some(p=>['job_start','surface_start','probe_start'].includes(p.action)),false,'browser polling never starts a physical phase');
  console.log('Project cycle: preparing/probing/cutting lease, observer isolation, global Stop and no polling starts PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});

const assert = require('node:assert/strict');
(async()=>{
  const {createController}=await import('../ui/src/controller.js');
  const timers=new Map();let timerId=0;
  const clock={setTimeout(callback,delay){timers.set(++timerId,{callback,delay});return timerId;},clearTimeout(id){timers.delete(id);}};
  const actions=[];
  const status={control_token:'fixture',cnc:{connected:true,fresh:true,state:'Idle',position:[2,3,1],job:{state:'empty'},z_probe:{active:false},calibration:{job:{state:'empty'},cycle:null}}};
  const fetcher=async(url,options={})=>{
    const payload=options.body?JSON.parse(options.body):null;
    let result={};
    if(payload){actions.push(payload);if(payload.action==='profile_test_start'){
      status.cnc.z_probe={active:true,state:'starting',kind:'profile_test'};
      status.cnc.calibration.cycle={active:true,phase:'probing'};
      result.cycle_lease='private-cycle-owner';
    }}
    return {ok:true,json:async()=>structuredClone(payload?result:status)};
  };
  async function beat(){const [id,timer]=[...timers].find(([,v])=>v.delay===2000);timers.delete(id);await timer.callback();}
  const owner=createController(fetcher,clock);owner.start();await new Promise(setImmediate);
  await owner.confirmedSend({action:'profile_test_start',confirmed:true,fixed_probe:true},owner.snapshot(),()=>owner.manualReady.value);
  await beat();assert.equal(actions.at(-1).action,'profile_test_heartbeat');
  status.cnc.z_probe={active:false,state:'completed',kind:'profile_test'};
  status.cnc.calibration.cycle.phase='cutting';status.cnc.calibration.job={id:'test',state:'running'};
  await owner.refresh();await beat();
  assert.equal(actions.at(-1).lease,'private-cycle-owner');
  assert.equal(actions.filter(p=>p.action==='profile_test_start').length,1);
  assert.equal(actions.some(p=>p.action==='profile_test_cut'),false,'polling must not issue a second start');
  owner.stop();timers.clear();
  const observer=createController(fetcher,clock);observer.start();await new Promise(setImmediate);
  const before=actions.length;await beat();assert.equal(actions.length,before);observer.stop();timers.clear();
  status.cnc.calibration.cycle.active=false;status.cnc.calibration.job.state='completed';
  await owner.refresh();owner.start();await new Promise(setImmediate);
  const complete=actions.length;await beat();assert.equal(actions.length,complete);owner.stop();
  console.log('Profile cycle: one confirmation, owner lease across probe/cut, passive observers and no polling starts PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});

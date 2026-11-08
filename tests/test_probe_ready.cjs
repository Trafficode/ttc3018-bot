const assert=require('node:assert/strict');
(async()=>{
 const {probeBlockReason}=await import('../ui/src/probe-ready.js');
 const state={known:true,pending:null,active:false,distance:10,feed:20,cnc:{connected:true,fresh:true,state:'Idle',probe_tested:true,probe_triggered:false,position:[0,0,1]}};
 assert.equal(probeBlockReason(state),'');
 assert.match(probeBlockReason({...state,cnc:{...state.cnc,probe_triggered:true}}),/Rozewrzyj/);
 assert.match(probeBlockReason({...state,cnc:{...state.cnc,probe_tested:false}}),/przytrzymaj/);
 assert.match(probeBlockReason({...state,distance:10.1}),/0,1 do 10/);
 assert.match(probeBlockReason({...state,cnc:{...state.cnc,state:'Jog'}}),/musi stać/);
 assert.match(probeBlockReason({...state,cnc:{...state.cnc,position:null}}),/współrzędnych/);
 console.log('Probe readiness: contact/release, exact blocking reason, 10 mm, Idle and coordinates PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});

const assert=require('node:assert/strict');
(async()=>{
 const {projectReadiness,firstProbePlan,projectProbeFailure}=await import('../ui/src/project-readiness.js');
 const base={cnc:{connected:true,fresh:true,state:'Idle',position:[0,0,2.182],probe_tested:true,probe_triggered:false},known:true,pending:null,active:false,busy:false,xyReady:true,bounds:{X:[0,10],Y:[0,10]},thickness:1.5,profile:{id:'v'},profileError:'',capability:{available:true},done:false,blocked:false,reviewRequired:true,reviewAccepted:true,previewMatches:true,stageId:'isolation',referenceDistance:10,referenceFeed:20};
 assert.deepEqual(projectReadiness(base),{measure:[],execute:[]});
 const cases=[['connection',{known:false}],['connection',{cnc:{...base.cnc,connected:false}}],['connection',{cnc:{...base.cnc,fresh:false}}],['machine',{cnc:{...base.cnc,state:'Alarm'}}],['machine',{active:true}],['position',{cnc:{...base.cnc,position:null}}],['probe-test',{cnc:{...base.cnc,probe_tested:false}}],['probe-contact',{cnc:{...base.cnc,probe_triggered:true}}],['probe-reading',{cnc:{...base.cnc,probe_triggered:null}}],['pending',{pending:'connect'}],['busy',{busy:true}],['xy',{xyReady:false}],['bounds',{bounds:null}],['distance',{referenceDistance:10.1}],['feed',{referenceFeed:9}],['stock',{thickness:''}],['tool',{profile:null}],['profile',{profileError:'Update profile'}],['capability',{capability:{available:false,reason:'Missing THT'}}],['done',{done:true}],['geometry',{blocked:true,geometryError:'Short circuit'}],['preview',{previewMatches:false}],['consent',{reviewAccepted:false}]];
 for(const[id,change]of cases){const r=projectReadiness({...base,...change});assert.ok(r.execute.some(v=>v.id===id&&v.text.length>10),id);}
 const diagnostic=projectReadiness({...base,thickness:'',reviewAccepted:false,capability:{available:false}});
 assert.deepEqual(diagnostic.measure,[]);assert.equal(diagnostic.execute.length,3);
 const cycle={id:'old',setupId:'setup',stage:'isolation',phase:'failed',position:[0,0,2.182],error:'ALARM:5'};
 const cnc={...base.cnc,project_cycle:cycle,z_probe:{kind:'surface',state:'failed',completed:0,error:'ALARM:5'}};
 const historical=projectProbeFailure(cnc,'setup');assert.equal(historical.code,'ALARM:5');assert.equal(historical.reference,true);
 assert.ok(Math.abs(historical.attempt.targetZ-.782)<1e-8); // Old 1.4 mm reference.
 assert.equal(projectProbeFailure(cnc,'different'),null);
 assert.deepEqual(projectReadiness({...base,cnc}).execute,[],'past alarm is not a current interlock');
 const plan=firstProbePlan(cnc,10,32);assert.equal(plan.distanceMm,10);assert.ok(Math.abs(plan.targetZ+7.818)<1e-8);
 assert.equal(plan.feedMmMin,32);
 cnc.z_probe={...cnc.z_probe,error:'PROBE_NO_CONTACT',attempt:{phase:'grid',point:7,start:[5,5,1],targetZ:-.4,distanceMm:1.4,feedMmMin:20}};
 assert.equal(projectProbeFailure(cnc,'setup').code,'NO_CONTACT');assert.equal(projectProbeFailure(cnc,'setup').reference,false);
 assert.equal(firstProbePlan({position:[]},10,20),null);
 const {createController}=await import('../ui/src/controller.js');let timer=0;const clock={setTimeout(){return ++timer},clearTimeout(){}};
 let state={control_token:'fixture',cnc:{...cnc,probe_tested:false,job:{state:'ready'},project_cycle:cycle}};const actions=[];
 const c=createController(async(url,options)=>{if(options?.body)actions.push(JSON.parse(options.body));return{ok:true,json:async()=>structuredClone(state)}},clock);
 await c.refresh();assert.match(c.notice.value.text,/Poprzednia próba/);assert.match(c.notice.value.text,/STYK/);assert.equal(c.notice.value.dismissible,true);
 c.acknowledge();assert.doesNotMatch(c.notice.value.text,/Poprzednia próba/);
 state.cnc.probe_tested=true;await c.refresh();assert.equal(c.manualReady.value,true);
 await c.confirmedSend({action:'project_execute'},c.snapshot(),()=>c.manualReady.value,async()=>{state.cnc.project_cycle={id:'new',active:true,phase:'probing'};state.cnc.z_probe={active:true,kind:'surface',state:'probing'};return{project_cycle_lease:'fixture-owner'}});
 state.cnc.project_cycle.phase='cutting';state.cnc.z_probe={active:false,state:'completed',kind:'surface'};state.cnc.job={id:'cut',state:'running'};await c.refresh();assert.doesNotMatch(c.notice.value.text,/ALARM|PROBE_NO_CONTACT/);
 assert.equal(actions.length,0,'viewing recovery never sends machine actions');
 console.log('Project readiness: every disabled reason, 10 mm reference, historical failure and fresh restart PASS');
})().catch(e=>{console.error(e);process.exitCode=1});

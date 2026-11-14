const assert=require('node:assert/strict');
(async()=>{
 const {readApiJson}=await import('../ui/src/api-json.js');
 const data={project_cycle_lease:'fixture'};
 assert.deepEqual(await readApiJson(new Response(JSON.stringify(data),{status:202}),true),data);
 await assert.rejects(()=>readApiJson(new Response(JSON.stringify({error:'Idle wymagane'}),{status:409}),true),/Idle wymagane/);
 for(const [body,status] of [['',200],['',500],['<html>proxy error</html>',502],['null',200],['[]',200]]){
  await assert.rejects(()=>readApiJson(new Response(body,{status}),true),e=>e.message.includes('nie zostało potwierdzone')&&e.message.includes('HTTP '+status));
 }
 const {createController}=await import('../ui/src/controller.js');
 let posts=0;
 const state={control_token:'fixture',cnc:{connected:true,fresh:true,state:'Idle',position:[0,0,1],job:{id:'job',state:'ready'}}};
 const c=createController(async(url,options)=>{
  if(options?.method==='POST'){posts++;return new Response('',{status:200});}
  return new Response(JSON.stringify(state));
 },{setTimeout(){return 1},clearTimeout(){}});
 await c.refresh();
 assert.equal(await c.send({action:'job_start',confirmed:true,job_id:'job'}),false);
 assert.equal(posts,1);
 assert.match(c.notice.value.text,/nie zostało potwierdzone/);
 await c.refresh();assert.equal(posts,1,'polling never retries a machine command');
 console.log('API JSON: empty/invalid responses, server errors and no automatic retry PASS');
})().catch(e=>{console.error(e);process.exitCode=1});

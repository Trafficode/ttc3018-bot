const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
(async()=>{
 const listeners={},win=Object.assign(new EventTarget(),{matchMedia:()=>({matches:false}),isSecureContext:true});
 const doc=Object.assign(new EventTarget(),{visibilityState:'visible'});
 const registrations=[];
 global.window=win;global.document=doc;
 Object.defineProperty(global,'navigator',{value:{serviceWorker:{register:async(...args)=>registrations.push(args)}},configurable:true});
 const pwa=await import('../ui/src/pwa.js');
 let reads=0;
 const controller={offline:{value:false},refresh:async()=>{reads++;}};
 pwa.attachAppLifecycle(controller);
 assert.equal(registrations[0][0],'/sw.js');
 win.dispatchEvent(new Event('offline'));assert.equal(controller.offline.value,true);
 controller.offline.value=false;win.dispatchEvent(new Event('online'));assert.equal(controller.offline.value,true);assert.equal(reads,1);
 doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(reads,1);
 doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(reads,2);
 const prompt=new Event('beforeinstallprompt',{cancelable:true});win.dispatchEvent(prompt);assert.equal(pwa.installPrompt.value,prompt);assert.equal(prompt.defaultPrevented,true);
 win.dispatchEvent(new Event('appinstalled'));assert.equal(pwa.installed.value,true);assert.equal(pwa.installPrompt.value,null);
 const cached=[];
 const caches={open:async()=>({addAll:async files=>cached.push(...files),match:async name=>'offline:'+name}),keys:async()=>[]};
 const self={location:{origin:'https://fixture.invalid'},addEventListener:(name,callback)=>{listeners[name]=callback;}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/sw.js'),'utf8'),{self,caches,URL,fetch:async()=>{throw new Error('offline');}});
 let install;listeners.install({waitUntil:promise=>{install=promise;}});await install;
 assert.deepEqual(cached.sort(),['/offline.css','/offline.html']);
 for(const [url,method,mode]of[['/api/status','GET','cors'],['/api/cnc/action','POST','cors'],['/camera.mjpg','GET','cors'],['/app.js','GET','cors']]){
  let intercepted=false;listeners.fetch({request:{url:'https://fixture.invalid'+url,method,mode},respondWith:()=>{intercepted=true;}});assert.equal(intercepted,false,url+' must stay network-only');
 }
 let navigation;listeners.fetch({request:{url:'https://fixture.invalid/',method:'GET',mode:'navigate'},respondWith:promise=>{navigation=promise;}});assert.equal(await navigation,'offline:/offline.html');
 console.log('PWA lifecycle, install events and network-only machine boundary passed.');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});

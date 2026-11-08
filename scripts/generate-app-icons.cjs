// Render the existing vector mark; no alternate logo or drawing is generated.
// Provide Playwright through NODE_PATH or the repository's development runtime.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const directory=path.resolve(__dirname,'../web/icons');await fs.mkdir(directory,{recursive:true});
 const svg=await fs.readFile(path.resolve(__dirname,'../web/favicon.svg'),'utf8');
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{for(const [name,size,maskable]of[['app-192.png',192,false],['app-512.png',512,false],['app-maskable-512.png',512,true]]){
  const page=await browser.newPage({viewport:{width:size,height:size},deviceScaleFactor:1});
  const width=maskable?Math.round(size*.75):size;
  await page.setContent(`<body style="margin:0;display:grid;place-items:center;width:${size}px;height:${size}px;background:#10161e"><img width="${width}" height="${width}" src="data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}"></body>`);
  await page.locator('img').evaluate(img=>img.decode());
  await page.screenshot({path:path.join(directory,name)});await page.close();
 }}finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});

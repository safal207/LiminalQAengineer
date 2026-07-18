#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";
import sharp from "sharp";

const args = Object.fromEntries(process.argv.slice(2).reduce((a,v,i,x)=>i%2?a:[...a,[v.replace(/^--/,""),x[i+1]]],[]));
const round3 = v => Number.isFinite(v) ? Math.round(v*1000)/1000 : null;
const median = xs => { const a=xs.filter(Number.isFinite).sort((x,y)=>x-y); if(!a.length)return null; const m=Math.floor(a.length/2); return a.length%2?a[m]:(a[m-1]+a[m])/2; };
const hash = b => crypto.createHash("sha256").update(b).digest("hex");

async function observers(page){
  await page.evaluateOnNewDocument(()=>{
    window.__lq={lcp:null,long:[]};
    try{new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lq.lcp={startTime:e.startTime,url:e.url||null,size:e.size,renderTime:e.renderTime,loadTime:e.loadTime,tag:e.element?.tagName||null,loading:e.element?.getAttribute?.("loading")||null,src:e.element?.currentSrc||e.element?.src||null};}).observe({type:"largest-contentful-paint",buffered:true});}catch(e){window.__lq.lcpError=String(e)}
    try{new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lq.long.push(e.duration)}).observe({type:"longtask",buffered:true});}catch(e){window.__lq.longError=String(e)}
  });
}

async function metrics(page,url){
  return page.evaluate(u=>{
    const r=performance.getEntriesByType("resource").find(x=>x.name===u);
    const p=performance.getEntriesByType("paint").find(x=>x.name==="first-contentful-paint");
    const l=window.__lq?.lcp||null;
    return {
      fcp_ms:p?.startTime??null,lcp_ms:l?.startTime??null,lcp_entry:l,
      asset_start_ms:r?.startTime??null,asset_end_ms:r?.responseEnd??null,
      asset_encoded_bytes:r?.encodedBodySize??null,asset_transfer_bytes:r?.transferSize??null,
      asset_to_lcp_gap_ms:Number.isFinite(l?.startTime)&&Number.isFinite(r?.responseEnd)?l.startTime-r.responseEnd:null,
      long_task_ms:(window.__lq?.long||[]).reduce((a,b)=>a+b,0),
      request_count:performance.getEntriesByType("resource").length,
      observer_errors:{lcp:window.__lq?.lcpError||null,long:window.__lq?.longError||null}
    };
  },url);
}

async function run(browser,exp,variant,round,optimized,out){
  const ctx=await browser.createBrowserContext(); const page=await ctx.newPage();
  await page.setUserAgent(exp.runtime_profile.user_agent); await page.setViewport(exp.runtime_profile.viewport); await page.setCacheEnabled(false); await observers(page);
  const c=await page.createCDPSession(); await c.send("Network.enable"); await c.send("Network.setCacheDisabled",{cacheDisabled:true});
  const n=exp.runtime_profile.network; await c.send("Network.emulateNetworkConditions",{offline:false,latency:n.latency_ms,downloadThroughput:n.download_bytes_per_second,uploadThroughput:n.upload_bytes_per_second,connectionType:n.connection_type});
  await c.send("Emulation.setCPUThrottlingRate",{rate:exp.runtime_profile.cpu_throttling_rate});
  const injection={fulfilled:0,error:null};
  if(variant==="optimized_asset"){
    await c.send("Fetch.enable",{patterns:[{urlPattern:exp.hero_url,resourceType:"Image",requestStage:"Request"}]});
    c.on("Fetch.requestPaused",async e=>{try{if(e.request.url!==exp.hero_url){await c.send("Fetch.continueRequest",{requestId:e.requestId});return;}await c.send("Fetch.fulfillRequest",{requestId:e.requestId,responseCode:200,responseHeaders:[{name:"content-type",value:"image/webp"},{name:"cache-control",value:"no-store"},{name:"x-liminalqa-counterfactual",value:"optimized-asset"}],body:optimized.toString("base64")});injection.fulfilled++;}catch(err){injection.error=String(err?.stack||err);try{await c.send("Fetch.continueRequest",{requestId:e.requestId})}catch{}}});
  }
  let navigation_error=null; const started_at=new Date().toISOString();
  try{await page.goto(exp.target_url,{waitUntil:"domcontentloaded",timeout:90000});}catch(e){navigation_error=String(e?.stack||e)}
  await new Promise(r=>setTimeout(r,exp.runtime_profile.observation_ms));
  const m=await metrics(page,exp.hero_url); const result={schema_version:"liminalqa-openai-asset-run-v1",variant,round,started_at,completed_at:new Date().toISOString(),navigation_error,injection,metrics:Object.fromEntries(Object.entries(m).map(([k,v])=>[k,typeof v==="number"?round3(v):v]))};
  await fs.mkdir(path.join(out,"asset-runs"),{recursive:true}); await fs.writeFile(path.join(out,"asset-runs",`${round}-${variant}.json`),JSON.stringify(result,null,2)+"\n");
  await ctx.close(); return result;
}

async function main(){
  if(!args.experiment||!args.chrome||!args["output-dir"])throw new Error("--experiment --chrome --output-dir required");
  const exp=JSON.parse(await fs.readFile(args.experiment,"utf8")); const out=args["output-dir"]; await fs.mkdir(out,{recursive:true});
  const response=await fetch(exp.hero_url,{headers:{"user-agent":exp.runtime_profile.user_agent}}); if(!response.ok)throw new Error(`asset fetch HTTP ${response.status}`);
  const original=Buffer.from(await response.arrayBuffer()); const optimized=await sharp(original).resize({width:exp.optimized_asset.width_px,withoutEnlargement:true}).webp({quality:exp.optimized_asset.quality,effort:exp.optimized_asset.effort}).toBuffer();
  const prep={source_url:exp.hero_url,original_bytes:original.length,optimized_bytes:optimized.length,original_sha256:hash(original),optimized_sha256:hash(optimized),byte_reduction_percent:round3((original.length-optimized.length)/original.length*100)};
  await fs.mkdir(path.join(out,"prepared"),{recursive:true}); await fs.writeFile(path.join(out,"prepared","optimized.webp"),optimized); await fs.writeFile(path.join(out,"prepared","asset.json"),JSON.stringify(prep,null,2)+"\n");
  const browser=await puppeteer.launch({executablePath:args.chrome,headless:true,args:["--no-sandbox","--disable-dev-shm-usage","--disable-background-networking"]});
  const variants={baseline:[],optimized_asset:[]};
  try{for(let r=1;r<=exp.runs_per_variant;r++){const order=r%2?["baseline","optimized_asset"]:["optimized_asset","baseline"];for(const v of order)variants[v].push(await run(browser,exp,v,r,optimized,out));}}finally{await browser.close()}
  for(const [v,runs] of Object.entries(variants)){if(runs.some(x=>x.navigation_error||!Number.isFinite(x.metrics.lcp_ms)||!Number.isFinite(x.metrics.asset_start_ms)))throw new Error(`${v} invalid run`);if(v==="optimized_asset"&&runs.some(x=>x.injection.fulfilled!==1||x.injection.error))throw new Error("optimized interception failed");}
  const keys=["fcp_ms","lcp_ms","asset_start_ms","asset_end_ms","asset_to_lcp_gap_ms","long_task_ms","request_count"];
  const summary=v=>Object.fromEntries(keys.map(k=>[k,round3(median(variants[v].map(x=>x.metrics[k])))])); const b=summary("baseline"),t=summary("optimized_asset");
  const effect=Object.fromEntries(keys.map(k=>[k,{delta:round3(t[k]-b[k]),improvement_percent:b[k]?round3((b[k]-t[k])/b[k]*100):null}]));
  const baselineMatch=variants.baseline.filter(x=>x.metrics.lcp_entry?.url===exp.hero_url).length; const supported=baselineMatch>=2&&effect.lcp_ms.delta<=-1000&&effect.lcp_ms.improvement_percent>=20&&prep.byte_reduction_percent>=50;
  const packet={schema_version:"liminalqa-openai-asset-counterfactual-v1",experiment:exp,verdict:baselineMatch<2?"INCONCLUSIVE":supported?"SUPPORTED":"NOT_SUPPORTED",confidence:baselineMatch>=2?"HIGH":"LOW",prepared_asset:prep,baseline_lcp_match_count:baselineMatch,variants:{baseline:{run_count:3,medians:b,runs:variants.baseline},optimized_asset:{run_count:3,medians:t,runs:variants.optimized_asset}},effects:effect,generated_at:new Date().toISOString()};
  const rd=path.join(out,"asset-result"); await fs.mkdir(rd,{recursive:true}); await fs.writeFile(path.join(rd,"asset-optimization-result.json"),JSON.stringify(packet,null,2)+"\n");
  const md=["# LiminalQA · OpenAI homepage exact-asset optimization counterfactual","",`**Verdict:** ${packet.verdict}  `,`**Baseline LCP asset match:** ${baselineMatch}/3  `,`**Prepared bytes:** ${prep.original_bytes} → ${prep.optimized_bytes} (${prep.byte_reduction_percent}% reduction)`,"","| Metric | Baseline | Optimized | Delta | Improvement |","|---|---:|---:|---:|---:|",...keys.map(k=>`| ${k} | ${b[k]} | ${t[k]} | ${effect[k].delta} | ${effect[k].improvement_percent}% |`),"","> One exact public asset fetch and browser-local request fulfillment only. No server state, authentication, API calls, prompts, agents, fuzzing, load testing, or vulnerability claims.",""]; await fs.writeFile(path.join(rd,"summary.md"),md.join("\n")); console.log(md.join("\n"));
}
main().catch(e=>{console.error(e?.stack||e);process.exitCode=1});

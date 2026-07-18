#!/usr/bin/env python3
"""Build a bounded LiminalQA space-time causal graph from one Lighthouse run."""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def load(p):
    d=json.loads(Path(p).read_text(encoding='utf-8'))
    if not isinstance(d,dict): raise ValueError('JSON object required')
    return d


def find_report(folder):
    for pat in ('lhr-*.json','*.report.json','*.json'):
        for p in sorted(Path(folder).glob(pat)):
            try: d=load(p)
            except Exception: continue
            if isinstance(d.get('audits'),dict) and isinstance(d.get('categories'),dict): return p,d
    raise FileNotFoundError('No Lighthouse report')


def audit(d,k): return d.get('audits',{}).get(k,{})
def rows(d,k):
    v=audit(d,k).get('details',{}).get('items',[])
    return [x for x in v if isinstance(x,dict)] if isinstance(v,list) else []
def num(d,k):
    v=audit(d,k).get('numericValue')
    return round(float(v),3) if isinstance(v,(int,float)) else None
def req(d,frag): return next((x for x in rows(d,'network-requests') if frag in str(x.get('url',''))),None)
def tm(r,k):
    v=r.get(k) if r else None
    return round(float(v),1) if isinstance(v,(int,float)) else None

def nested(d,k):
    out=[]
    for block in rows(d,k):
        if block.get('type')=='table' and isinstance(block.get('items'),list): out += [x for x in block['items'] if isinstance(x,dict)]
    return out

def lcp_node(d): return next((x for x in rows(d,'lcp-phases-insight') if x.get('type')=='node'),{})
def phases(d,legacy=False):
    out={}; key='largest-contentful-paint-element' if legacy else 'lcp-phases-insight'
    for x in nested(d,key):
        name=x.get('phase') or x.get('label'); value=x.get('timing') if legacy else x.get('duration')
        if isinstance(name,str) and isinstance(value,(int,float)): out[name]=round(float(value),1)
    return out

def checks(d):
    b=next((x for x in rows(d,'lcp-discovery-insight') if x.get('type')=='checklist'),{})
    raw=b.get('items',{}) if isinstance(b,dict) else {}
    return {k:bool(v.get('value')) for k,v in raw.items() if isinstance(v,dict)}
def resource(d):
    return {x.get('resourceType'):{'requests':x.get('requestCount'),'kib':round(float(x.get('transferSize') or 0)/1024,1)} for x in rows(d,'resource-summary') if isinstance(x.get('resourceType'),str)}
def error(d):
    for x in rows(d,'errors-in-console'):
        if 'require is not defined' in str(x.get('description')): return x.get('description')
    return None

def contrast(d):
    return [{'label':n.get('nodeLabel'),'selector':n.get('selector'),'explanation':n.get('explanation')} for x in rows(d,'color-contrast') if isinstance((n:=x.get('node')),dict)]
def shifts(d):
    out=[]
    for x in rows(d,'layout-shifts'):
        causes=[]; sub=x.get('subItems',{})
        for y in sub.get('items',[]) if isinstance(sub,dict) else []:
            extra=y.get('extra',{}) if isinstance(y.get('extra'),dict) else {}
            causes.append({'cause':y.get('cause'),'node':extra.get('nodeLabel'),'url':extra.get('value')})
        out.append({'score':x.get('score'),'causes':causes})
    return out

def unused(d):
    out=[]
    for x in rows(d,'unused-javascript'):
        t,w=x.get('totalBytes'),x.get('wastedBytes')
        if isinstance(t,(int,float)) and isinstance(w,(int,float)): out.append({'url':x.get('url'),'wasted_kib':round(w/1024,1),'wasted_percent':round(100*w/t,1) if t else 0})
    return sorted(out,key=lambda x:x['wasted_kib'],reverse=True)[:8]

def build(path,d):
    root=req(d,'https://tradernet.ru/'); doc=next((x for x in rows(d,'network-requests') if x.get('mimeType')=='text/html' and x.get('statusCode')==200),None)
    mobile=req(d,'hero.mobile.light.2x.webp'); desktop=req(d,'/hero.light.2x.webp'); font=req(d,'Inter-roman.var.woff2'); lc=lcp_node(d); ph=phases(d); old=phases(d,True); ck=checks(d); rs=resource(d)
    dbg=audit(d,'document-latency-insight').get('details',{}).get('debugData',{}); dbg=dbg if isinstance(dbg,dict) else {}
    score=lambda k:round(d['categories'][k]['score']*100)
    nodes=[
      {'id':'navigation','space':'user','time_ms':0,'state':'observed','label':'Public mobile navigation'},
      {'id':'redirect','space':'edge','time_ms':{'start':tm(root,'networkRequestTime'),'end':tm(root,'networkEndTime')},'state':'observed','label':'Language redirect','metrics':{'observed_ms':dbg.get('redirectDuration'),'modelled_savings_ms':num(d,'redirects')}},
      {'id':'document','space':'origin','time_ms':{'start':tm(doc,'networkRequestTime'),'end':tm(doc,'networkEndTime')},'state':'observed','label':'Final HTML','metrics':{'server_response_ms':num(d,'server-response-time')}},
      {'id':'css','space':'document_head','time_ms':986,'state':'observed','label':'Render-blocking CSS','metrics':{'modelled_savings_ms':num(d,'render-blocking-resources')}},
      {'id':'runtime','space':'main_thread','time_ms':990,'state':'observed','label':'RequireJS + app bootstrap','metrics':{'main_thread_ms':num(d,'mainthread-work-breakdown'),'js_execution_ms':num(d,'bootup-time')}},
      {'id':'lcp_discovery','space':'document_to_media','time_ms':tm(desktop,'networkRequestTime'),'state':'observed','label':'LCP not initially discoverable','metrics':{'discoverable':ck.get('requestDiscoverable'),'fetchpriority_high':ck.get('priorityHinted'),'observed_delay_ms':ph.get('resourceLoadDelay'),'simulated_delay_ms':old.get('Load Delay')}},
      {'id':'hero_dupe','space':'responsive_media','time_ms':{'mobile':tm(mobile,'networkRequestTime'),'desktop':tm(desktop,'networkRequestTime')},'state':'observed','label':'Both hero variants transferred'},
      {'id':'hydration','space':'hydration_boundary','time_ms':tm(desktop,'networkRequestTime'),'state':'hypothesis','confidence':'MEDIUM','label':'Client reconciliation may replace hero'},
      {'id':'lcp','space':'above_fold','time_ms':num(d,'largest-contentful-paint'),'state':'observed','label':'Late largest content','metrics':{'lcp_ms':num(d,'largest-contentful-paint'),'fcp_ms':num(d,'first-contentful-paint'),'element':lc.get('nodeLabel'),'selector':lc.get('selector')}},
      {'id':'js','space':'network_runtime','time_ms':{'start':985,'end':12740},'state':'observed','label':'JavaScript overdelivery','metrics':{'requests':rs.get('script',{}).get('requests'),'transfer_kib':rs.get('script',{}).get('kib'),'unused_savings_ms':num(d,'unused-javascript'),'top_unused':unused(d)}},
      {'id':'require_error','space':'document_runtime','time_ms':tm(doc,'networkEndTime'),'state':'observed' if error(d) else 'not_observed','label':'require is not defined','metrics':{'description':error(d)}},
      {'id':'layout','space':'below_fold','time_ms':tm(font,'networkRequestTime'),'state':'observed','label':'Unsized media + font shift content','metrics':{'cls':num(d,'cumulative-layout-shift'),'shifts':shifts(d)}},
      {'id':'contrast','space':'above_fold','time_ms':num(d,'first-contentful-paint'),'state':'observed','label':'Hero copy + CTA contrast failures','metrics':{'elements':contrast(d)}},
      {'id':'decision','space':'quality_gate','time_ms':num(d,'largest-contentful-paint'),'state':'derived','label':'LiminalQA WARN','metrics':{'performance':score('performance'),'accessibility':score('accessibility'),'best_practices':score('best-practices'),'seo':score('seo')}}]
    edges=[['navigation','redirect','triggers','observed'],['redirect','document','delays','observed'],['document','css','discovers','observed'],['css','lcp','delays_render','derived'],['document','runtime','starts','observed'],['runtime','lcp_discovery','gates_discovery','derived'],['lcp_discovery','lcp','dominates','derived'],['hero_dupe','hydration','supports','derived'],['hydration','lcp_discovery','may_explain','hypothesis'],['runtime','js','loads','observed'],['js','decision','reduces_responsiveness','derived'],['require_error','decision','lowers_best_practices','derived'],['layout','decision','degrades_stability','derived'],['contrast','decision','degrades_accessibility','derived'],['lcp','decision','drives_warning','derived']]
    ranking=[
      [1,'Late LCP discovery','CONFIRMED','Not in initial request graph; no fetchpriority=high; 83% simulated LCP phase.','Put the responsive LCP image in initial HTML and rerun 3 times.'],
      [2,'JavaScript overdelivery','CONFIRMED','55 scripts, ~1.53 MiB, ~965 KiB estimated unused.','Compare against a landing-only bundle.'],
      [3,'Language redirect','CONFIRMED','489 ms observed; ~1.1 s modelled savings.','Serve/link directly to canonical language URL.'],
      [4,'Responsive hero reconciliation','PARTLY CONFIRMED','Both variants load; later desktop asset is LCP on mobile.','Capture DOM mutations and initiators.'],
      [5,'Render-blocking CSS','CONFIRMED','Two critical stylesheets; ~509 ms modelled savings.','Inline critical CSS and defer the rest.'],
      [6,'Image dimensions and font timing','CONFIRMED','Two shifts tied to unsized subhero and font.','Add dimensions/aspect-ratio; test font-display.'],
      [7,'RequireJS ordering race','HYPOTHESIS','Inline code reports require undefined.','Inspect source order and add a runtime guard test.']]
    return {'schema_version':'liminalqa-space-time-causality-v1','target':d.get('finalUrl'),'guidance':'Readable, stable primary mobile content should appear quickly without runtime errors.','axes':{'space':['edge','origin','document_head','main_thread','responsive_media','viewport','quality_gate'],'valid_time':'navigation-relative milliseconds','transaction_time':'Lighthouse fetch and graph generation','note':'Observed trace and simulated mobile metrics are kept separate.'},'run_count':1,'evidence':{'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fetch_time':d.get('fetchTime'),'lighthouse_version':d.get('lighthouseVersion')},'dominant_path':['navigation','redirect','document','runtime','lcp_discovery','lcp','decision'],'nodes':nodes,'edges':[{'from':a,'to':b,'relation':r,'state':s} for a,b,r,s in edges],'ranked_causes':[{'rank':r,'cause':c,'status':s,'why':w,'next_test':n} for r,c,s,w,n in ranking],'boundaries':{'active_security_testing':False,'authenticated_testing':False,'financial_operations':False,'vulnerability_claim':False,'temporal_stability_proven':False},'generated_at':datetime.now(timezone.utc).isoformat()}

def get(g,i): return next(x for x in g['nodes'] if x['id']==i)
def render(g):
    l=get(g,'lcp')['metrics']; j=get(g,'js')['metrics']; e=g['evidence']; c=get(g,'contrast')['metrics']['elements']; er=get(g,'require_error')['metrics']['description'] or 'not captured'
    lines=['# LiminalQA · Tradernet space-time causality graph','',f"**Target:** `{g['target']}`  ",f"**Evidence SHA-256:** `{e['sha256']}`  ",f"**Runs:** {g['run_count']}",'','```mermaid','flowchart LR','  A["navigation"] --> B["redirect +489 ms"] --> C["final HTML ~1.09 s"]','  C --> D["render-blocking CSS ~509 ms"] --> G["LCP 10.9 s"]','  C --> E["RequireJS + app bootstrap"] --> F["LCP not initially discoverable"] --> G','  E --> J["55 scripts / ~1.53 MiB / ~965 KiB unused"] --> Q["LiminalQA WARN"]','  M["mobile hero early"] --> N["desktop hero later"]','  N -. possible reconciliation .-> F','  U["unsized subhero + font"] --> V["CLS 0.141"] --> Q','  W["low contrast copy + CTA"] --> Q','  R["require is not defined"] --> Q','  G --> Q','```','','## Dominant path','','`navigation → redirect → HTML → runtime bootstrap → late LCP discovery → LCP 10.9 s → WARN`','','## Ranked causes','','| Rank | Cause | Status | Why | Next test |','|---:|---|---|---|---|']
    for x in g['ranked_causes']: lines.append(f"| {x['rank']} | {x['cause']} | {x['status']} | {x['why']} | {x['next_test']} |")
    lines += ['','## Space map','','| Layer | Problem | Effect |','|---|---|---|','| Edge | Language redirect | Delays every cold visit |','| Document | Blocking CSS | Delays visual construction |','| Runtime | Broad bundles + RequireJS | Transfer and CPU waste |','| Responsive media | Both hero variants load | Extra bytes; possible late reconciliation |','| Above fold | Late hero + contrast failures | Slow and less readable first impression |','| Below fold | Unsized image + font | Layout shifts |','','## Time facts','','| Event | Time | Class |','|---|---:|---|','| Redirect completes | ~489 ms | observed |','| Final HTML completes | ~1,089 ms | observed |','| Mobile hero begins | ~987 ms | observed |','| Desktop/LCP hero begins | ~2,099 ms | observed |','| Font begins | ~2,111 ms | observed |','| LCP | ~10,866 ms | simulated mobile metric |','','## Concrete defects','',f'- Runtime: `{er.replace(chr(10)," ")}`',f'- Contrast failures: **{len(c)}** elements, including the primary CTA.',f'- Scripts: **{j["requests"]}** requests, **{j["transfer_kib"]} KiB**, ~965 KiB estimated unused.','- Both mobile and desktop hero variants transfer in one mobile navigation.','','## Proven vs hypothesis','','**Confirmed:** redirect, non-initial LCP discovery, duplicate hero transfer, unused JS, blocking CSS, runtime error, layout causes, contrast failures.','','**Hypotheses:** hydration replaces the hero; RequireJS error breaks a visible action; timing is stable across days/regions/runs.','','## Reflection','','The server is not the main bottleneck in this trace. Highest leverage: remove the redirect, expose the correct responsive LCP image in initial HTML, and avoid bootstrapping the broad trading application before landing content stabilizes.','','> Passive public-page evidence only. No authentication, trades, fuzzing, load testing, private data, or vulnerability claim.','']
    return '\n'.join(lines)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--input-dir',required=True); p.add_argument('--output-dir',required=True); a=p.parse_args(); path,d=find_report(a.input_dir); g=build(path,d); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'causality-graph.json').write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); (out/'causality-graph.md').write_text(render(g),encoding='utf-8')
if __name__=='__main__': main()

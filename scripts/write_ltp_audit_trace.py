#!/usr/bin/env python3
"""Create/verify a deterministic, read-only LTP JSONL audit trace."""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ZERO="0"*64; SHA=re.compile(r"^[0-9a-f]{64}$"); COMMIT=re.compile(r"^[0-9a-f]{40}$")
class TraceContractError(ValueError): pass

def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def fsha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def ts(v:str)->str:
 try:d=datetime.fromisoformat(v.replace("Z","+00:00"))
 except ValueError as e:raise TraceContractError(f"invalid RFC3339 timestamp: {v}") from e
 if d.tzinfo is None:raise TraceContractError(f"timestamp lacks timezone: {v}")
 return v
def load_registry(p:Path)->tuple[set[str],str]:
 try:x=json.loads(p.read_text())
 except Exception as e:raise TraceContractError(f"invalid critical-action registry: {p}") from e
 a=x.get("actions") if isinstance(x,dict) else None
 if not isinstance(a,dict) or not a:raise TraceContractError("registry actions missing")
 return set(a),fsha(p)
def make_frame(fid:str,timestamp:str,kind:str,payload:dict[str,Any],continuity:str|None)->dict[str,Any]:
 f={"v":"0.1","id":fid,"ts":timestamp,"type":kind,"payload":payload}
 if continuity:f["continuity_token"]=continuity
 return f
def build_entries(frames:Iterable[tuple[str,dict[str,Any]]],session:str)->list[dict[str,Any]]:
 out=[];prev=ZERO
 for i,(direction,frame) in enumerate(frames):
  digest=hashlib.sha256(prev.encode()+canon(frame)).hexdigest()
  out.append({"i":i,"ts":frame["ts"],"direction":direction,"session_id":session,"frame":frame,"prev_hash":prev,"hash":digest});prev=digest
 return out
def parse_jsonl(p:Path)->list[dict[str,Any]]:
 if not p.is_file():raise TraceContractError(f"trace not found: {p}")
 out=[]
 for n,line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(),1):
  if not line.strip():continue
  try:v=json.loads(line)
  except json.JSONDecodeError as e:raise TraceContractError(f"invalid JSONL line {n}: {e.msg}") from e
  if not isinstance(v,dict):raise TraceContractError(f"line {n} is not object")
  out.append(v)
 if not out:raise TraceContractError("trace is empty")
 return out
def verify_entries(entries:list[dict[str,Any]],critical:set[str])->dict[str,Any]:
 session=None;prev=ZERO;ids=set();cts=set();identity=None;routes=[]
 for i,e in enumerate(entries):
  if e.get("i")!=i:raise TraceContractError(f"entry index mismatch at position {i}")
  s=e.get("session_id")
  if not isinstance(s,str) or not s:raise TraceContractError(f"missing session_id at position {i}")
  if session is None:session=s
  elif s!=session:raise TraceContractError(f"session identity changed at position {i}")
  f=e.get("frame")
  if not isinstance(f,dict):raise TraceContractError(f"missing frame at position {i}")
  if f.get("v")!="0.1":raise TraceContractError(f"unsupported frame version at position {i}")
  fid=f.get("id")
  if not isinstance(fid,str) or not fid:raise TraceContractError(f"missing frame id at position {i}")
  if fid in ids:raise TraceContractError(f"duplicate frame id: {fid}")
  ids.add(fid);ts(str(f.get("ts","")))
  if not isinstance(f.get("type"),str):raise TraceContractError(f"missing frame type at position {i}")
  p=f.get("payload",{})
  if not isinstance(p,dict):raise TraceContractError(f"payload not object at position {i}")
  ct=f.get("continuity_token")
  if ct is not None:
   if not isinstance(ct,str) or not ct:raise TraceContractError(f"invalid continuity token at position {i}")
   cts.add(ct)
  if f["type"]=="orientation" and isinstance(p.get("identity"),str):
   if identity is None:identity=p["identity"]
   elif identity!=p["identity"]:raise TraceContractError("orientation identity changed")
  if e.get("prev_hash")!=prev:raise TraceContractError(f"broken previous-hash binding at position {i}")
  cur=e.get("hash")
  if not isinstance(cur,str) or not SHA.fullmatch(cur):raise TraceContractError(f"invalid event hash at position {i}")
  calc=hashlib.sha256(prev.encode()+canon(f)).hexdigest()
  if cur!=calc:raise TraceContractError(f"event hash mismatch at position {i}")
  prev=cur
  if f["type"]=="route_response":
   routes.append(p);decision=str(p.get("decision","")).upper();allow=p.get("admissible") is True
   if decision in {"BLOCK","DENY","HOLD","FREEZE"} and allow:raise TraceContractError(f"non-ALLOW decision marked admissible at position {i}")
   if p.get("context")=="WEB" and p.get("targetState") in critical and allow:raise TraceContractError(f"critical WEB-direct action at position {i}")
 if len(cts)>1:raise TraceContractError("continuity token changed")
 if not identity:raise TraceContractError("identity binding missing")
 return {"valid":True,"frames":len(entries),"session_id":session,"identity":identity,"hash_root":prev,"continuity_token":next(iter(cts),None),"route_decisions":len(routes)}
def inv(root:Path)->list[dict[str,Any]]:
 out=[]
 for p in sorted(root.rglob("*")):
  if p.is_file():
   r=p.relative_to(root).as_posix()
   if not r.startswith("ltp/") and r not in {"manifest.json","artifact-receipt.json"}:out.append({"path":r,"size_bytes":p.stat().st_size,"sha256":fsha(p)})
 return out
def writej(p:Path,v:Any):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
def build(a:argparse.Namespace)->int:
 for name in ("expected_sha","initial_sha","workflow_sha","ltp_sha"):
  if not COMMIT.fullmatch(getattr(a,name)):raise TraceContractError(f"{name} must be 40-char SHA")
 if a.expected_sha!=a.initial_sha:raise TraceContractError("initial SHA differs from expected SHA")
 start=ts(a.started_at);root=Path(a.output_dir).resolve();critical,rsha=load_registry(Path(a.critical_actions_registry).resolve());files=inv(root)
 invroot=hashlib.sha256(canon(files)).hexdigest();session=f"tradernet-{a.run_id}-{a.run_attempt}";ct="ct-"+hashlib.sha256(f"{a.repository}:{a.expected_sha}:{a.run_id}:{a.run_attempt}".encode()).hexdigest()[:24];identity=f"{a.repository}@{a.expected_sha}"
 constraints={"public_page_only":True,"read_only":True,"no_authentication":True,"no_form_submission":True,"no_financial_operation":True,"no_external_message":True,"no_deploy":True,"no_protected_effect":True}
 frames=[
 ("out",make_frame("step-001",start,"hello",{"agent":"liminalqa-tradernet-auditor","repository":a.repository,"expected_sha":a.expected_sha,"workflow_sha":a.workflow_sha,"run_id":str(a.run_id),"run_attempt":str(a.run_attempt),"artifact_name":a.artifact_name,"ltp_inspector_sha":a.ltp_sha,"critical_actions_registry_sha256":rsha},None)),
 ("out",make_frame("step-002",start,"orientation",{"identity":identity,"status":"healthy","drift":0.0,"constraints":constraints},ct)),
 ("out",make_frame("step-003",start,"focus_snapshot",{"identity":identity,"drift":0.0,"focus_momentum":1.0,"rationale":"bounded evidence capture"},ct)),
 ("in",make_frame("step-004",start,"route_request",{"goal":"record bounded public audit evidence","source_context":"CI","target":a.target,"repository":a.repository,"expected_sha":a.expected_sha,"run_id":str(a.run_id),"run_attempt":str(a.run_attempt),"constraints":constraints},ct)),
 ("out",make_frame("step-005",start,"route_response",{"context":"CI","targetState":"capture_public_evidence","admissible":True,"decision":"EXECUTE","capabilities":[],"branches":[{"id":"bounded-public-capture","confidence":1.0,"status":"admissible","reason":"read-only public scope and exact-head identity verified"}]},ct)),
 ("out",make_frame("step-006",start,"observation",{"capture_status":a.capture_status,"evidence_file_count":len(files),"evidence_inventory_sha256":invroot,"evidence_files":files},ct)),
 ("in",make_frame("step-007",start,"route_request",{"goal":"preserve immutable audit evidence","source_context":"CI","constraints":constraints},ct)),
 ("out",make_frame("step-008",start,"route_response",{"context":"CI","targetState":"write_audit_artifact","admissible":True,"decision":"EXECUTE","capabilities":[],"branches":[{"id":"immutable-artifact","confidence":1.0,"status":"admissible","reason":"output remains inside declared CI artifact boundary"}]},ct)),
 ("out",make_frame("step-009",start,"orientation",{"identity":identity,"status":"healthy","drift":0.0,"focus_momentum":1.0,"constraints":constraints},ct))]
 entries=build_entries(frames,session);d=root/"ltp";d.mkdir(parents=True,exist_ok=True);trace=d/"trace.jsonl";trace.write_text("\n".join(json.dumps(e,separators=(",",":"),ensure_ascii=False) for e in entries)+"\n")
 result=verify_entries(entries,critical);result.update({"trace_sha256":fsha(trace),"ltp_inspector_sha":a.ltp_sha,"critical_actions_registry_sha256":rsha,"evidence_inventory_sha256":invroot});writej(d/"local-verification.json",result);return 0
def verify(a:argparse.Namespace)->int:
 critical,rsha=load_registry(Path(a.critical_actions_registry).resolve());p=Path(a.trace).resolve();r=verify_entries(parse_jsonl(p),critical);r.update({"trace_sha256":fsha(p),"critical_actions_registry_sha256":rsha});writej(Path(a.output).resolve(),r) if a.output else print(json.dumps(r,sort_keys=True));return 0
def parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);b=s.add_parser("build")
 for n in ("output_dir","audit_name","target","repository","expected_sha","initial_sha","workflow_sha","run_id","run_attempt","started_at","capture_status","artifact_name","ltp_sha","critical_actions_registry"):b.add_argument("--"+n.replace("_","-"),required=True)
 b.set_defaults(fn=build);v=s.add_parser("verify");v.add_argument("--trace",required=True);v.add_argument("--critical-actions-registry",required=True);v.add_argument("--output");v.set_defaults(fn=verify);return p
def main()->int:
 try:
  a=parser().parse_args();return int(a.fn(a))
 except TraceContractError as e:print(f"TRACE CONTRACT ERROR: {e}");return 2
if __name__=="__main__":raise SystemExit(main())

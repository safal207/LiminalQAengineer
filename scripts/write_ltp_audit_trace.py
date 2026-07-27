#!/usr/bin/env python3
"""Create/verify a deterministic, read-only LTP JSONL audit trace."""
from __future__ import annotations
import argparse, hashlib, json, math, re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ZERO="0"*64; SHA=re.compile(r"^[0-9a-f]{64}$"); COMMIT=re.compile(r"^[0-9a-f]{40}$")
class TraceContractError(ValueError): pass

def _js_numbers(v:Any)->Any:
 if isinstance(v,float):
  if not math.isfinite(v):raise TraceContractError("non-finite number is not canonical JSON")
  return int(v) if v.is_integer() else v
 if isinstance(v,list):return [_js_numbers(x) for x in v]
 if isinstance(v,dict):return {k:_js_numbers(x) for k,x in v.items()}
 return v
def canon(v:Any)->bytes:return json.dumps(_js_numbers(v),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
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
 if not identity:raise TraceContractError,"identity binding missing")
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
 start=ts(a.started_at);root=Path(a.output_dir*Þ²‰oyÊâ¶'–»!jZv· ŠËkÈö­…§+ŠØœjVœ¶*'²· ŠËkÊ·¬¢[Þ~)^²)ï®Š-Š{ë¢‹
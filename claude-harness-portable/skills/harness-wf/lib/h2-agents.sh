#!/usr/bin/env bash
# harness-wf — 역할 agentId 영속(resume 관통) + active-agents(watchdog 입력) 관리
# agents.json        : { "<role>": "<agentId>" }            ← resume 관통 (SendMessage to=agentId)
# active-agents.json  : { "<agentId>": {role,dispatch_ts,eta_s,done} } ← h2-watchdog 입력
# usage:
#   h2-agents.sh register  <h2dir> <agentId> <role> <eta_s>
#   h2-agents.sh done       <h2dir> <agentId>
#   h2-agents.sh resume-id  <h2dir> <role>      # stdout = agentId (없으면 빈문자)
#   h2-agents.sh list       <h2dir>
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"

cmd=${1:?cmd}; dir=${2:?h2dir}
AG="$dir/agents.json"; AC="$dir/active-agents.json"

node -e '
  const fs=require("fs");
  const [,cmd,AG,AC,a3,a4,a5]=process.argv;
  const rd=(p)=>{try{return JSON.parse(fs.readFileSync(p,"utf8"))}catch(_){return {}}};
  const wr=(p,o)=>{const t=p+".tmp."+process.pid;fs.writeFileSync(t,JSON.stringify(o));fs.renameSync(t,p)};
  if(cmd==="register"){
    const [agentId,role,eta]=[a3,a4,a5];
    const ag=rd(AG); ag[role]=agentId; wr(AG,ag);
    const ac=rd(AC); ac[agentId]={role,dispatch_ts:Date.now(),eta_s:Number(eta)||0,done:false}; wr(AC,ac);
    process.stdout.write("registered "+role+"="+agentId);
  } else if(cmd==="done"){
    const agentId=a3; const ac=rd(AC);
    if(ac[agentId]) ac[agentId].done=true;
    wr(AC,ac); process.stdout.write("done "+agentId);
  } else if(cmd==="resume-id"){
    const role=a3; const ag=rd(AG); process.stdout.write(ag[role]||"");
  } else if(cmd==="list"){
    process.stdout.write(JSON.stringify(rd(AC)));
  } else { process.stderr.write("unknown cmd: "+cmd); process.exit(2); }
' "$cmd" "$AG" "$AC" "${3:-}" "${4:-}" "${5:-}"

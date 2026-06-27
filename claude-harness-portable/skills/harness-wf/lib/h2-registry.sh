#!/usr/bin/env bash
# harness-wf — button dead-man's switch 등록부 SSOT (~/.claude/.harness-active.json).
# button startHarness2DeadmanWatchdog() 가 60s 폴링 → 각 h2dir/.self-wake-ts mtime staleness 감지 →
# 워치독 사망 시 등록된 session 을 1회 깨움 (워치독 독립 외부 관찰자 = ZERO-MAIN dead-man's switch).
# 경로 통일(MSYS2↔Windows 함정): 레지스트리 = node os.homedir()(=C:\Users\jsh86, env.HOME msys 무시)
#   / h2dir = cygpath -w(Windows 절대경로) → button(Windows node) 의 fs.statSync 와 동일 형식.
# register: scaffold 시 upsert. unregister: 종료 시 제거.
# usage:
#   h2-registry.sh register   <h2dir> [session]   # session 생략 시 $PSMUX_SESSION → display-message fallback
#   h2-registry.sh unregister <h2dir>
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"   # node PATH 확보 (MSYS2 node 미탑재 함정)
mode=${1:?mode: register|unregister}; h2dir_in=${2:?h2dir}
h2dir=$(cygpath -w "$h2dir_in" 2>/dev/null || echo "$h2dir_in")    # Windows 절대경로 (button Windows node 매칭)
sess=${3:-${PSMUX_SESSION:-}}
if [ -z "$sess" ]; then sess=$(psmux display-message -p '#S' 2>/dev/null || true); fi
node -e '
  const fs=require("fs"),path=require("path"),os=require("os");
  const [,mode,h2dir,sess]=process.argv;
  const reg=path.join(os.homedir(),".claude",".harness-active.json");
  let a=[]; try{a=JSON.parse(fs.readFileSync(reg,"utf8"))}catch(_){}
  if(!Array.isArray(a))a=[];
  a=a.filter(e=>e&&e.h2dir!==h2dir);                       // upsert: 동일 h2dir 제거 후 재삽입
  if(mode==="register"){
    if(!sess){process.stderr.write("register: session 미해결(PSMUX_SESSION/display-message 둘 다 실패)\n");process.exit(3)}
    a.push({h2dir,session:sess,registeredAt:Date.now()});
  }
  fs.writeFileSync(reg,JSON.stringify(a,null,2));
  process.stdout.write(mode+" ok: "+h2dir+(mode==="register"?" -> "+sess:"")+" @ "+reg+"\n");
' "$mode" "$h2dir" "$sess"

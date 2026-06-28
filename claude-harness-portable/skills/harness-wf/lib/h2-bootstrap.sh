#!/usr/bin/env bash
# harness-wf — bootstrap (harness-wf spawn-session.sh 등가, phase-loop-with-registry s1~s4).
# transport = Claude Code in-process TEAMMATE (run_in_background 프리미티브 폐기).
# 본 스크립트 책무 = scaffold(.harness 디렉토리/로그/state) + harness.md(taskspec 치환, preserve guard).
# dispatch prompt + manifest 생성은 SSOT 헬퍼 teammate-spawn.sh build 에 위임(설계 정수 단일출처).
# 그 후 메인(Supervisor)이 manifest.json 읽어 TeamCreate → Agent(team_name,name) 로 teammate 스폰.
# usage: h2-bootstrap.sh <h2dir> <taskspec_file>
#   taskspec 형식:
#     GOAL: <pipeline goal>
#     SACRED: <불가침>
#     OPEN: <도전허용>
#     PHASE 1: <final objective>
#       SUBOBJ 1.1: <desc> | verify: <객관 명령/기준>
#       SUBOBJ 1.2: ...
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"
SK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # skill root

H=${1:?h2dir}; SPEC=${2:?taskspec_file}
[ -f "$SPEC" ] || { echo "taskspec not found: $SPEC" >&2; exit 2; }
mkdir -p "$H/verdicts" "$H/artifacts" "$H/dispatch"
[ -s "$H/execution-log.jsonl" ] || printf '' > "$H/execution-log.jsonl"   # issue#1 fix: 기존 진행기록 보존(wipe 금지)
printf '{}' > "$H/active-agents.json"
[ -s "$H/agents.json" ] || printf '{}' > "$H/agents.json"                  # issue#1 fix: live agentId 보존
[ -f "$H/improvement-registry.md" ] || printf '# harness improvement-registry\n\n| 내용 | 출처세션 | 상태 | 적용위치 | 비고 |\n|---|---|---|---|---|\n' > "$H/improvement-registry.md"
printf 'harness active\n' > "$H/.active"

TS=$(date +%s%3N)
# execution-log 헤더 이벤트 (supervisor-realtime-event-logging 등가)
printf '%s\n' "{\"ev\":\"wf_header\",\"wf\":\"harness\",\"phase\":0,\"started\":$TS}" >> "$H/execution-log.jsonl"
bash "$SK/lib/h2-state.sh" transition "$H" S0 IDLE 0

# taskspec → harness.md 필드 (node 파싱: GOAL/SACRED/OPEN/PHASES_TABLE/ROLE_ASSIGN)
PARSED=$(node -e '
  const fs=require("fs");
  const t=fs.readFileSync(process.argv[1],"utf8").split(/\r?\n/);
  let goal="",sacred="",open="";const phases=[];let cur=null;
  for(const ln of t){
    let m;
    if(m=ln.match(/^\s*GOAL:\s*(.*)/i)) goal=m[1].trim();
    else if(m=ln.match(/^\s*SACRED:\s*(.*)/i)) sacred=m[1].trim();
    else if(m=ln.match(/^\s*OPEN:\s*(.*)/i)) open=m[1].trim();
    else if(m=ln.match(/^\s*PHASE\s+(\S+):\s*(.*)/i)){cur={n:m[1],fo:m[2].trim(),subs:[]};phases.push(cur);}
    else if(m=ln.match(/^\s*SUBOBJ\s+(\S+):\s*(.*)/i)){const parts=m[2].split(/\|\s*verify:\s*/i);cur&&cur.subs.push({id:m[1],desc:parts[0].trim(),verify:(parts[1]||"관찰가능 기준").trim()});}
  }
  let tbl="| Phase | Final Objective | Sub-obj | 설명 | 검증(객관) | 담당 |\n|---|---|---|---|---|---|\n";
  let assign="- **Worker(active)**: Sub-obj 순차 구현 (turn 카운터 self-relay → Standby 인계, handoff-key 관통)\n- **Standby1~5**: dormant pool, SendMessage(name) 로 active 승계\n- **Verifier**: 각 Sub-obj 독립검증 (zero-main step-gate 랑데부, verdict idempotent)\n- **watchdog(sonnet)**: liveness probe only (ctx 측정 불가 = CTX-INVISIBLE 실증)\n- **Healer**: Verifier FAIL 시 (on-demand, 9-step)\n- **SR**: Pre-Review(C) / T1-T4 / Post-Review(A) (on-trigger)\n";
  for(const p of phases) for(const s of p.subs)
    tbl+=`| ${p.n} | ${p.fo} | ${s.id} | ${s.desc} | ${s.verify} | Worker→Verifier |\n`;
  process.stdout.write(JSON.stringify({goal,sacred,open,tbl,assign,nsub:phases.reduce((a,p)=>a+p.subs.length,0)}));
' "$SPEC")

# harness.md = 템플릿 치환 — 기존 있으면 보존(codify 모델 wipe 금지, issue#1-류)
if [ -s "$H/harness.md" ]; then echo "[h2-bootstrap] harness.md 보존(기존 codify 유지)"; else
node -e '
  const fs=require("fs");
  const [,tpl,out,h2,ts,pj]=process.argv;
  const P=JSON.parse(pj);
  let s=fs.readFileSync(tpl,"utf8");
  const map={"{{TS}}":ts,"{{H2DIR}}":h2,"{{GOAL}}":P.goal||"(미지정)","{{SACRED}}":P.sacred||"(없음)","{{OPEN}}":P.open||"(전 구현영역)","{{PHASES_TABLE}}":P.tbl,"{{ROLE_ASSIGN}}":P.assign};
  for(const[k,v] of Object.entries(map)) s=s.split(k).join(v);
  fs.writeFileSync(out,s);
' "$SK/templates/harness-md.tmpl" "$H/harness.md" "$H" "$TS" "$PARSED"
fi

# ── dispatch prompt + manifest = SSOT 헬퍼 teammate-spawn.sh 에 위임 ──
# 구모델(run_in_background dispatch / agentId watchdog ctx측정) 폐기.
# 설계 정수(turn 카운터 self-relay·handoff-key·zero-main·CTX-INVISIBLE·step-gate idempotent) = teammate-spawn.sh 단일출처.
bash "$SK/lib/teammate-spawn.sh" build  "$H" "$SPEC"
bash "$SK/lib/teammate-spawn.sh" verify "$H"

# 구모델 잔존 산출물 제거 (혼동 방지: *.task.txt / watchdog.cmd = run_in_background 시절 유물)
rm -f "$H"/dispatch/*.task.txt "$H"/dispatch/watchdog.cmd 2>/dev/null || true

NSUB=$(printf '%s' "$PARSED" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(""+(JSON.parse(s).nsub||0)))')
echo "=== h2-bootstrap 완료 (transport=teammate-in-process) ==="
echo "harness.md: $H/harness.md (Sub-obj ${NSUB}개)"
echo "dispatch prompts: $(ls "$H"/dispatch/*.prompt 2>/dev/null | wc -l)종"
echo "manifest: $H/manifest.json (teammate-spawn.sh verify PASS)"
echo ""
echo ">>> MAIN(Supervisor) 다음 행동:"
echo "  (1) manifest.json members[] 읽기"
echo "  (2) TeamCreate(team_name) — 1회"
echo "  (3) 각 member: Agent(team_name, name=<name>, model=<model>, prompt=\"\$(cat <member.prompt>)\")  ⛔ 전문 VERBATIM 주입. 'Read 해라' 포인터 금지(disclaimer 선행의존 갭 — 역할주입은 dispatch prompt 자체완결)."
echo "      = active Worker + Standby1~5 + Verifier + sonnet watchdog 한 배치. Healer=on_demand(Verifier FAIL시) / SR=on_trigger."
echo "  (4) ⛔ run_in_background 금지(폐기 프리미티브). ⛔ 글로벌 작성 task 생성 금지(teammate auto-claim 오라우팅 — 메인이 글로벌 선완료 후 스폰)."
echo "  (5) ZERO-MAIN: 스폰 후 Supervisor 본문 0 tool-call. 기상 = R7 3조건(phase_complete / standby pool 고갈 / 복구불능)."

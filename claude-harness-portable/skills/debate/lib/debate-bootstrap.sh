#!/usr/bin/env bash
# debate — bootstrap (원본 debate spawn-session.sh+psmux 등가, in-process teammate).
# bash 는 Agent/TeamCreate tool 불가(스폰=메인 전용) → 헬퍼는 debate.md + scaffold +
# dispatch prompt(Challenger+watchdog active / Judge on-demand) + manifest 까지 생성.
# 그 후 메인이 manifest 읽어 TeamCreate "debate" + Agent(Challenger,watchdog). Judge=Step4 on-demand.
# transport 헬퍼(h2-state/log/agents/env)+haiku-watchdog.txt = harness-wf 재사용(DRY).
# disclaimer = debate 전용. challenger-constitution.md/judge-protocol.md = verbatim 재사용.
# usage: debate-bootstrap.sh <debatedir> <context_spec_file>
#   context_spec 형식:
#     TOPIC: <토론 주제 1줄>
#     CONTEXT: <debate-context.md 경로 (도메인 자료)>
#     PROPOSAL: <debate-brief.md 경로 (제안 — Challenger 는 domain_ack 후에만 봄)>
#     SACRED: <불가침 (선택)>
set -euo pipefail
SK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # debate skill root
# 재사용 transport — 형제 harness-wf 우선(설치 위치 무관), 없으면 ~/.claude 절대경로 fallback.
H2LIB="$(cd "$SK/../harness-wf/lib" 2>/dev/null && pwd)"; [ -d "$H2LIB" ] || H2LIB="$HOME/.claude/skills/harness-wf/lib"
H2TPL="$(cd "$SK/../harness-wf/templates" 2>/dev/null && pwd)"; [ -d "$H2TPL" ] || H2TPL="$HOME/.claude/skills/harness-wf/templates"
source "$H2LIB/h2-env.sh"

H=${1:?debatedir}; SPEC=${2:?context_spec_file}
[ -f "$SPEC" ] || { echo "context_spec not found: $SPEC" >&2; exit 2; }
mkdir -p "$H/artifacts" "$H/dispatch"
printf '' > "$H/execution-log.jsonl"
printf '{}' > "$H/active-agents.json"
printf '{}' > "$H/agents.json"
printf 'debate active\n' > "$H/.active"

TS=$(date +%s%3N)
JITTER=$(( RANDOM % 11 ))   # Challenger turn jitter 0~10 (CTX-INVISIBLE self-relay 분산). harness 벤치마크.
printf '%s\n' "{\"ev\":\"wf_header\",\"wf\":\"debate\",\"phase\":0,\"started\":$TS}" >> "$H/execution-log.jsonl"
bash "$H2LIB/h2-state.sh" transition "$H" S0 IDLE 0

PARSED=$(node -e '
  const fs=require("fs");
  const t=fs.readFileSync(process.argv[1],"utf8").split(/\r?\n/);
  let topic="",ctx="",prop="",sacred="";
  for(const ln of t){let m;
    if(m=ln.match(/^\s*TOPIC:\s*(.*)/i)) topic=m[1].trim();
    else if(m=ln.match(/^\s*CONTEXT:\s*(.*)/i)) ctx=m[1].trim();
    else if(m=ln.match(/^\s*PROPOSAL:\s*(.*)/i)) prop=m[1].trim();
    else if(m=ln.match(/^\s*SACRED:\s*(.*)/i)) sacred=m[1].trim();
  }
  process.stdout.write(JSON.stringify({topic,ctx,prop,sacred}));
' "$SPEC")

node -e '
  const fs=require("fs");const [,out,h,ts,pj]=process.argv;const P=JSON.parse(pj);
  fs.writeFileSync(out,`# debate 실행 계획 (debate.md)

> bootstrap ts=${ts} · dir=${h} · in-process teammate(Supervisor+Challenger+Sonnet watchdog / Judge=Step4 on-demand).

## Topic
${P.topic||"(미지정)"}

## Context (도메인 자료 — Challenger 가 domain_ack 전 독립 Read)
${P.ctx||"(Supervisor 가 debate-context.md 작성·경로 지정)"}

## Proposal (제안 — Challenger 는 domain_ack 후에만 열람)
${P.prop||"(Supervisor 가 debate-brief.md 작성)"}

## Sacred
${P.sacred||"(없음)"}

## 흐름
⓪ROI → §2 Challenger+watchdog dispatch + 도메인주입(ev:domain_ack) → §3 라운드(Steelman→Score→Attack→Rebuttal, ev 랑데부) → §4 수렴(max4R) → §5 Judge on-demand(Clean Room) → §6 verdict 회수.

## 역할
- **Supervisor(메인 Opus)**: ROI·brief·Score·Rebuttal·수렴판정·Judge 스폰·회수. 매 라운드 능동 개입.
- **Challenger(opus, 상주)**: 도메인 독립이해 → Steelman → Attack. gating ev 마다 Supervisor wake-ping 필수.
- **watchdog(sonnet)**: silent-death backstop(1차 wake 아님).
- **Judge(opus, Step4 on-demand fresh=Clean Room)**: judge-protocol.md 전문 → verdict → wake-ping.
`);
' "$H/debate.md" "$H" "$TS" "$PARSED"

# Challenger.prompt = disclaimer-strict-debate + role-challenger-debate + 배정 (JITTER 치환)
CT="$H/dispatch/Challenger.task.txt"
{ cat "$SK/templates/role-challenger-debate.txt"
  echo ""; echo "=== 배정 (debate.md 참조) ==="
  echo "debate.md 의 흐름대로. constitution: $SK/challenger-constitution.md (Read). <H2DIR>=$H 치환."
} > "$CT"
node -e '
  const fs=require("fs");const [,tpl,task,out,role,h,schema,rdv,jit]=process.argv;
  let s=fs.readFileSync(tpl,"utf8");
  // {{TASK}}(role 본문) 먼저 삽입 → 그 안의 {{H2DIR}}/{{JITTER}} 를 그 다음 치환 (Object 삽입순서 보존)
  const map={"{{ROLE}}":role,"{{TASK}}":fs.readFileSync(task,"utf8"),"{{SCHEMA}}":schema,"{{RENDEZVOUS}}":rdv,"{{H2DIR}}":h,"{{JITTER}}":jit};
  for(const[k,v] of Object.entries(map)) s=s.split(k).join(v);
  fs.writeFileSync(out,s);
' "$SK/templates/disclaimer-strict-debate.txt" "$CT" "$H/dispatch/Challenger.prompt" Challenger "$H" \
  '{"role":"Challenger","summary":"...","exit_code":0,"files_touched":[],"blockers":[]}' \
  '(Supervisor 가 ev:domain_ack/steelman_done/attack_done/relay 의 wake-ping 으로 수신 — Score/Rebuttal/다음라운드 직접 진행. 단계 지시 = SendMessage(to="Challenger").)' \
  "$JITTER"

# Judge.prompt = disclaimer + role-judge-debate (on-demand: Step4 에 메인이 spawn)
JT="$H/dispatch/Judge.task.txt"
{ cat "$SK/templates/role-judge-debate.txt"
  echo ""; echo "=== 배정 ==="; echo "judge-protocol.md: $SK/judge-protocol.md (Read·전문 준수). judge-brief: Supervisor 가 debate-judge-brief.md 작성. <H2DIR>=$H 치환."
} > "$JT"
node -e '
  const fs=require("fs");const [,tpl,task,out,role,h,schema,rdv,jit]=process.argv;
  let s=fs.readFileSync(tpl,"utf8");
  // {{TASK}}(role 본문) 먼저 삽입 → 그 안의 {{H2DIR}}/{{JITTER}} 를 그 다음 치환 (Object 삽입순서 보존)
  const map={"{{ROLE}}":role,"{{TASK}}":fs.readFileSync(task,"utf8"),"{{SCHEMA}}":schema,"{{RENDEZVOUS}}":rdv,"{{H2DIR}}":h,"{{JITTER}}":jit};
  for(const[k,v] of Object.entries(map)) s=s.split(k).join(v);
  fs.writeFileSync(out,s);
' "$SK/templates/disclaimer-strict-debate.txt" "$JT" "$H/dispatch/Judge.prompt" Judge "$H" \
  '{"role":"Judge","verdict":"...","exit_code":0}' \
  '(Clean Room — Challenger 와 무통신. verdict_done 후 Supervisor wake-ping 필수.)' "0"

# watchdog.prompt = haiku-watchdog.txt(harness 재사용) 치환
node -e '
  const fs=require("fs");const [,tpl,out,h,st,pl,cap]=process.argv;
  let s=fs.readFileSync(tpl,"utf8");
  const map={"{{H2DIR}}":h,"{{STALE_S}}":st,"{{POLL_S}}":pl,"{{CAP_S}}":cap};
  for(const[k,v] of Object.entries(map)) s=s.split(k).join(v);
  fs.writeFileSync(out,s);
' "$H2TPL/haiku-watchdog.txt" "$H/dispatch/watchdog.prompt" "$H" 600 30 3000

# manifest (메인이 읽어 TeamCreate+Agent — harness transport 정합)
node -e '
  const fs=require("fs");const [,h,jit]=process.argv;const J=Number(jit)||0;
  const m={
    debatedir:h, wf:"debate",
    transport:"teammate-in-process",
    spawn_rule:"Supervisor: STEP-1 TeamCreate(team_name=debate) 1회 → STEP-2 Agent(team_name=debate,name=Challenger|watchdog, model, subagent_type=general-purpose, prompt=cat(member.prompt) VERBATIM). Judge=Step4 on-demand(기존 team join, TeamCreate 재호출 금지). run_in_background FORBIDDEN. name/team_name 필수. raw Agent 금지.",
    relay:{
      primary:"Challenger turn-counter (CTX-INVISIBLE): turn>=50+jitter"+J+" && 라운드경계 -> ev:relay+wake-ping+idle",
      respawn:"Supervisor wake-ping 수신 → 동일 Agent(team_name=debate,name=Challenger) 재dispatch (debate-keypoints.md+직전 라운드 .md 흡수)",
      jitter:J,
      backstop:["gating ev 마다 Challenger/Judge wake-ping SendMessage(주 waker)","watchdog silent-death staleness","산출 .md 파일 = 복구 앵커"]
    },
    members:[
      {role:"Challenger",name:"Challenger",model:"opus", kind:"active",   prompt:h+"/dispatch/Challenger.prompt", eta_s:1800},
      {role:"watchdog",  name:"watchdog",  model:"sonnet",kind:"liveness", prompt:h+"/dispatch/watchdog.prompt",   eta_s:3000, no_active_register:true},
      {role:"Judge",     name:"Judge",     model:"opus", kind:"on-demand",prompt:h+"/dispatch/Judge.prompt",      eta_s:1800, on_demand:true}
    ],
    note:"debate = Supervisor 능동진행 + Challenger 상주 + Judge Step4 on-demand(Clean Room) + watchdog backstop. wake = teammate wake-ping SendMessage(주, idle 보장 아님)."
  };
  fs.writeFileSync(h+"/manifest.json", JSON.stringify(m,null,2));
' "$H" "$JITTER"

echo "=== debate-bootstrap 완료 ==="
echo "debate.md: $H/debate.md"
echo "dispatch: $(ls "$H/dispatch"/*.prompt 2>/dev/null | wc -l)종 (Challenger+watchdog active / Judge on-demand)"
echo "manifest: $H/manifest.json (transport=teammate-in-process, jitter=$JITTER)"
echo ""
echo ">>> MAIN 다음 행동 (transport=teammate-in-process):"
echo "  STEP-1  TeamCreate(team_name=\"debate\", agent_type=\"supervisor\", description=\"debate 토론 team\")  ← 1회"
echo "  STEP-2  (한 메시지 병렬, prompt=파일 전문 VERBATIM):"
echo "     (a) Agent(team_name=\"debate\", name=\"Challenger\", model=\"opus\",  subagent_type=general-purpose, prompt=cat $H/dispatch/Challenger.prompt)"
echo "     (b) Agent(team_name=\"debate\", name=\"watchdog\",   model=\"sonnet\", subagent_type=general-purpose, prompt=cat $H/dispatch/watchdog.prompt)"
echo "  ⛔ run_in_background 절대 금지, name/team_name 필수."
echo "  STEP-3  Challenger agentId → h2-agents.sh register $H <agentId> Challenger 1800 (watchdog 미등록)."
echo "  STEP-4  수렴/4R 도달 시 Judge on-demand: Agent(team_name=\"debate\", name=\"Judge\", model=\"opus\", prompt=cat $H/dispatch/Judge.prompt) — 기존 team join."
echo "  wake: Challenger/Judge gating ev 마다 SendMessage(to=\"Supervisor\") wake-ping(주) → 메인 h2-log.sh last 분류. idle=best-effort, watchdog=silent-death backstop."

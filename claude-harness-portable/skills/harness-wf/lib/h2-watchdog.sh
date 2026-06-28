#!/usr/bin/env bash
# harness-wf — patrol ① staleness 엔진 (LLM 0). 정식 경로 = Haiku agent 가 `check` one-shot 반복 호출.
# (bash loop 단독은 idle Supervisor 를 못 깨움 = 설계 결함 → Haiku agent watchdog 으로 wake.
#  loop 모드는 보조/디버그용만 유지.)
# usage:
#   h2-watchdog.sh check <h2dir> <stale_s>            # one-shot: stalled agent JSON 출력 (Haiku 가 호출)
#   h2-watchdog.sh loop  <h2dir> [stale_s=180] [poll_s=30]   # (보조) bg 루프, STUCK append
#   h2-watchdog.sh scan  <h2dir> <stale_s> <since_ts>  # one-shot 이벤트 신호: {"status":"alive|phase_complete|escalate|stuck"}. since_ts 이후 새 ev 만 트리거(재스폰 시 과거 재트리거 방지).
#   h2-watchdog.sh watch <h2dir> [poll=60] [cap=540] [stale=360] [since_ms]  # 블로킹 루프: .self-wake-ts heartbeat + .watchdog-stop sentinel + scan. 이벤트/stop → WATCHDOG_RESULT 후 종료(=task-notification, Supervisor 기상). cap → status:cap+next_since 출력 후 종료(= watchdog agent 가 self-respawn: next_since 로 재호출, Supervisor 미경유 = ZERO-MAIN). since_ms(6번째)=self-respawn 시 직전 종료 ts 전진(과거 이벤트 재트리거 방지). 단일 watchdog SSOT.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"

mode=${1:?mode: check|loop}; dir=${2:?h2dir}
LOG="$dir/execution-log.jsonl"; AC="$dir/active-agents.json"

# stalled agent 목록 산출 (now ms, stale_s) → JSON {"stalled":[{agent,role,silent_ms}],"checked":N}
_scan() {
  local now="$1" st="$2"
  node -e '
    const fs=require("fs");
    const [,ac,log,nowS,staleS]=process.argv;
    let A={}; try{A=JSON.parse(fs.readFileSync(ac,"utf8"))}catch(_){}
    let lines=[]; try{lines=fs.readFileSync(log,"utf8").split("\n").filter(x=>x.trim())}catch(_){}
    const last={};
    for(const l of lines){try{const o=JSON.parse(l);if(o.agent)last[o.agent]=Math.max(last[o.agent]||0,o.ts||0)}catch(_){}}
    const now=Number(nowS), st=Number(staleS)*1000, stalled=[]; let n=0;
    for(const [id,m] of Object.entries(A)){
      if(m&&m.done) continue; n++;
      const lt=last[id]||(m&&m.dispatch_ts)||0;
      if(lt&&now-lt>st) stalled.push({agent:id,role:(m&&m.role)||null,silent_ms:now-lt});
    }
    process.stdout.write(JSON.stringify({stalled,checked:n}));
  ' "$AC" "$LOG" "$now" "$st"
}

# 이벤트 신호 (since 이후 새 ev): phase_complete / escalate|blocked / silent-death(stuck) / alive
# within-phase 정상 commit·verdict 흐름엔 alive (Worker↔Verifier 자율 pull = Supervisor 미개입).
_scan_status() {
  local st="$1" since="$2"
  local proj; proj=$(cd "$dir/.." && pwd)
  local EV
  EV=$(node -e '
    const fs=require("fs");
    const [,log,sinceS]=process.argv; const since=Number(sinceS)||0;
    let lines=[];try{lines=fs.readFileSync(log,"utf8").split("\n").filter(x=>x.trim())}catch(_){}
    let pc=null,esc=null;
    for(const l of lines){try{const o=JSON.parse(l);if((o.ts||0)<=since)continue;
      if(o.ev==="phase_complete")pc=o; else if(o.ev==="escalate"||o.ev==="blocked")esc=o;
    }catch(_){}}
    if(pc)process.stdout.write(JSON.stringify({status:"phase_complete",phase:pc.phase??null}));
    else if(esc)process.stdout.write(JSON.stringify({status:"escalate",reason:esc.reason??null,sub:esc.sub??null}));
    else process.stdout.write("");
  ' "$LOG" "$since")
  if [ -n "$EV" ]; then printf '%s\n' "$EV"; return; fi
  # silent-death 비활성(2026-05-30 fix): active Worker 의 long-running 파일편집(첫 commit 전 execution-log 무신호)+blocked 재개 공백을 stuck 으로 오판해 watchdog 조기종료(stale 360→1200 도 부족 — blocked 27분 공백 실측). 진짜 좀비(전원 정지)는 teammate idle_notification(이 환경 자동도착)+cap 주기 재스폰 점검이 커버. watch = phase_complete/blocked/escalate 즉시감지(위) + cap 으로만 종료.
  : "${st:-}" "${proj:-}"   # 미사용 인자 silence(set -e 무해)
  printf '{"status":"alive"}\n'
}

case "$mode" in
  check)
    st=${3:?stale_s}
    _scan "$(date +%s%3N)" "$st"
    ;;
  loop)
    # 정식 경로: 메인이 Bash(run_in_background:true) 로 기동.
    # healthy → 무한 상주(조용, $0). stall → append + EXIT → Bash 도구가 메인 재호출(깨움).
    # safety-cap(기본 2700s) → "cap" 으로 exit (잊힌 watchdog 방지). 10분 Bash 캡 무관(detached 지속).
    st=${3:-180}; poll=${4:-30}; cap=${5:-2700}; t0=$(date +%s)
    while :; do
      if [ -f "$AC" ]; then
        R=$(_scan "$(date +%s%3N)" "$st")
        if ! printf '%s' "$R" | grep -q '"stalled":\[\]'; then
          printf '%s' "$R" | node -e 'const fs=require("fs");let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const o=JSON.parse(s);for(const x of o.stalled){fs.appendFileSync(process.argv[1],JSON.stringify({role:"WATCHDOG",ev:"stuck",agent:x.agent,role_of:x.role,silent_ms:x.silent_ms,ts:Date.now()})+"\n")}}catch(_){}})' "$LOG" 2>/dev/null || true
          echo "WATCHDOG_EXIT {\"status\":\"stuck\",\"detail\":$R}"
          exit 0
        fi
      fi
      if [ $(( $(date +%s) - t0 )) -ge "$cap" ]; then
        echo "WATCHDOG_EXIT {\"status\":\"cap\"}"; exit 0
      fi
      sleep "$poll"
    done
    ;;
  scan)
    st=${3:?stale_s}; since=${4:-0}
    _scan_status "$st" "$since"
    ;;
  watch)
    # 단일 watchdog 블로킹 루프 (Haiku 가 KICKOFF 에서 1회 호출). 이벤트/cap/stop 시 종료.
    poll=${3:-60}; cap=${4:-540}; stale=${5:-1200}; since_arg=${6:-}   # stale 1200>cap 540: active Worker 의 long-running SO 구현(첫 commit 전 execution-log·git 둘 다 조용, 측정 698s)을 false-stuck 으로 오판하던 결함 fix(2026-05-30). 진짜 stuck 은 blocked/escalate 즉시감지+cap self-respawn 주기점검+teammate idle_notification 으로 커버. since_arg(6번째)=self-respawn 전진 ts.
    since0=${since_arg:-$(date +%s%3N)}; t0=$(date +%s)
    while :; do
      touch "$dir/.self-wake-ts" 2>/dev/null || true     # heartbeat → Supervisor dedup(.self-wake-ts 신선=alive)
      # 이벤트 종료(stopped/phase_complete/escalate/stuck) 시 .self-wake-ts 제거 → Supervisor 재스폰 dedup 통과(REARM 가능).
      # 종료 직전까지의 신선 heartbeat 가 "다른 watchdog alive" 로 오판돼 재스폰을 막아 phase 후 watchdog 영구 idle 였음(2026-06-28 fix).
      # cap 만 예외 — self-respawn 으로 같은 watchdog 가 즉시 재진입하므로 heartbeat 유지(dedup skip 정상).
      if [ -f "$dir/.watchdog-stop" ]; then rm -f "$dir/.self-wake-ts" 2>/dev/null||true; echo 'WATCHDOG_RESULT {"status":"stopped"}'; exit 0; fi
      R=$(_scan_status "$stale" "$since0")
      case "$R" in
        *'"status":"alive"'*) : ;;
        *) rm -f "$dir/.self-wake-ts" 2>/dev/null||true; echo "WATCHDOG_RESULT $R"; exit 0 ;;
      esac
      if [ $(( $(date +%s) - t0 )) -ge "$cap" ]; then echo "WATCHDOG_RESULT {\"status\":\"cap\",\"next_since\":$(date +%s%3N)}"; exit 0; fi
      sleep "$poll"
    done
    ;;
  *) echo "usage: h2-watchdog.sh {check|loop|scan|watch} <h2dir> ..." >&2; exit 2 ;;
esac

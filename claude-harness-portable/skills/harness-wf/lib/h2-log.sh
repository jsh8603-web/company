#!/usr/bin/env bash
# harness-wf — execution-log.jsonl append-only SSOT + poll rendezvous
# 근거: 측정 — O_APPEND 동시(subagent+메인) append 무손상 / 1s 폴링 → 왕복 3.4s peer 랑데부.
# content 는 항상 이 파일로 흐른다 (메인 = relay 아님).
# usage:
#   h2-log.sh append <h2dir> <json-line>
#   h2-log.sh since  <h2dir> <ts_ms>                       # ts > 인 줄
#   h2-log.sh last   <h2dir> [role]                        # 마지막 매칭 줄
#   h2-log.sh wait   <h2dir> <role> <ev> <timeout_s> [poll_s]   # 랑데부 (전체스캔 — 단발 only)
#   h2-log.sh wait-since <h2dir> <role> <ev> <timeout_s> <poll_s> <since_ts>  # ts>since 만 매칭 (순차 sub-obj 안전: stale done/verdict 재매칭 차단). 매칭 시 해당 줄 stdout.
#   h2-log.sh wait-commit <h2dir> <since_sha> <timeout_s> <poll_s>  # 블로킹 git-commit 폴: <since_sha>..HEAD 새 commit(oneline, 시간순) 출력. Worker ev:done 누락(신규-1)에 무영향 — commit=ground truth. since_sha 빈값이면 HEAD 1개. proj=dirname(h2dir).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"

cmd=${1:-}; dir=${2:-}
if [ -z "$cmd" ] || [ -z "$dir" ]; then
  echo "usage: h2-log.sh {append|since|last|wait} <h2dir> ..." >&2; exit 2
fi
LOG="$dir/execution-log.jsonl"

case "$cmd" in
  append)
    line=${3:?json line required}
    printf '%s\n' "$line" >> "$LOG"   # O_APPEND: 작은 줄 원자적 (측정 입증)
    ;;
  since)
    ts=${3:?ts_ms required}
    node -e 'const fs=require("fs");const t=Number(process.argv[2]);let s="";try{s=fs.readFileSync(process.argv[1],"utf8")}catch(_){}for(const l of s.split("\n")){if(!l.trim())continue;try{const o=JSON.parse(l);if((o.ts||0)>t)console.log(l)}catch(_){}}' "$LOG" "$ts"
    ;;
  last)
    role=${3:-}
    node -e 'const fs=require("fs");const r=process.argv[2]||null;let s="";try{s=fs.readFileSync(process.argv[1],"utf8")}catch(_){}const ls=s.split("\n").filter(x=>x.trim());for(let i=ls.length-1;i>=0;i--){try{const o=JSON.parse(ls[i]);if(!r||o.role===r){console.log(ls[i]);break}}catch(_){}}' "$LOG" "$role"
    ;;
  wait)
    role=${3:?role}; ev=${4:?ev}; tmo=${5:?timeout_s}; poll=${6:-1}
    deadline=$(( $(date +%s) + tmo ))
    while [ "$(date +%s)" -le "$deadline" ]; do
      if [ -f "$LOG" ] && node -e 'const fs=require("fs");const[,f,r,e]=process.argv;let h=false;try{for(const l of fs.readFileSync(f,"utf8").split("\n")){if(!l.trim())continue;try{const o=JSON.parse(l);if(o.role===r&&o.ev===e){h=true;break}}catch(_){}}}catch(_){}process.exit(h?0:1)' "$LOG" "$role" "$ev"; then
        echo "MATCH role=$role ev=$ev"; exit 0
      fi
      sleep "$poll"
    done
    echo "TIMEOUT role=$role ev=$ev after ${tmo}s" >&2; exit 1
    ;;
  wait-since)
    role=${3:?role}; ev=${4:?ev}; tmo=${5:?timeout_s}; poll=${6:?poll_s}; since=${7:?since_ts}
    deadline=$(( $(date +%s) + tmo ))
    while [ "$(date +%s)" -le "$deadline" ]; do
      MATCHED=$(node -e 'const fs=require("fs");const[,f,r,e,st]=process.argv;const s=Number(st);let out="";try{for(const l of fs.readFileSync(f,"utf8").split("\n")){if(!l.trim())continue;try{const o=JSON.parse(l);if(o.role===r&&o.ev===e&&(o.ts||0)>s)out=l;}catch(_){}}}catch(_){}process.stdout.write(out)' "$LOG" "$role" "$ev" "$since" 2>/dev/null || true)
      if [ -n "$MATCHED" ]; then
        printf '%s\n' "$MATCHED"; exit 0
      fi
      sleep "$poll"
    done
    echo "TIMEOUT role=$role ev=$ev since=$since after ${tmo}s" >&2; exit 1
    ;;
  wait-commit)
    # 블로킹 git-commit 폴 — Worker done 신호 신뢰불가(신규-1) 대응, commit-SHA = ground truth.
    # since_sha 이후 새 commit 을 oneline(시간순)으로 출력. Verifier 가 ev:done 비의존 forward-pull 에 사용.
    since=${3:-}; tmo=${4:?timeout_s}; poll=${5:?poll_s}
    proj=$(cd "$dir/.." && pwd)
    deadline=$(( $(date +%s) + tmo ))
    while [ "$(date +%s)" -le "$deadline" ]; do
      if [ -n "$since" ]; then
        NEW=$(git -C "$proj" log --oneline --reverse "${since}..HEAD" 2>/dev/null || true)
      else
        NEW=$(git -C "$proj" log --oneline -1 2>/dev/null || true)
      fi
      if [ -n "$NEW" ]; then printf '%s\n' "$NEW"; exit 0; fi
      sleep "$poll"
    done
    echo "TIMEOUT wait-commit since=$since after ${tmo}s" >&2; exit 1
    ;;
  *)
    echo "unknown cmd: $cmd" >&2; exit 2
    ;;
esac

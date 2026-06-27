#!/usr/bin/env bash
# harness-wf — Agent dispatch prompt 조립 (메인이 Agent tool 호출 전 prompt 생성)
# scope-disclaimer 템플릿 + role + task + 스키마 placeholder 치환 → stdout (메인이 받아 Agent prompt 로 사용).
# 메인은 dispatch 시 Worker/Verifier/Healer = model:sonnet, SR = model:opus (창의 엔진·harness-wf 원본 충실 파리티) 로 호출할 것.
# usage:
#   h2-dispatch.sh <h2dir> <strict|sr> <role> <task_file> <schema> [rendezvous|mode]
#   (sr 일 때 마지막 인자 = MODE: C|T1|T2|T3|T4|A / strict 일 때 = RENDEZVOUS 문자열)
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"

dir=${1:?h2dir}; kind=${2:?strict|sr}; role=${3:?role}; taskf=${4:?task_file}; schema=${5:?schema}; extra=${6:-}
TPL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../templates" && pwd)"
case "$kind" in
  strict) tpl="$TPL_DIR/disclaimer-strict.txt" ;;
  sr)     tpl="$TPL_DIR/disclaimer-sr.txt" ;;
  *) echo "kind must be strict|sr" >&2; exit 2 ;;
esac
[ -f "$taskf" ] || { echo "task_file not found: $taskf" >&2; exit 2; }

node -e '
  const fs=require("fs");
  const [,tpl,h2,role,taskf,schema,extra,kind]=process.argv;
  let s=fs.readFileSync(tpl,"utf8");
  const task=fs.readFileSync(taskf,"utf8");
  const map={ "{{ROLE}}":role, "{{H2DIR}}":h2, "{{TASK}}":task, "{{SCHEMA}}":schema };
  if(kind==="sr"){ map["{{MODE}}"]=extra||"C"; } else { map["{{RENDEZVOUS}}"]=extra||"(없음 — execution-log append 만)"; }
  for(const [k,v] of Object.entries(map)) s=s.split(k).join(v);
  process.stdout.write(s);
' "$tpl" "$dir" "$role" "$taskf" "$schema" "$extra" "$kind"

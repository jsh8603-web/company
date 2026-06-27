#!/usr/bin/env bash
# harness-wf — phase-state.json atomic helper
# 근거: P3 측정 (tmp+rename, 6전이 tmp leak 0). 메인 turn-loop 상태 SSOT.
# usage:
#   h2-state.sh set        <h2dir> <json>
#   h2-state.sh get        <h2dir>
#   h2-state.sh field      <h2dir> <key>
#   h2-state.sh transition <h2dir> <state> <name> <phase>   # set + execution-log append
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"

cmd=${1:-}; dir=${2:-}
if [ -z "$cmd" ] || [ -z "$dir" ]; then
  echo "usage: h2-state.sh {set|get|field|transition} <h2dir> ..." >&2; exit 2
fi
PS="$dir/phase-state.json"
LOG="$dir/execution-log.jsonl"

atomic_write() { # $1=path $2=content  (tmp + rename = POSIX atomic on same fs)
  local tmp="$1.tmp.$$"
  printf '%s' "$2" > "$tmp"
  mv -f "$tmp" "$1"
}

case "$cmd" in
  set)
    json=${3:?json required}
    atomic_write "$PS" "$json"
    ;;
  get)
    cat "$PS"
    ;;
  field)
    key=${3:?key required}
    node -e 'const fs=require("fs");const s=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));process.stdout.write(String(s[process.argv[2]]??""))' "$PS" "$key"
    ;;
  transition)
    state=${3:?state}; name=${4:?name}; phase=${5:?phase}
    ts=$(date +%s%3N)
    json=$(node -e 'process.stdout.write(JSON.stringify({state:process.argv[1],name:process.argv[2],phase:Number(process.argv[3]),ts:Number(process.argv[4])}))' "$state" "$name" "$phase" "$ts")
    atomic_write "$PS" "$json"
    printf '%s\n' "{\"ev\":\"transition->$state\",\"name\":\"$name\",\"phase\":$phase,\"ts\":$ts}" >> "$LOG"
    ;;
  *)
    echo "unknown cmd: $cmd" >&2; exit 2
    ;;
esac

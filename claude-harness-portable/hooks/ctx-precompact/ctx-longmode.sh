#!/usr/bin/env bash
# ctx-longmode.sh — 컨텍스트 cap 토글 (opus 1m 전용 의미, 전역 flag 1회).
#
# 기본 cap = 500k. long-mode on = 750k (1회 토글, 중간 단계 없음).
#   on     : cap 500k → 750k (warn 630k / critical 720k)
#   off    : flag 제거 → cap 500k 원복 (warn 420k / critical 480k)
#   status : 현재 상태 출력 (default)
#
# flag = 전역 1개 파일($HOME/.claude/.ctx-longmode, 내용 "750000").
#   harness 메인 단일 세션 전제 → agent 가 자기 session_id 를 몰라도 토글 가능.
#   /compact(self-compact.sh) 또는 세션 재시작 시 자동 원복 권장.

FLAG="$HOME/.claude/.ctx-longmode"
ACTION="${1:-status}"

case "$ACTION" in
  on)
    if [ -f "$FLAG" ]; then
      echo "[ctx-longmode] ALREADY_ON cap=750k. 원복은 off." >&2
    else
      printf '750000' > "$FLAG"
      echo "[ctx-longmode] ON cap=750k (warn 630k / critical 720k). /compact·세션재시작 시 자동 원복." >&2
    fi
    ;;
  off)
    rm -f "$FLAG"
    echo "[ctx-longmode] OFF cap=500k 원복 (warn 420k / critical 480k)." >&2
    ;;
  status)
    if [ -f "$FLAG" ]; then echo "[ctx-longmode] STATUS=ON cap=750k" >&2
    else echo "[ctx-longmode] STATUS=OFF cap=500k" >&2; fi
    ;;
  *)
    echo "usage: ctx-longmode.sh [on|off|status]" >&2; exit 1
    ;;
esac

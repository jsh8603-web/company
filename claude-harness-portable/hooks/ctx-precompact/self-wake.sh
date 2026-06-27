#!/usr/bin/env bash
# self-wake.sh — 메인 세션 자가 깨우기 (auto-compact 후 idle 자동 재개).
#
# harness wf 없이 단독 세션에서, 압축 직후 메인이 멈춰 쉬는 걸 방지한다.
# 멀티플렉서(tmux/psmux) pane 을 주기 capture → 직전과 동일(=idle)하면 wake 메시지 주입.
# 작업이 끝나면 `stop` 으로 종료(STOP sentinel). transport = mux-lib.sh (self-compact.sh 와 공유).
#
#   self-wake.sh start [interval_s=180] ["wake msg"]   # detached 루프 시작
#   self-wake.sh stop                                   # 루프 종료
#   self-wake.sh status                                 # 동작 여부
#   self-wake.sh _tick ["msg"]                          # (내부/테스트) 1회 판정, sleep 없음
#   self-wake.sh _loop [interval] ["msg"]               # (내부) detached 루프 본체
#
# 테스트 env: WAKE_DRY=1 → 실제 주입 대신 [DRY] 로그 / WAKE_MOCK_CAP="..." → capture mock.

set -uo pipefail

CMD="${1:-status}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/mux-lib.sh"

STATE_DIR="$HOME/.claude/.self-wake"
STOP="$STATE_DIR/stop"; PIDF="$STATE_DIR/pid"; LOG="$STATE_DIR/log"; PREVF="$STATE_DIR/prev.snap"
SELF="$DIR/$(basename "${BASH_SOURCE[0]}")"
LOOP_SESS="claude-selfwake"
mkdir -p "$STATE_DIR"

# capture (WAKE_MOCK_CAP 우선 = 테스트).
_capture() {
  if [ -n "${WAKE_MOCK_CAP:-}" ]; then printf '%s' "$WAKE_MOCK_CAP"; return 0; fi
  mux_capture
}

# wake 주입 (WAKE_DRY → [DRY] 로그만).
_send() {
  local msg="$1"
  if [ -n "${WAKE_DRY:-}" ]; then echo "[self-wake][DRY] would send: $msg"; return 0; fi
  mux_send "$msg"
}

# 1회 판정: 직전 캡처와 동일(idle)하면 wake. 첫 호출/변화 있으면 skip.
_tick_once() {
  local msg="$1"
  local prev=""; [ -f "$PREVF" ] && prev="$(cat "$PREVF" 2>/dev/null)"
  local cur; cur="$(_capture 2>/dev/null || true)"
  printf '%s' "$cur" > "$PREVF"
  if [ -n "$cur" ] && [ "$cur" = "$prev" ]; then
    _send "$msg" && echo "$(date -Iseconds 2>/dev/null || date) WAKE injected" >> "$LOG"
    return 0
  fi
  return 2
}

case "$CMD" in
  start)
    interval="${2:-180}"
    MSG="${3:-계속 진행 — 압축 후 자동 재개. 작업이 끝났으면 self-wake.sh stop.}"
    rm -f "$STOP" "$PREVF"
    if [ "$(_mux_kind)" = none ]; then
      echo "[self-wake] ❌ 멀티플렉서(tmux/psmux) 미감지 — start 불가" >&2; exit 1
    fi
    if mux_new_detached "$LOOP_SESS" "bash '$SELF' _loop $interval '$MSG'"; then
      echo "[self-wake] ✅ started (interval=${interval}s, transport=$(_mux_kind), loop session=$LOOP_SESS). 종료: self-wake.sh stop"
    else
      echo "[self-wake] ❌ detached 루프 생성 실패" >&2; exit 1
    fi
    ;;
  stop)
    touch "$STOP"
    mux_kill "$LOOP_SESS" || true
    rm -f "$PIDF"
    echo "[self-wake] stopped (sentinel + loop session kill)"
    ;;
  status)
    if [ -f "$STOP" ]; then echo "[self-wake] STATUS=stopped"
    elif [ -f "$PIDF" ]; then echo "[self-wake] STATUS=running (pid $(cat "$PIDF" 2>/dev/null), loop=$LOOP_SESS)"
    else echo "[self-wake] STATUS=idle (미시작)"; fi
    ;;
  _tick)
    _tick_once "${2:-계속 진행}"; exit $?
    ;;
  _loop)
    interval="${2:-180}"; MSG="${3:-계속 진행}"
    echo $$ > "$PIDF"
    while [ ! -f "$STOP" ]; do
      sleep "$interval"
      [ -f "$STOP" ] && break
      _tick_once "$MSG" || true
    done
    rm -f "$PIDF"
    echo "$(date -Iseconds 2>/dev/null || date) loop stopped" >> "$LOG"
    ;;
  *)
    echo "usage: self-wake.sh {start [interval] [msg]|stop|status}" >&2; exit 1
    ;;
esac

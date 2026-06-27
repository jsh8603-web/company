#!/usr/bin/env bash
# mux-lib.sh — 멀티플렉서(tmux/psmux) transport 추상화. source 해서 사용.
#
# self-compact.sh / self-wake.sh 공용. psmux·tmux 여부와 관계없이 동작하게:
#   - psmux 실행파일 경로: PSMUX_BIN env → PATH(command -v) → winget glob 자동탐색
#   - psmux session 명:    PSMUX_SESSION → PSMUX_TARGET_SESSION → display-message '#S'
#   - 우선순위: 실제 tmux 명령 + $TMUX > psmux > 없음
#     (⚠️ psmux 는 $TMUX env 를 설정하므로 tmux 는 'command -v tmux' 실제 명령 가용으로만 판정)
#
# 제공: _mux_kind / _mux_session / mux_capture / mux_send / mux_new_detached / mux_kill

# psmux 실행파일 경로 해결 (없으면 비영 return).
_mux_psmux_bin() {
  if [ -n "${PSMUX_BIN:-}" ] && [ -x "$PSMUX_BIN" ]; then echo "$PSMUX_BIN"; return 0; fi
  local b; b="$(command -v psmux 2>/dev/null)"; [ -n "$b" ] && { echo "$b"; return 0; }
  local c
  for c in "$HOME"/AppData/Local/Microsoft/WinGet/Packages/marlocarlo.psmux*/psmux.exe \
           "${LOCALAPPDATA:-}"/Microsoft/WinGet/Packages/marlocarlo.psmux*/psmux.exe; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

# 멀티플렉서 종류: tmux | psmux | none
_mux_kind() {
  if command -v tmux >/dev/null 2>&1 && [ -n "${TMUX:-}" ]; then echo tmux; return 0; fi
  if _mux_psmux_bin >/dev/null 2>&1; then echo psmux; return 0; fi
  echo none; return 1
}

# psmux session 명 해결.
_mux_session() {
  if [ -n "${PSMUX_SESSION:-}" ]; then echo "$PSMUX_SESSION"; return 0; fi
  if [ -n "${PSMUX_TARGET_SESSION:-}" ]; then echo "$PSMUX_TARGET_SESSION"; return 0; fi
  local b; b="$(_mux_psmux_bin)" || return 1
  MSYS_NO_PATHCONV=1 "$b" display-message -p '#S' 2>/dev/null | tr -d '[:space:]'
}

# 현재 pane 캡처 (stdout).
mux_capture() {
  case "$(_mux_kind)" in
    tmux)  tmux capture-pane -p 2>/dev/null ;;
    psmux) local b s; b="$(_mux_psmux_bin)"; s="$(_mux_session)"; [ -n "$s" ] || return 1
           MSYS_NO_PATHCONV=1 "$b" capture-pane -p -t "$s" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

# 텍스트 입력 + Enter ($1=text). MUX_DRY=1 → 실행 대신 명령 echo (테스트).
mux_send() {
  local msg="$1" b s
  case "$(_mux_kind)" in
    tmux)  [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] tmux send-keys \"$msg\" Enter"; return 0; }
           tmux send-keys "$msg" Enter ;;
    psmux) b="$(_mux_psmux_bin)"; s="$(_mux_session)"; [ -n "$s" ] || return 1
           [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] $b send-keys -t $s \"$msg\" Enter"; return 0; }
           MSYS_NO_PATHCONV=1 "$b" send-keys -t "$s" "$msg" Enter ;;
    *) return 1 ;;
  esac
}

# detached session 생성 ($1=session명, $2=command). MUX_DRY=1 → echo.
mux_new_detached() {
  local b
  case "$(_mux_kind)" in
    tmux)  [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] tmux new-session -d -s $1 \"$2\""; return 0; }
           tmux new-session -d -s "$1" "$2" ;;
    psmux) b="$(_mux_psmux_bin)"
           [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] $b new-session -d -s $1 \"$2\""; return 0; }
           MSYS_NO_PATHCONV=1 "$b" new-session -d -s "$1" "$2" ;;
    *) return 1 ;;
  esac
}

# session kill ($1=session명).
mux_kill() {
  local b
  case "$(_mux_kind)" in
    tmux)  [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] tmux kill-session -t $1"; return 0; }
           tmux kill-session -t "$1" 2>/dev/null ;;
    psmux) b="$(_mux_psmux_bin)"
           [ -n "${MUX_DRY:-}" ] && { echo "[MUX_DRY] $b kill-session -t $1"; return 0; }
           MSYS_NO_PATHCONV=1 "$b" kill-session -t "$1" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

#!/usr/bin/env bash
# self-compact.sh — 세션이 스스로 /compact 를 자기 터미널에 입력한다.
#
# critical 도달 시 ctx-precompact.js 가 "이 스크립트를 실행하라"고 지시 → agent 가
# Bash tool 로 호출 → 멀티플렉서(tmux/psmux)를 자동 감지해 자기 pane 에 /compact 입력.
# hook 이 외부에서 강제 주입하는 게 아니라, **세션이 스스로** 실행하는 자율 압축 경로.
#
# 멀티플렉서가 없으면 안내만 출력 → 사용자가 직접 /compact 입력하거나
# autoCompactEnabled 네이티브 압축에 맡긴다.
# 압축 시 long-mode flag 도 함께 원복(cap 750k → 500k).

FLAG="$HOME/.claude/.ctx-longmode"
rm -f "$FLAG" 2>/dev/null || true   # 압축 = long-mode 자동 원복

if [ -n "$TMUX" ]; then
  tmux send-keys "/compact" Enter
  echo "[self-compact] tmux: /compact 입력 완료. 압축 후 저장한 맥락으로 작업 속개."
elif [ -n "$PSMUX_SESSION" ] && command -v psmux >/dev/null 2>&1; then
  psmux send-keys -t "$PSMUX_SESSION" "/compact" Enter
  echo "[self-compact] psmux($PSMUX_SESSION): /compact 입력 완료. 압축 후 작업 속개."
elif command -v tmux >/dev/null 2>&1 && tmux list-panes >/dev/null 2>&1; then
  tmux send-keys "/compact" Enter
  echo "[self-compact] tmux(detected): /compact 입력 완료. 압축 후 작업 속개."
else
  echo "[self-compact] 멀티플렉서(tmux/psmux) 미감지 — 직접 '/compact' 를 입력하거나 autoCompactEnabled 네이티브 압축에 맡기세요. (저장은 이미 완료했으니 압축 후 그대로 재개됩니다.)"
fi

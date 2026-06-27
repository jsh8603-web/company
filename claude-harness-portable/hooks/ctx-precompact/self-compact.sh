#!/usr/bin/env bash
# self-compact.sh — 세션이 스스로 /compact 를 자기 터미널에 입력한다.
#
# critical 도달 시 ctx-precompact.js 가 "이 스크립트를 실행하라"고 지시 → agent 가
# Bash tool 로 호출 → mux-lib 가 멀티플렉서(tmux/psmux)를 자동 감지해 자기 pane 에 /compact 입력.
# hook 이 외부에서 강제 주입하는 게 아니라, **세션이 스스로** 실행하는 자율 압축 경로.
#
# 멀티플렉서가 없으면 안내만 출력 → 직접 /compact 입력하거나 autoCompactEnabled 에 위임.
# 압축 시 long-mode flag 도 함께 원복(cap 750k → 500k).

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/mux-lib.sh"

# 핸드오프 게이트 (handoff-guide.md 연동, 2차 확인): handoff-done sentinel 도 우회도 없으면 거부.
# PreCompact 훅(ctx-precompact-pre.js)이 1차 hard block 이고, 여기는 세션 자율 경로 친절 안내.
CWD="$(pwd)"
SENT="$CWD/.ctx-precompact/handoff-done"
SKIP="$CWD/.ctx-precompact/handoff-skip"
if [ ! -f "$SENT" ] && [ ! -f "$SKIP" ]; then
  echo "[self-compact] ⛔ 핸드오프 미작성 — handoff-guide.md 로 작성 후 'echo <md경로> > $SENT' 기록하고 재호출. 긴급 우회: touch $SKIP" >&2
  exit 1
fi

rm -f "$HOME/.claude/.ctx-longmode" 2>/dev/null || true   # 압축 = long-mode 자동 원복

if mux_send "/compact"; then
  echo "[self-compact] /compact 입력 완료 ($(_mux_kind)). 압축 후 저장한 맥락으로 작업 속개."
else
  echo "[self-compact] 멀티플렉서(tmux/psmux) 미감지 — 직접 '/compact' 를 입력하거나 autoCompactEnabled 네이티브 압축에 맡기세요. (저장은 이미 완료했으니 압축 후 그대로 재개됩니다.)"
fi

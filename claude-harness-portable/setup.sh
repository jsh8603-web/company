#!/usr/bin/env bash
# setup.sh — claude-harness-portable 설치 (다른 PC 에서 바로 적용).
#   1) skills/harness-wf      → ~/.claude/skills/harness-wf
#   2) hooks/ctx-precompact   → ~/.claude/hooks/ctx-precompact
#   3) settings.json 에 PostToolUse/PreCompact 훅 + autoCompactEnabled 병합
#
# 사용: bash setup.sh   (CLAUDE_HOME 으로 대상 디렉토리 override 가능)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_HOME:-$HOME/.claude}"
NODE="$(command -v node || true)"

if [ -z "$NODE" ]; then
  echo "[setup] ❌ node 미발견 — node 설치 후 재실행 (훅이 node 로 동작)." >&2
  exit 1
fi

echo "[setup] 대상: $CLAUDE_DIR"
mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/hooks"

echo "[setup] (1/3) 스킬 설치 (skills/* — harness-wf, debate ...)..."
for sk in "$HERE/skills"/*/; do
  name="$(basename "$sk")"
  rm -rf "$CLAUDE_DIR/skills/$name"
  cp -r "$sk" "$CLAUDE_DIR/skills/$name"
  echo "  - skills/$name"
done

echo "[setup] (2/3) ctx-precompact 훅 설치..."
rm -rf "$CLAUDE_DIR/hooks/ctx-precompact"
cp -r "$HERE/hooks/ctx-precompact" "$CLAUDE_DIR/hooks/"

# 실행권한
chmod +x "$CLAUDE_DIR/hooks/ctx-precompact/"*.sh 2>/dev/null || true
chmod +x "$CLAUDE_DIR/skills/"*/lib/*.sh 2>/dev/null || true

echo "[setup] (3/3) settings.json 훅 등록..."
SETTINGS="$CLAUDE_DIR/settings.json"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
# 백업
cp "$SETTINGS" "$SETTINGS.bak.$(date +%s)" 2>/dev/null || true
"$NODE" "$HERE/setup-merge-settings.js" "$SETTINGS" "$CLAUDE_DIR"

echo ""
echo "[setup] ✅ 완료."
echo "  - harness 트리거: '하네스wf' / 'harness' (skills/harness-wf)"
echo "  - debate 트리거: 'debate' / '토론' / '반론' (skills/debate, transport=harness-wf/lib 재사용)"
echo "  - 계획 wf 트리거: '계획 wf' / '강화 계획' / '상세 계획' (skills/enhanced-planning-wf)"
echo "  - 압축 전 핸드오프 강제: handoff-guide.md 기준 미작성 시 /compact 차단 (PreCompact 게이트)"
echo "  - 압축 cap: 기본 500k, long-mode 750k → 'bash ~/.claude/hooks/ctx-precompact/ctx-longmode.sh on'"
echo "  - critical(96%) 도달 시 세션이 self-compact.sh 로 스스로 /compact 입력"
echo "  - Claude Code 재시작 후 settings.json 훅 반영됨."

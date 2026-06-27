# harness-wf — node PATH 해석 (MSYS2/Windows 환경 node 미탑재 함정 대응).
# 다른 lib/h2-*.sh 가 source. SSOT = ~/.claude/hooks/node-runner.sh 와 동일 방식.
if ! command -v node >/dev/null 2>&1; then
  for d in "/c/Program Files/nodejs" "/c/tools/nodejs" "$HOME/.local/bin" "/c/Users/$USER/AppData/Roaming/npm"; do
    if [ -x "$d/node.exe" ] || [ -x "$d/node" ]; then export PATH="$d:$PATH"; break; fi
  done
fi
command -v node >/dev/null 2>&1 || { echo "h2: node binary not found on PATH" >&2; exit 1; }

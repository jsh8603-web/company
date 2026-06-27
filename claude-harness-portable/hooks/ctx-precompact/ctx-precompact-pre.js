'use strict';
// ctx-precompact-pre.js — portable PreCompact hook (핸드오프 게이트 + cooldown marker).
//
// (1) 핸드오프 게이트 (handoff-wf 연동): /compact 직전, <cwd>/.ctx-precompact/handoff-done
//     sentinel(내용=핸드오프 md 절대경로)이 가리키는 md 가 실제 존재 + 최소 크기 이상이어야
//     통과. 아니면 exit(2) 로 압축 차단 → "압축 전 무조건 핸드오프 작성" 강제.
//     모든 압축 경로(수동 /compact + native auto-compact)가 PreCompact 를 거치므로 둘 다 차단된다.
//     긴급 우회: <cwd>/.ctx-precompact/handoff-skip (1회용, 인계 포기).
// (2) 통과 시 cooldown 'PENDING' marker write. 압축 직후 transcript tail 의 last usage 는
//     압축 전 stale 값이라, 첫 PostToolUse 가 critical 을 재발화해 연속 압축을 유발할 수 있다.
//     PENDING → ctx-precompact.js 가 첫 호출을 stale 로 잡고 SKIP, 새 응답 등장 시 자동 해제.
//
// stdin JSON: { session_id, cwd, transcript_path, ... }
// Claude Code 표준: PreCompact 에서 exit(2) = 압축 block, stderr = 사유(세션에 전달).

const fs = require('fs');
const path = require('path');

const MIN_HANDOFF_BYTES = 400; // 빈/스텁 핸드오프 우회 차단 (6섹션이면 수 KB)

function writeCooldown(dir, sid) {
  try {
    fs.mkdirSync(dir, { recursive: true });
    if (sid) fs.writeFileSync(path.join(dir, `${sid}.cooldown`), 'PENDING');
  } catch {}
}

try {
  const p = JSON.parse(fs.readFileSync(0, 'utf8'));
  const sid = p.session_id;
  const cwd = p.cwd || process.cwd();
  const dir = path.join(cwd, '.ctx-precompact');
  const dirFwd = dir.replace(/\\/g, '/');
  const skip = path.join(dir, 'handoff-skip');
  const sentinel = path.join(dir, 'handoff-done');

  // 긴급 우회 (1회용 소비)
  if (fs.existsSync(skip)) {
    try { fs.unlinkSync(skip); } catch {}
    writeCooldown(dir, sid);
    process.exit(0);
  }

  // 핸드오프 검증: sentinel 이 가리키는 md 가 실제 존재 + 최소 크기
  let ok = false;
  try {
    const mdPath = String(fs.readFileSync(sentinel, 'utf8')).trim();
    if (mdPath && fs.existsSync(mdPath) && fs.statSync(mdPath).size >= MIN_HANDOFF_BYTES) ok = true;
  } catch {}

  if (ok) {
    try { fs.unlinkSync(sentinel); } catch {} // 소비 → 다음 압축 때 재작성 강제
    writeCooldown(dir, sid);
    process.exit(0);
  }

  // 차단 — 핸드오프 작성 유도
  const reason = [
    '🔍 /compact 차단 — 핸드오프 미작성/부실 (압축 전 무조건 작성).',
    '핸드오프 가이드(~/.claude/hooks/ctx-precompact/handoff-guide.md)로 6섹션 + 작업단위 5필드 핸드오프 md 작성 →',
    `mkdir -p "${dirFwd}" && echo "<핸드오프 md 절대경로>" > "${dirFwd}/handoff-done" → /compact 재시도.`,
    `긴급 우회(인계 포기): touch "${dirFwd}/handoff-skip"`,
  ].join('\n');
  try { process.stderr.write(reason); } catch {}
  process.exit(2);
} catch {
  // 파싱 실패 = 안전하게 통과 (압축 영구 차단으로 세션이 멈추는 것 방지)
  process.exit(0);
}

'use strict';
// ctx-precompact-pre.js — portable PreCompact hook.
// /compact 직전 fire → cooldown 'PENDING' marker write.
// 압축 직후 transcript tail 의 last usage 는 압축 전 stale 값이라, 첫 PostToolUse 1-2회가
// critical 을 재발화해 연속 압축을 유발할 수 있다. PENDING marker → ctx-precompact.js 가
// 첫 호출 토큰을 stale 로 잡고 SKIP, 새 응답 등장(토큰 변동) 시 자동 해제한다.
//
// stdin JSON: { session_id, cwd, transcript_path, ... }

const fs = require('fs');
const path = require('path');

try {
  const p = JSON.parse(fs.readFileSync(0, 'utf8'));
  const sid = p.session_id;
  const cwd = p.cwd || process.cwd();
  if (sid) {
    const d = path.join(cwd, '.ctx-precompact');
    fs.mkdirSync(d, { recursive: true });
    fs.writeFileSync(path.join(d, `${sid}.cooldown`), 'PENDING');
  }
} catch {}
process.exit(0);

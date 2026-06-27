'use strict';
// ctx-precompact.js — portable PostToolUse hook (사전압축 경고 + 자가 압축 지시).
//
// 매 tool call 뒤 실행. 세션 transcript(jsonl)의 last usage 로 토큰을 추산 →
// cap 임계 돌파 시 경고(warn) 또는 압축 지시(critical)를 additionalContext 로 주입한다.
//
// 설계 (button ctx-warn-post-tool.js 의 portable 파생 — self-contained):
//   - registry(.session-registry.txt) 의존 제거: 세션 식별 = stdin 의 session_id,
//     토큰/모델 = stdin 의 transcript_path 직접 tail (어느 환경에서도 동작).
//   - 외부 body md / log-event 의존 제거: 경고 본문 인라인.
//   - cap: opus 기본 500k, long-mode flag 시 750k (1회 토글, ctx-longmode.sh).
//          sonnet/haiku = 180k (물리 200k 한계 고려).
//          비율: warn 84% / critical 96% / clear 24%.
//   - critical 도달 시 → 세션이 **스스로** /compact 를 입력하도록 지시(self-compact.sh).
//     hook 이 외부에서 강제 주입하지 않는다(세션 자율 = 사용자 선호).
//
// stdin JSON: { session_id, transcript_path, cwd, agent_id?, agent_type?, ... }
// stdout JSON: { hookSpecificOutput: { hookEventName:'PostToolUse', additionalContext } }

const fs = require('fs');
const path = require('path');
const os = require('os');

const HOME = process.env.USERPROFILE || os.homedir();
// long-mode flag = 전역 1개 파일 (harness 메인 단일 세션 전제 — agent 가 session_id 를
// 몰라도 ctx-longmode.sh on 으로 토글 가능). 내용 = cap 숫자("750000"). 존재 = long-mode.
const LONGMODE_FLAG = path.join(HOME, '.claude', '.ctx-longmode');

// cap 임계: opus 기본 500k / long-mode 750k. sonnet·haiku 180k.
function getThresholds(model) {
  const m = String(model || '').toLowerCase();
  const isOpus = m.includes('opus');
  if (isOpus) {
    let cap = 500_000;
    try {
      if (fs.existsSync(LONGMODE_FLAG)) {
        const raw = (fs.readFileSync(LONGMODE_FLAG, 'utf8') || '').trim();
        cap = parseInt(raw, 10) || 750_000;
      }
    } catch {}
    return {
      warn: Math.round(cap * 0.84),
      critical: Math.round(cap * 0.96),
      clear: Math.round(cap * 0.24),
      cap,
    };
  }
  // sonnet/haiku: 물리 컨텍스트 ~200k → opus cap 보다 반드시 작게.
  return { warn: 130_000, critical: 160_000, clear: 40_000, cap: 180_000 };
}

function noop() { try { process.stdout.write(''); } catch {} process.exit(0); }

function emitLine(status, kv = {}) {
  try {
    const id = kv.stage === 'critical' ? 'ctx-precompact.critical'
             : kv.stage === 'warn' ? 'ctx-precompact.warn' : 'ctx-precompact';
    const parts = Object.entries(kv)
      .filter(([k, v]) => k !== 'stage' && v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${k}=${String(v).replace(/\s+/g, '_')}`);
    process.stderr.write(`[${id}] ${status} ${parts.join(' ')}\n`);
  } catch {}
}

function emit(body, kv) {
  if (kv) emitLine('FIRE', kv);
  try {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: body },
    }));
  } catch {}
  process.exit(0);
}

// transcript jsonl 끝에서 마지막 usage(토큰 합) + model 추출.
function tailJsonl(transcriptPath) {
  try {
    const stat = fs.statSync(transcriptPath);
    const size = stat.size;
    if (!size) return null;
    const chunk = Math.min(262144, size);
    const fd = fs.openSync(transcriptPath, 'r');
    const buf = Buffer.alloc(chunk);
    fs.readSync(fd, buf, 0, chunk, size - chunk);
    fs.closeSync(fd);
    const lines = buf.toString('utf8').split('\n');
    let tokens = null, model = null;
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (!line || line[0] !== '{') continue;
      try {
        const d = JSON.parse(line);
        const u = d && d.message && d.message.usage;
        if (u && tokens == null) {
          tokens = (u.input_tokens || 0)
                 + (u.cache_creation_input_tokens || 0)
                 + (u.cache_read_input_tokens || 0);
        }
        if (d && d.message && d.message.model && !model) model = d.message.model;
        if (tokens != null && model) break;
      } catch {}
    }
    return { tokens, model };
  } catch { return null; }
}

// ── latch / cooldown (cwd 하위, 프로젝트 격리) ──
function latchDir(cwd) { return path.join(cwd, '.ctx-precompact'); }
function latchPath(cwd, sid, stage) { return path.join(latchDir(cwd), `${sid}.${stage}.json`); }
function cooldownPath(cwd, sid) { return path.join(latchDir(cwd), `${sid}.cooldown`); }

function readLatch(cwd, sid, stage) {
  try { return JSON.parse(fs.readFileSync(latchPath(cwd, sid, stage), 'utf8')); }
  catch { return null; }
}
function writeLatch(cwd, sid, stage, obj) {
  try {
    fs.mkdirSync(latchDir(cwd), { recursive: true });
    fs.writeFileSync(latchPath(cwd, sid, stage), JSON.stringify(obj));
  } catch {}
}
function deleteLatch(cwd, sid, stage) {
  try { fs.unlinkSync(latchPath(cwd, sid, stage)); } catch {}
}

// post-compact cooldown (이벤트 기반 stale-token 방지): /compact 직후 jsonl tail
// last usage 는 압축 전 stale 값 그대로 남아 tool call 1-2회만에 재판정될 수 있다.
//   - PreCompact hook(ctx-precompact-pre.sh)이 'PENDING' marker write
//   - 첫 PostToolUse 가 현재 tokens 를 stale 로 기록 + SKIP
//   - tokens == stale → 여전히 stale → SKIP / tokens != stale → 새 응답 등장 → 해제
function checkCooldown(cwd, sid, tokens) {
  try {
    const p = cooldownPath(cwd, sid);
    const raw = String(fs.readFileSync(p, 'utf8')).trim();
    if (raw === 'PENDING' || raw === '') {
      try { fs.writeFileSync(p, String(tokens)); } catch {}
      return true;
    }
    const stale = parseInt(raw, 10);
    if (!Number.isFinite(stale)) { try { fs.unlinkSync(p); } catch {} return false; }
    if (tokens === stale) return true;
    try { fs.unlinkSync(p); } catch {}
    return false;
  } catch { return false; }
}

function buildWarnBody({ kTok, pct, criticalK, cap }) {
  const isOpus = cap >= 500_000;
  const longHint = (isOpus && cap < 750_000)
    ? `🔀 **long-mode 우회 (opus, ckpt 와 동등한 정식 탈출구)**: 잔여 작업이 적으면 \`bash ~/.claude/hooks/ctx-precompact/ctx-longmode.sh on\` 1회 → cap ${Math.round(cap/1000)}k→750k 확장 → warn 즉시 해제, 작업 그대로 속개. /compact·resume 시 자동 원복.`
    : '';
  return [
    `⚠️ [컨텍스트 경고] ${kTok}k tok (${pct}%) — cap ${Math.round(cap/1000)}k. 진행 중 작업의 핵심 상태(다음 의도·열어본 파일·미해결 결정)를 progress.md 또는 메모에 1회 저장해 두면 ${criticalK}k 압축 시 맥락 유실이 없다.`,
    longHint,
    `${criticalK}k 도달 시 자동으로 압축(/compact)을 입력하라는 지시가 주입된다. 지금은 저장만 하고 작업을 계속해도 된다.`,
  ].filter(Boolean).join('\n');
}

function buildCriticalBody({ kTok, pct, cwd }) {
  const cwdFwd = cwd.replace(/\\/g, '/');
  return [
    `🚨 [최우선 — 컨텍스트 CRITICAL] ${kTok}k tok (${pct}%). 아래 2단계를 이번 turn 에 완료한다 (둘 다 필수, 건너뛰기 금지):`,
    `1) **저장**: 진행 중 작업의 (a)마지막 결정 (b)다음 의도 (c)열어본 핵심 파일·재개 지점 을 \`${cwdFwd}/progress.md\` 하단 또는 메모에 구체적으로 1회 기록. "진행 중" 류 추상 금지.`,
    `2) **세션 스스로 /compact 입력**: 저장 직후 다음 Bash 1회만 호출 → 세션이 자기 터미널에 /compact 를 입력한다(멀티플렉서 자동 감지): \`bash ~/.claude/hooks/ctx-precompact/self-compact.sh\``,
    `   ↳ 멀티플렉서(tmux/psmux)가 없으면 self-compact.sh 가 안내만 하고, 그 경우 직접 \`/compact\` 를 입력하거나 autoCompactEnabled 네이티브 압축에 맡긴다.`,
    `⛔ subagent 작업 중(결과 미반환)이면 /compact 가 결과를 고아화한다 — subagent 완료·결과 수집 후에만 압축. 또는 opus 면 \`ctx-longmode.sh on\`(750k) 으로 압축 자체를 회피.`,
    `압축 후엔 저장한 내용으로 작업을 그대로 이어간다.`,
  ].join('\n');
}

(function main() {
  try {
    const raw = fs.readFileSync(0, 'utf8');
    let p = {};
    try { p = JSON.parse(raw); } catch {}
    // subagent 발 tool call 엔 주입 skip (메인만). subagent /compact 주입 = 메인 강제압축 유발.
    if (p.agent_id || p.agent_type) return noop();

    const sid = p.session_id;
    const tp = p.transcript_path;
    const cwd = p.cwd || process.cwd();
    if (!sid || !tp) return noop();

    const info = tailJsonl(tp);
    if (!info || info.tokens == null) return noop();

    const th = getThresholds(info.model);
    const kTok = Math.floor(info.tokens / 1000);
    const pct = Math.floor((info.tokens / th.cap) * 100);
    const criticalK = Math.floor(th.critical / 1000);

    if (info.tokens < th.clear) {
      deleteLatch(cwd, sid, 'warn');
      deleteLatch(cwd, sid, 'critical');
      return noop();
    }
    if (info.tokens < th.warn) return noop();

    if (info.tokens >= th.critical) {
      if (checkCooldown(cwd, sid, info.tokens)) {
        emitLine('SKIP', { stage: 'critical', sid, reason: 'post-compact-stale-token', kTok, pct });
        return noop();
      }
      // critical: 해제 로직 없음 — 매 tool call FIRE 로 /compact 행동을 강제.
      // logEvent/stderr 는 최초 1회만 (도배 방지).
      const latch = readLatch(cwd, sid, 'critical');
      const firstFire = !latch || !latch.fire_ts;
      if (firstFire) writeLatch(cwd, sid, 'critical', { fire_ts: Date.now() });
      return emit(buildCriticalBody({ kTok, pct, cwd }),
        firstFire ? { stage: 'critical', sid, kTok, pct } : null);
    }

    // warn: cooldown 통과 + firstFire 만 1회 경고 (이후 동일 단계 재발화 안 함).
    if (checkCooldown(cwd, sid, info.tokens)) {
      emitLine('SKIP', { stage: 'warn', sid, reason: 'post-compact-stale-token', kTok, pct });
      return noop();
    }
    const latch = readLatch(cwd, sid, 'warn');
    const firstFire = !latch || !latch.fire_ts;
    if (!firstFire) return noop();
    writeLatch(cwd, sid, 'warn', { fire_ts: Date.now() });
    return emit(buildWarnBody({ kTok, pct, criticalK, cap: th.cap }),
      { stage: 'warn', sid, kTok, pct });
  } catch {
    return noop();
  }
})();

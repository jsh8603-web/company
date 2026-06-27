'use strict';
// setup-merge-settings.js — ~/.claude/settings.json 에 ctx-precompact 훅을 idempotent 병합.
//   PostToolUse → ctx-precompact.js (사전압축 경고 + 자가 압축 지시)
//   PreCompact  → ctx-precompact-pre.js (cooldown marker)
//   autoCompactEnabled → true (네이티브 압축 안전망)
// 기존 설정/다른 훅은 보존. 중복 등록 방지(command 문자열 매칭).
//
// usage: node setup-merge-settings.js <settings.json path> <claude_dir>

const fs = require('fs');
const path = require('path');

const SETTINGS = process.argv[2];
const CLAUDE_DIR = process.argv[3];
if (!SETTINGS || !CLAUDE_DIR) { console.error('usage: node setup-merge-settings.js <settings.json> <claude_dir>'); process.exit(1); }

const fwd = (p) => p.replace(/\\/g, '/');
const POST_CMD = `node "${fwd(path.join(CLAUDE_DIR, 'hooks', 'ctx-precompact', 'ctx-precompact.js'))}"`;
const PRE_CMD = `node "${fwd(path.join(CLAUDE_DIR, 'hooks', 'ctx-precompact', 'ctx-precompact-pre.js'))}"`;

let cfg = {};
try { cfg = JSON.parse(fs.readFileSync(SETTINGS, 'utf8')); } catch { cfg = {}; }
if (!cfg.hooks) cfg.hooks = {};

// 해당 event 배열에서 command 가 이미 등록됐는지(부분 매칭) 검사 후 없으면 추가.
function ensureHook(event, command, matcher) {
  if (!Array.isArray(cfg.hooks[event])) cfg.hooks[event] = [];
  const arr = cfg.hooks[event];
  const exists = arr.some((entry) =>
    Array.isArray(entry.hooks) && entry.hooks.some((h) => typeof h.command === 'string' && h.command.includes('ctx-precompact')));
  if (exists) {
    // 경로 갱신(재설치 대비): ctx-precompact 포함 command 를 최신 절대경로로 교체.
    for (const entry of arr) {
      if (!Array.isArray(entry.hooks)) continue;
      for (const h of entry.hooks) {
        if (typeof h.command === 'string' && h.command.includes('ctx-precompact.js')) h.command = POST_CMD;
        if (typeof h.command === 'string' && h.command.includes('ctx-precompact-pre.js')) h.command = PRE_CMD;
      }
    }
    return 'updated';
  }
  arr.push({ matcher, hooks: [{ type: 'command', command }] });
  return 'added';
}

const r1 = ensureHook('PostToolUse', POST_CMD, '');
const r2 = ensureHook('PreCompact', PRE_CMD, '');
if (cfg.autoCompactEnabled === undefined) cfg.autoCompactEnabled = true;

fs.writeFileSync(SETTINGS, JSON.stringify(cfg, null, 2) + '\n');
console.log(`[setup] settings.json: PostToolUse=${r1}, PreCompact=${r2}, autoCompactEnabled=${cfg.autoCompactEnabled}`);

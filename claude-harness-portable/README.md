# claude-harness-portable

다른 PC 에서 바로 적용 가능한 **Claude Code 자산 2종** — 단일 워커 harness 워크플로우 + 사전압축 훅.
`bash setup.sh` 1회로 `~/.claude` 에 설치된다 (registry/psmux 같은 환경 전용 인프라 의존 없음).

## 구성

```
claude-harness-portable/
  skills/harness-wf/         # 단일 워커 harness 워크플로우 (트리거: 하네스wf / harness)
    skill.md  protocol.md    # 진입점 + 런타임 SSOT
    lib/*.sh                 # 상태머신·로그·watchdog·teammate-spawn (SSOT=teammate-spawn.sh build())
    templates/               # role/disclaimer 템플릿
  hooks/ctx-precompact/      # 사전압축 훅
    ctx-precompact.js        # PostToolUse — cap 임계 경고 + 자가 압축 지시
    ctx-precompact-pre.js    # PreCompact — 압축 후 stale-token cooldown marker
    ctx-longmode.sh          # cap 500k ↔ 750k 토글 (1회)
    self-compact.sh          # 세션이 스스로 /compact 입력 (tmux/psmux 자동 감지)
  setup.sh                   # 설치 + settings.json 훅 등록
  setup-merge-settings.js    # settings.json idempotent 병합
```

## 설치

```bash
bash setup.sh
# 대상 디렉토리 변경: CLAUDE_HOME=/path/to/.claude bash setup.sh
```

설치 후 Claude Code 를 재시작하면 settings.json 훅이 반영된다. node 필요(훅이 node 로 동작).

---

## 1. harness-wf — 단일 워커 워크플로우

5역할(Worker / Verifier / Healer / SR / watchdog) 협업 + 목적 기반 독립 검증. psmux 키입력주입 없이
**공식 프리미티브(Agent tool + SendMessage)** 로 동작한다. 메인 세션 = Supervisor.

**이 portable 버전의 특징** (button 원본 harness2-wf 대비):
- **단일 Worker** — standby 대기워커 풀(5개) 제거. opus 1m(~1M 컨텍스트)이라 단일 워커가 압축에
  도달하는 일 자체가 드물고, 압축은 native auto-compact 가, 프로세스 kill 복구는 handoff-key +
  execution-log backstop 이 담당한다.
- **전 작업 agent = opus 1m** — Worker / Verifier / Healer / SR 모두 `model: opus`.
  watchdog 만 `haiku`(토큰 측정 0 의 liveness 단순 루프라 모델 품질 무관 → 비용 절감).

**사용**: Claude Code 세션에서 `하네스wf` 또는 `harness` 트리거 → 메인이 `protocol.md` 를 읽고
`.harness/` scaffold → 역할 dispatch → 상태머신 루프. 상세는 `skills/harness-wf/protocol.md`.

전제: plan.md/요구사항 존재 + Phase/Sub-obj 분해 가능 + 3+ 파일 변경 규모.

---

## 2. ctx-precompact — 사전압축 훅

세션 토큰을 transcript 로 추산해 cap 임계 돌파 시 경고/압축을 유도한다. **registry 무의존**
(세션 식별 = stdin `session_id`, 토큰·모델 = stdin `transcript_path` tail).

| 단계 | 임계 (opus 기본 cap 500k) | 동작 |
|---|---|---|
| clear | < 24% (120k) | latch 리셋 |
| warn | ≥ 84% (420k) | 1회 경고 — 핵심 상태 저장 권유 + long-mode 안내 |
| critical | ≥ 96% (480k) | 매 tool call 압축 지시 — 저장 후 **세션이 스스로 /compact 입력** |

- **cap 기본 500k**, **long-mode 1회 750k**:
  ```bash
  bash ~/.claude/hooks/ctx-precompact/ctx-longmode.sh on      # 500k → 750k (warn 630k/critical 720k)
  bash ~/.claude/hooks/ctx-precompact/ctx-longmode.sh off     # 원복
  bash ~/.claude/hooks/ctx-precompact/ctx-longmode.sh status
  ```
  sonnet/haiku 세션은 물리 한계상 cap 180k(warn 130k / critical 160k) 자동 적용.

- **세션 자가 압축**: critical 도달 시 hook 은 *지시만* 주입하고, 세션이 `self-compact.sh` 를
  스스로 호출해 멀티플렉서(tmux/psmux)에 `/compact` 를 입력한다. 멀티플렉서가 없으면 안내만 하고
  `autoCompactEnabled` 네이티브 압축에 맡긴다 (hook 이 외부에서 강제 주입하지 않음).

- **연속 압축 방지**: PreCompact 훅이 cooldown marker 를 남겨, 압축 직후 stale 토큰값으로 critical 이
  재발화하는 것을 차단한다(새 응답 등장 시 자동 해제).

### subagent 안전
PostToolUse 훅은 stdin 의 `agent_id`/`agent_type` 가 있으면(=subagent 발) 주입을 skip 한다.
subagent 진행 중 /compact 는 결과를 고아화하므로 메인 세션에만 적용된다.

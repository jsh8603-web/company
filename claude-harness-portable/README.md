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
  skills/debate/             # in-process teammate 토론 (트리거: debate / 토론 / 반론)
    skill.md  protocol.md    # Steelman+Attack + Clean Room Judge
    challenger-constitution.md  judge-protocol.md
    lib/debate-bootstrap.sh  # transport = harness-wf/lib 재사용 (형제 경로 자동참조)
    templates/               # challenger/judge/disclaimer 템플릿
  skills/enhanced-planning-wf/  # 다관점 계획 검증 (트리거: 계획 wf / 강화 계획 / 상세 계획)
    skill.md                 # Pre-flight + Phase 0~4 + 조사 3-소스(웹/finance db/메모)
  hooks/ctx-precompact/      # 사전압축 훅 + 자가 재개
    ctx-precompact.js        # PostToolUse — cap 임계 경고 + 자가 압축 지시
    ctx-precompact-pre.js    # PreCompact — 핸드오프 게이트(미작성 시 압축 차단) + stale-token cooldown
    handoff-guide.md         # 핸드오프 작성 기준(6섹션/5필드) — 압축 전 무조건 작성 강제
    ctx-longmode.sh          # cap 500k ↔ 750k 토글 (1회)
    mux-lib.sh               # 멀티플렉서(tmux/psmux) transport 추상화 (공용)
    self-compact.sh          # 세션이 스스로 /compact 입력
    self-wake.sh             # 압축 후 idle 자동 재개 (harness 밖 단독 세션용)
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

### 핸드오프 강제 게이트 (압축 전 무조건 작성)
critical 도달 시 hook 이 "핸드오프 작성 → sentinel → self-compact" 를 지시하고, PreCompact 훅이
핸드오프 없는 /compact 를 `exit(2)` 로 **차단**한다 (수동 /compact + native auto-compact 모두). 이로써
압축이 일어나기 전에 핸드오프가 반드시 존재하게 된다.
- 작성 기준 (frontmatter + 6섹션 + 작업단위 5필드 + Write 전 자가체크 3) = `handoff-guide.md`. 핵심
  판정 = "다음 세션이 대화 로그 없이 이 파일 하나만으로 동등 재개 가능한가".
- 작성 위치: `~/.claude/.handoff-vault` 지정 시 `<볼트루트>/<프로젝트>/YYYYMMDD-HHMM-{topic}.md`
  (볼트 = **BGE RAG 색인 대상** → 의미 검색으로 과거 작업 조회), 미지정 시 `<프로젝트>/handoff/`.
  frontmatter `title`·요약 문단이 검색 품질을 좌우한다. 조회 3단 = RAG 의미검색(주)/ls 시간순/INDEX.
- 통과 조건: `<cwd>/.ctx-precompact/handoff-done` (내용 = 핸드오프 md 절대경로) 가 가리키는 md 가 실제
  존재 + 최소 400B. 통과 시 sentinel 소비 → 다음 압축 때 재작성 강제.
- 긴급 우회: `touch <cwd>/.ctx-precompact/handoff-skip` (1회용, 인계 포기).

---

## 3. self-wake — 압축 후 idle 자동 재개

harness wf **밖에서** 단독 세션에 ctx-precompact 훅만 쓸 때, auto-compact 직후 메인이 멈춰
쉬는 걸 방지한다. (harness wf 안에서는 watchdog + 네이티브 idle_notification 이 이 역할을 하므로
self-wake 는 불필요.)

```bash
bash ~/.claude/hooks/ctx-precompact/self-wake.sh start [interval_s=180] ["wake msg"]
bash ~/.claude/hooks/ctx-precompact/self-wake.sh stop      # 작업 끝나면 반드시 stop
bash ~/.claude/hooks/ctx-precompact/self-wake.sh status
```

- 멀티플렉서(tmux/psmux) pane 을 `interval` 마다 capture → **직전과 동일하면(=idle) wake 메시지 주입**.
  화면이 변하는 동안(작업 중)엔 주입하지 않는다.
- transport = `mux-lib.sh` (self-compact.sh 와 공유). **psmux 든 tmux 든 그 여부와 관계없이 동작**:
  psmux 실행파일은 `PSMUX_BIN` env → PATH → winget glob 으로 해결, session 명은 `PSMUX_SESSION` →
  `display-message` fallback. 실제 tmux 명령이 있으면 tmux 우선(psmux 가 설정하는 `TMUX` env 함정 회피).
- **작업 완료 시 `stop` 필수** — 안 그러면 idle 을 "압축 후 멈춤"으로 보고 계속 깨운다(STOP sentinel).

### 멀티플렉서 메모
- harness 의 teammate(에이전트팀)는 Agent tool + SendMessage(in-process)라 psmux 의존이 **아니다**.
  psmux 가 필요한 건 **메인 세션 pane 제어**(self-wake / self-compact)뿐이다.
- Windows psmux 는 실행파일이 PATH 에 없고 winget 절대경로이며 `TMUX` env 를 설정하므로, transport 는
  `mux-lib.sh` 가 이 둘을 모두 처리한다. 경로가 비표준이면 `PSMUX_BIN=/path/to/psmux.exe` 로 지정.

---

## 4. debate — in-process teammate 토론

멀티라운드 토론(Steelman+Attack 강제, Constitutional 평가 그리드, Clean Room Judge, 수렴 자동 감지).
Challenger/Judge = **opus**, watchdog = haiku. transport 는 harness-wf 와 **공유**(`harness-wf/lib` 재사용).

**트리거**: `debate` / `토론` / `반론` → 메인 Supervisor 가 `protocol.md` 를 읽고
`lib/debate-bootstrap.sh .debate <context_spec_file>` 로 scaffold → `TeamCreate(team_name="debate")` →
`Agent(Challenger, model=opus)` + `Agent(watchdog, model=haiku)` → 수렴 시 `Agent(Judge, model=opus)` on-demand.

- **psmux 의존 아님**: teammate = Agent tool + SendMessage(in-process). harness 와 동일하게 메인 세션만
  psmux 위에서 돈다.
- **harness-wf 필수 동반 설치**: debate 의 로그/agent 등록은 `harness-wf/lib/h2-log.sh`·`h2-agents.sh` 를
  재사용한다. `bootstrap` 이 형제 경로(`skills/harness-wf/lib`)를 자동 참조하므로 setup.sh 가 둘 다 설치하면 동작.

---

## 5. enhanced-planning-wf — 다관점 계획 검증

복잡한 계획을 **Pre-flight 범위 판정 + Phase 0~4** 로 검증해 허점을 사전 제거한다. Phase 0α 전략 검증은
`debate` 스킬에 위임하고, Phase 1 다관점 검증은 Agent Team(in-process)으로 수행한다.

**트리거**: `계획 wf` / `강화 계획` / `상세 계획` → 메인이 `skill.md` 를 읽고 Pre-flight 판정 → 해당
Phase 순차 실행 → Phase 4 에서 `progress.md` 생성 + 실행 엔진(harness) 라우팅.

**이 portable 버전의 특징** (button 원본 대비):
- **외부 인프라 의존 제거**: psmux·registry·remote Guard·`/ultraplan`·`model-switch-and-send.sh` 모두 제거.
  AskUserQuestion 을 그냥 쓰고(remote Guard 없음), Opus 세션에서 실행하면 된다.
- **조사 3-소스 추상화**: 외부 자문 스킬(search-engine·cross-verify) 대신 — 외부 웹(`WebSearch`/`WebFetch`
  네이티브) + **finance db(ODBC)** + **메모(회의록·메일)**. 판정 한 줄 = "데이터 있나/값?" → db /
  "왜 이렇게 정했나?" → 메모 / "외부 표준·신규?" → 웹. db 접속·메모 검색의 환경 고유 부분은 skill.md
  §9 의 설정 지점에 채운다.
- **실행 엔진 = harness 단일**: button 의 코딩wf·경량화 3-way 대신 harness + 직접 실행 2택으로 단순화.
- **도메인 무관(범용)**: 소프트웨어든 finance .py/excel 모델이든 그대로 적용. UI 가 없는 finance 작업은
  Phase 2(UI/UX)가 Pre-flight 에서 자동 스킵된다.

**동반 의존**: `harness-wf`(실행 엔진) + `debate`(Phase 0α). 셋 다 같은 패키지라 `setup.sh` 가 함께 설치한다.

---
tags: [type/protocol, domain/harness-wf, topic/harness]
date: 2026-05-19
status: active
---

# harness-wf — 메인 Supervisor 런타임 프로토콜 (SSOT)

> 트리거 `하네스wf` / `harness-wf` / `harness`. psmux 키입력주입 5역할 harness-wf 의 공식 프리미티브 실현형.
> 근거: plan-harness-wf-official-migration-2026-05-19.md (status=confirmed, 전 측정 PASS). 기존 harness-wf 병행 보존(삭제 금지).
> **메인 세션(Opus, SendMessage/Task/Agent 보유) = Supervisor.** subagent = teamless bg Agent(scope-disclaimer 강제).

## 1. .harness/ 디렉토리 (런타임 SSOT, 프로젝트 루트 하위)

```
.harness/
  phase-state.json      # 상태머신 단일값 (atomic, h2-state.sh)
  execution-log.jsonl   # append-only 이벤트 SSOT (content 는 항상 여기로, h2-log.sh)
  active-agents.json     # {agentId:{role,dispatch_ts,eta_s,done}} — watchdog 입력
  agents.json            # 역할별 영속 agentId (resume 관통용)
  patrol-config.json     # {sample_K:5, stale_s:180, sensitive_paths:[...]}
  verdicts/phase-N.json  # Verifier 판정 아카이브
  artifacts/phase-N/     # 산출물
  improvement-registry.md
```

## 2. 8단계 → 실현형 매핑

| psmux 원본 | harness |
|---|---|
| ①계획재구성 | 메인 직접 (plan.md Phase 분해) |
| ②목표계층 | goals.json + Task(blockedBy) — U6 회피 위해 전이는 execution-log 미러 |
| ③승인 | 사람 (변경 없음) |
| ④Agent 스폰 (단일 Worker) | 역할별 Agent dispatch → agentId 를 agents.json 영속. role-scoped disclaimer 부착. **dispatch 모델: Worker/Verifier/Healer/SR = `model: opus`(opus 1m, 단일 워커 최고 품질). watchdog = `model: sonnet`(liveness blocking 루프 자체는 LLM 0 이나, shutdown/REARM 핸드셰이크가 SendMessage/Bash tool 의 **실제 invoke** 신뢰성을 요구 → haiku 는 그걸 텍스트로 때워 미종료·phase 후 무감시 유발, 2026-06-28 실측으로 sonnet 승격). 메인 Supervisor=Opus 는 idle-by-default** |
| ⑤역할주입 | dispatch prompt 에 role 정의 + {{H2DIR}} + JSON 스키마 임베드 (send-keys 제거) |
| ⑥SR Pre-Review | SR Agent dispatch (MODE=C) → final JSON 회수 |
| ⑦Phase 루프 | §4 상태머신 |
| ⑧정리 | 각 agent "summarize and stop" + 메인 improvement-registry 행 추가 + 아카이브 |

## 3. 상태머신 S0~S11

S0 IDLE / S1 WORKER_DISPATCHED / S2 WORKER_DONE / S3 VERIFIER_DISPATCHED / S4 VERIFIER_DONE / S5a PASS / S5b FAIL / S6 HEALER_DISPATCHED / S7 HEALER_DONE / S8 REWORK_DISPATCHED(→S2) / S9 SR_INTERRUPT / S10 COMPLETE / S11 ABORT(Healer retry≥3 미수렴).

전이 = `h2-state.sh transition .harness <S> <NAME> <phase>` (atomic + execution-log 자동 미러).

## 4. 메인 turn-loop (이벤트 기반, IDLE = 0토큰)

원칙: **주기적 폴링·per-SO relay 금지**(ZERO-MAIN, 사용자 확정). ⭐ ZERO-MAIN 불변식 = wake 횟수 0 이 아니라 **주기 wake=0, 모든 wake 는 진짜 edge-event**(phase_complete/escalate/stuck + **워치독 자신의 죽음**도 정당한 edge). cap(transport 한도 회피)은 edge 가 아니므로 self-respawn 으로 흡수(category-error fix 2026-06-07). per-SO(commit→독립검증→verdict)는 Worker↔Verifier **자율 pull**(§5) — 메인 미개입. 메인은 *저빈도 결정점* 에만 깨어난다.

이벤트 = (a) **watchdog 완료 task-notification(주 — 확정 wake)**: phase_complete / escalate|blocked / silent-death(stuck) [cap 제외 — watchdog self-respawn] (b) **button dead-man's switch 주입**(워치독 `.self-wake-ts` mtime stale = 워치독 사망 → 외부 재스폰 지시, 워치독 독립 관찰자) (c) 사람 입력. ⛔ 수신 시 → **무조건 `h2-log.sh last` 1회 Read 분류**(일반 Team idle-무시 OVERRIDE, 주기폴링 금지). 상세 wake = **§7a O11/O12 + §6 필독** (SendMessage wake-ping 폐지, watchdog 완료알림이 유일 확정 wake).

```
phase 시작:
  teammate-spawn.sh spawn → TeamCreate + Worker/Verifier/watchdog 1배치 dispatch (단일 Worker, standby pool 없음)
  (Healer/SR = on-demand spawn-one). resume_baseline append → Worker·Verifier KICKOFF 자율 착수.
  메인 = IDLE (per-SO 미개입; watchdog dedup = .self-wake-ts <120s 면 재스폰 skip).
watchdog 완료알림 / button dead-man's switch 주입 수신 → h2-log.sh last → status 분기:
  stopped / 워치독사망(button) → watchdog 1개 재스폰(dedup) → IDLE   # cap 은 watchdog self-respawn = Supervisor 미수신
  phase_complete    → §12.5 Phase 완료 체크리스트(gate-review·SR·sufficiency) → O12 확인 → 다음 phase spawn 또는 S10
  escalate | stuck  → 해당 SO diff read·중재 / Verifier·Worker spawn-one 재가동 → watchdog 재스폰 → IDLE
교대: 메인 토큰 750k → 역할 agentId 요약 인계 / 900k → 메인 인수인계
종료: 전 phase PASS(O12 git_head 매칭) → S10 → ⑧
```

## 5. 통신 — 메인은 relay 가 아니다

content 는 **항상** `execution-log.jsonl`(atomic append, 측정: 동시 subagent+메인 무손상) 로 흐른다.

| 경로 | 메인 거침 | 메커니즘 (SendMessage 0 — 사용자 확정 2026-05-29: key 큐잉 = grinding agent 속도저하) |
|---|---|---|
| Worker→Verifier (검증대상 전달) | 0 | **git commit = ground truth**. Verifier 가 `h2-log.sh wait-commit` 로 신규 commit 폴 → 독립검증. (Worker ev:done 누락[신규-1]에 무영향.) SendMessage 없음. |
| Verifier→Worker (verdict 전달) | 0 | Worker 가 `h2-log.sh wait-since` 로 자기 commit 의 verdict(git_head 매칭) pull. push 없음 — Verifier 는 append 만. |
| Verifier→Healer / Healer→Verifier | 0 | Healer fix = commit → Verifier 의 wait-commit 루프가 자동 재픽업. |
| Worker 압축 (ctx) | 0 | native auto-compact(ctx 기준 자동). 단일 Worker — standby relay 없음. in-process teammate 는 /compact 로 죽지 않음(상태 보존, 2026-05-19 실측). 프로세스 kill 시만 handoff-key+git HEAD 로 새 Worker 복구. |
| Phase 완료 / silent-death / escalate | 메인 (저빈도 결정점) | **watchdog turn 종료 → task-notification** 으로 Supervisor 기상 (SendMessage 아님). |
| Healer→Sup(Design FAIL) / SR↔Sup / retry≥3·DEADLOCK | 메인 (저빈도 결정점) | watchdog escalate 경유 또는 phase 경계 결정 |

퀄리티(환각차단) = 독립 컨텍스트 *구조적* 분리 + **Verifier 가 self-test 가 아니라 commit 을 별 컨텍스트로 재실행** → 채널이 공유파일(git+log)이든 검증깊이 불변. ⛔ **per-SO 는 100% pull 자율**(Supervisor 미개입 = ZERO-MAIN); 메인은 phase 경계·escalate 같은 저빈도 결정점에서만 watchdog 완료알림으로 깨어난다.

## 6. patrol 2층

### ① Sonnet watchdog (blocking 루프라 LLM 호출 저빈도 — cap 주기 self-respawn turn + 이벤트시만, 비용 영향 경미)
**bash-only watchdog 폐기 사유 (설계 결함)**: detached bash `while:` 는 execution-log 에 STUCK 을 append 해도 **idle Supervisor 를 깨울 수단이 없음**(완료푸시 없음). 게다가 watchdog 가 필요한 "전부 멈춤" 상황이면 다른 완료푸시도 없어 STUCK 이 영영 미독 = 무용. → **agent** watchdog(sonnet) 으로 대체.

메커니즘 (단일 blocking 루프, 이벤트 시에만 완료): watchdog teammate(sonnet) 의 KICKOFF = `bash h2-watchdog.sh watch <h2dir> 60 540 360` **단 한 번**. 그 안에서 단일 blocking 루프가 (LLM 0): 매 60s `_scan_status`(one-shot) + `.self-wake-ts` heartbeat + `.watchdog-stop` 점검 →
- **alive** (within-phase 정상 commit/verdict 흐름) → 계속 루프(상주, Supervisor 안 깨움). ⛔ per-SO·FAIL 은 Worker↔Verifier 자율 pull 이라 watchdog 이 깨우지 **않는다**(Supervisor 중계 0 = ZERO-MAIN).
- **phase_complete / escalate|blocked / stuck(silent-death)** 감지 → `WATCHDOG_RESULT {status,...}` 출력 + **turn 종료** → task-notification 으로 Supervisor 기상 (SendMessage 아님). 이 3종만 Supervisor 개입 가치 있는 이벤트.
- **cap(540s, 10분 Bash 한도 회피)** 도달 → `status:"cap"`+next_since 출력 → ⭐ sonnet watchdog 이 **self-respawn**(next_since 로 watch 재호출, Supervisor 미경유 = ZERO-MAIN). cap 은 transport 한도 회피일 뿐 이벤트 아님(category-error fix). auto-compaction 이 watchdog turn 누적 흡수. 워치독이 진짜 죽으면(crash/압축실패) heartbeat 멈춤 → button dead-man's switch 가 커버.

Supervisor 동작 (watchdog 완료 task-notification 또는 button dead-man's switch 주입 수신 시): `h2-log.sh last <h2dir>` 1회 Read → status 분기 — `phase_complete` → §12.5 Phase 완료 체크리스트 / `escalate|stuck` → 해당 SO diff read·중재 또는 Verifier 재가동(teammate-spawn.sh spawn-one) / `stopped`(비-S10) → watchdog 재무장 [cap 은 self-respawn = Supervisor 미관여]. ⛔ **watchdog 재무장 = REARM SendMessage (재-spawn 아님, 2026-06-28 fix)**: phase_complete/escalate/stuck/stopped 로 watchdog 이 turn 종료하면 죽지 않고 **idle(available)** 로 남고 watch 가 `.self-wake-ts` 를 제거(stale)한다 → §12.5/escalate 처리 후 그 idle watchdog teammate 에게 `SendMessage(to=agents.json[watchdog], message="REARM <next_since=현재 ms>")` 1회 → watchdog 가 watch 루프 재진입. **dedup**: REARM 직전 `.self-wake-ts` 가 신선(<120s)이면 = 다른 watchdog 가 이미 alive → **skip**(중복 sprawl 차단, 발견3 fix). 단 이벤트 종료 시 watch 가 .self-wake-ts 를 지우므로 정상 경로는 stale=통과. **진짜 사망(crash → button 주입)** 만 새 Agent spawn(spawn PLAN watchdog 멤버). 종료(S10) 시 `touch .watchdog-stop` → watchdog 다음 폴(≤60s) 안에 stopped 종료(REARM 금지) + **dead-man's switch 해제** `bash ~/.claude/skills/harness-wf/lib/h2-registry.sh unregister "$(cd .harness && pwd)"` (button 감시 등록부에서 제거).

**heartbeat-return 폐기**: 주기 alive 리턴 = 재스폰 churn + Supervisor 컨텍스트 드리프트 원인. 근거: SR/phase 주기 트리거는 전부 역할 완료푸시에 올라탐(Pre=⑥명시 / T3=Verifier FAIL push / 주기창의=phase경계 PASS push / Post=전PASS push) → 독립 타이머 불필요, SR 누락 0. "완료푸시 전무 장기정지"만 유일 사각 = watchdog stall-감지가 커버.

부수효과: (1) idle Supervisor 깨우기 = stall 시 완료푸시로 성립(bash 결함 수정) (2) 정상시 Supervisor 주기 wake 0 = 컨텍스트 드리프트 없음 (3) 감시비용 lightweight-wf 등가(비교 #4 해소). `h2-watchdog.sh`: `check`=one-shot(watchdog 호출), `loop`=보조/디버그.

### ② code-sanity (메인, 토큰 ∝ 위험이벤트)
정상경로(PASS·저위험·retry 0) = **메인 코드 안 읽음**(독립 Verifier 신뢰, 매 Sub-obj 재독 = 토큰낭비 + 컨텍스트분리 파괴). 메인 read 6 트리거:

1. Verifier verdict=FAIL → 해당 diff read, Healer 라우팅/에스컬 판정
2. PASS 인데 `risk_level≥med` OR files_touched ∩ 민감경로 → 그 Sub-obj 만 타깃 read
3. retry-count++ → diff read, 수렴 vs thrash 판정
4. Phase 경계(배치 전량 PASS) → phase 합산 diff 1회 경량 리뷰 (per-Sub-obj 아님)
5. 1-in-K 랜덤 감사(K=patrol-config.sample_K=5, phase당 ≥1) → Verifier 체계적 맹점 탐지
6. SR T-event / DEADLOCK → 기존 결정점

민감경로 = Immutable 파일 + `auth|login|token|password|session|payment|billing|encrypt|migration|schema|.env|config`. 속도 무영향: read_N 은 Worker_{N+1}∥Verifier_N 병렬 뒤에 숨음(P5 측정) → wall 0, 토큰만 비용.

Verifier final JSON 스키마: `{verdict, risk_level, files_touched, suspicious, next_action_hint}`.

## 7. FAIL 에스컬레이션 9-step (원본 fail-escalation-flow 1:1)

```
1 Verifier 검증 → PASS → 2 다음 Sub-obj (chain 탈출)
3 Verifier FAIL(1회) → Healer dispatch + retry-count++  (phase-state.json 필드, atomic)
4 Healer 수정 + 재검증요청            (retry<3)
5 FAIL 반복 → step3 루프              (retry<3)
6 retry≥3 → Supervisor 중재(메인 직접, Opus 코드 read+판단)
7 중재 실패 → SR T3 Creative Window dispatch(MODE=T3)
8 SR 후 실패 → Supervisor 직접 수정
9 실패 → [DEADLOCK] 사람 에스컬레이션 + improvement-registry 행
```
예외: 명백 타이포/컴파일에러 = 메인 즉시 step8 허용(사람 승인 시) / "긴급" = 즉시 step9.

⛔ **FAIL 라우팅 격자 (발견2 fix — Gate MUST-FIX 의 Healer 우회 차단, 2026-05-29)**: FAIL 유형별 처리 주체를 명문화한다(경계 모호 → 전부 Supervisor-direct 흐름 차단):
- **코드결함 FAIL / Gate Review MUST-FIX** → **Healer 9-step 기본**(spawn-one). Healer fix = commit → Verifier wait-commit 루프가 자동 재verdict(독립 검증 보장).
- **박제-type FAIL**(progress.md 이연·문서 동기화 = Supervisor 전담 도메인) → Supervisor-direct.
- **1-3줄 trivial**(selector·threshold·타이포) → Supervisor-direct 허용. ⛔ 단 그 fix 도 **commit** 해야 Verifier 가 자동 재verdict(commit-SHA pull §5) → "Supervisor-direct = 독립 verdict 없음" 갭이 commit-pull 로 닫힘. \`by:supervisor-direct\` 기재.
- 그 외 코드 수정을 Supervisor-direct 로 처리 금지(빠르다는 이유로 Healer 9-step 우회 = 발견2 재발).

## 7a. on-demand 라우팅 · ZERO-MAIN 정의 · verdict 무결성 (2026-05-19 vaultvoice Phase4-7 첫 실전 교훈)

- **ZERO-MAIN 정의 명확화 (O7)**: ZERO-MAIN = "Supervisor 가 *주기 폴링·relay 타이핑*을 하지 않는다"이지 "tool-call 0"이 아니다. **R7 on-demand 라우팅(Verifier FAIL→Healer spawn/SendMessage, Healer ev:fix→Verifier 재검증 보장, SR 트리거, prior 검증) = 정당한 R7 작업** — ZERO-MAIN 위반 아님. 단 *자동화 가능분*은 자동화해 개입을 최소화한다(아래).
- **on-demand 재검증 자동화 (O3, 개입 최소화)**: Verifier 의 **wait-commit 루프가 Healer fix commit 도 자동 픽업**(Healer fix = 새 commit → 동일 루프가 재검증, ev:done·SendMessage 불요). Supervisor 의 Healer↔Verifier 수동 라우팅은 *자동 픽업 미동작 시 spawn-one backstop* 으로만.
- **on-demand 완료감지 = SSOT 우선 (O2)**: Healer/SR 완료 판정은 `execution-log ev:fix`/`ev:sr_review`(SSOT)로 한다. **git/fs 단독 추론으로 "완료·충족" declaration 금지** — git 은 mid-commit 부분상태일 수 있음. git 확인은 ev:fix 수신 후 *보조 검증*만(prior-verify E97).
- **resume 후 부재기간 verdict 전수 재감사 (O4, 핵심)**: Supervisor 가 압축/장기부재 후 resume 하면, **부재 구간에 생성된 Verifier verdict 를 전수 재감사**한다. 특히 거짓PASS-history Sub(과거 1회라도 override/FAILED 전과) 는 Supervisor 독립 1-shot 실행으로 재확인 의무. (근거: 2026-05-19 5.6 = 압축 중 Supervisor 부재 시 Verifier 가 "5.7 통합스크립트 흡수"=R5a 금지 시간이동 합리화로 거짓PASS. 워치독은 liveness 만 보므로 verdict-integrity 무방비.)
- **거짓 behavioral PASS 차단 (O1, R5a 강화)**: 런타임 기준 Sub-obj 의 게이트는 **자기 테스트 산출물에 behavioral 어서션이 코드화**돼야 PASS. "다른 Sub-obj/통합스크립트가 흡수·대신검증" = 금지 시간이동 합리화 → 자동 FAILED. 정적 `includes()`/grep 은 순수정적 Sub 한정. (role-verifier 금지어구 목록에 명문화됨.)
- **verdict 무결성 마커 (O10)**: 동일 Sub 의 verdict 가 override/재판정될 때, Supervisor verdict_override 또는 후속 verdict 에 `supersedes:<old_ts>` 기재 권고. SSOT 독자가 stale verdict 를 오인하지 않게(WM 랑데부 외 보조).
- **on-demand 스폰 SSOT (O6, E-1)**: Healer/SR R7 스폰 = `teammate-spawn.sh spawn-one <h2dir> <name> [team]` PLAN 경유만(raw Agent 금지). 함수 신설 시 (1)함수 (2)case 분기 (3)usage 헤더 (4)case 에러문 4점 동기 — verify() self-integrity 가 spawn_one·unblock_leader↔case 와이어 자동 체크.
- **⛔ 팀 전환 교착 해소 (O13, leader 단일팀 데드락 — 2026-05-28 Inv Phase0 실증)**: 다음 phase 팀 `TeamCreate` 가 `Already leading team <X>` 로 막히면 = 이전 phase 의 **완료모드 teammate(exit_code:0 출력 후)** 가 `shutdown_request` 에 SendMessage 를 invoke 하지 않아(idle "available" 만 반복) `TeamDelete` 가 `active member(s)` 로 실패 → leader 단일팀 제약상 새 팀 생성 불가 = 데드락(shutdown 3회 시도 무응답 실증). **해소(SSOT)**: (a) `bash ~/.claude/skills/harness-wf/lib/teammate-spawn.sh unblock-leader <X>` → 팀 메타(`~/.claude/teams/<X>`+`tasks/<X>`) **mv 백업**(⛔ `rm -rf` 은 home-guard 차단 → mv 만) (b) **`TeamDelete` tool 1회** → 파일이 없어진 상태라 active-member 체크를 우회하고 in-memory leader 를 정리(성공) (c) `TeamCreate <new>` → `teammate-spawn.sh spawn` PLAN 으로 Agent 스폰. **동일 안내 3중 배치**: spawn PLAN STEP-0 / skill.md 진입체크리스트 3 / 본 항목. (근본 결함=완료모드 teammate 재dispatch 불가 = O11/O12 wake 갭과 동근원 — promotion-log K 'harness-post-phase-added-task'.)
- **in-process teammate /compact 생존 (사실 정정)**: in-process teammate 는 메인(Supervisor) 대화 ctx 요약과 무관한 독립 agent 루프 — 세션 프로세스 생존 시 `/compact` 로 죽지 **않는다**(2026-05-19 실측: 압축후 커밋·verdict 생성). relay.backstop(handoff-key/git HEAD/execution-log)은 *프로세스 kill* 복구용으로 유지하되, "압축=teammate 사망" 전제로 작업 중단 금지.
- **⛔ S10 종료 = Verifier-PASS-terminal 불변식 (O12, critical — 2026-05-20, git_head 기반 강화 2026-05-29)**: **Healer `ev:fix`·Worker `ev:done` 는 구조적으로 절대 terminal 이 아니다.** S7 HEALER_DONE → S8 REWORK → S2 (Verifier 재검증) → `verdict=PASSED` **만이** S5a → S10 진입 자격. ⛔ **S10(COMPLETE)·phase 완료 진입 invariant (매 SO 확장, 발견4-E)**: 각 SO 의 최신 Verifier `verdict=PASSED` 의 **`git_head` 가 그 SO 의 최종 commit sha 와 일치** + ts 가 동일 Sub 의 모든 `Healer ev:fix`/`Worker done` ts 초과. 위반(후속 PASSED 부재 또는 git_head 불일치, 마지막 ev = Healer fix/Worker done) = **진입 금지** → Supervisor 가 `teammate-spawn.sh spawn-one` 으로 Verifier 재가동(SendMessage 아님 = spawn)해 그 SO 재검증 강제 후에만 §⑧. (근거: Healer/Worker 턴 종료 = 독립 재검증 없는 verdict-integrity 구멍. O4 resume 재감사의 종료시점 판.) commit-SHA pull(§5)이라 Verifier 가 모든 commit 을 자동 검증 → 정상시 시간순 **마지막 발화 = Verifier**. resume 재감사(O4)는 이 git_head 매칭으로 누락 SO 검출.
- **⛔ Supervisor wake 메커니즘 — watchdog 완료 task-notification (O11 재설계, 2026-05-29 사용자 확정: per-SO SendMessage 폐지)**: 구 O11 은 "dormant 메인 확정 wake = Verifier 의 SendMessage wake-ping" 이었으나, **사용자 확정 — SendMessage 는 grinding agent(Worker/Verifier) 를 큐잉으로 느리게 하므로(key 가 큐에 들어가면 재독·재해석 비용) per-SO wake 에 일절 쓰지 않는다**. 또한 "watchdog→Supervisor 중계"도 ZERO-MAIN 위반(사용자 확정). 재설계:
  - **per-SO = 100% pull 자율, Supervisor·SendMessage 0**: Worker↔Verifier 는 **git commit + execution-log 공유파일**로만 랑데부(§5). Verifier 는 verdict append 만 — **Supervisor 를 깨우지 않는다**(wake-ping 폐지). FAIL = Worker 가 verdict reason 보고 자가 rework(retry<3, Supervisor 미경유).
  - **dormant 메인 wake 유일 경로 = watchdog teammate 의 turn 종료 → task-notification**(완료 알림 = mid-turn idle_notification 과 달리 확정적). watchdog 은 within-phase alive 동안 안 깨우고, **phase_complete / escalate|blocked / silent-death(stuck)** 감지 시에만 종료해 메인을 깨운다(§6). 즉 메인은 **phase 경계·escalate 같은 저빈도 결정점에서만** 기상 — "review·gate 위해 어차피 깨야 하는" 지점(사용자 인지 2026-05-29).
  - **과거 "phase 시작마다 수동 nudge" 결함의 진짜 원인** (2026-05-29 Inv 로그 실측): ① Verifier.prompt 의 **KICKOFF 부재** → fresh-spawn Verifier 가 phase 시작마다 idle (within-phase 는 정상 연쇄). ② Worker 가 commit 후 `done`/`handoff_key` 로깅 누락+idle(신규-1) → ev:done 기반 검증 전멸. ③ relay 가 commit 경계(verdict 전)에 발동 → Standby 가 pending verdict SO 건너뜀(결함2). **fix(전부 SendMessage 없이)**: Verifier KICKOFF + commit-SHA 연속 pull / Worker commit↔done 원자결합 / relay 경계=verdict PASSED 후 (§teammate-spawn.sh).
  - **(Supervisor 행동)**: watchdog 완료알림 수신 = **무조건 `h2-log.sh last <h2dir>` 1회 Read** → status 분기(§6). 일반 Team "idle 무시" OVERRIDE. 주기폴링 금지(ZERO-MAIN O7 양립).
  - **(공통) Supervisor 행동**: watchdog 완료 task-notification 수신 = **무조건 `bash ~/.claude/skills/harness-wf/lib/h2-log.sh last <h2dir>` 1회 Read** → ev 분류(§6 status 분기). 일반 Team "idle 무시" 가이드 harness OVERRIDE. 알림 1건=Read 1회(주기폴링 금지=ZERO-MAIN O7 양립). silent-death(stuck) = wake-ping 도 못 남기고 죽은 진짜 정지 감지용(watchdog 의 log/commit mtime stale 동시 판정).

## 8. 컨텍스트 연속 (사용자 핵심 요구 — 측정 입증)

역할 subagent 는 chunk/Sub-obj 완료마다 **죽이지 않는다**. 동일 agentId(`agents.json`)로 `SendMessage(to=agentId)` resume → "resumed from transcript" 전체 복원 = 사고 연속(측정: Round1 SEED=8642 → Round2 재고지0 recalled=8642). phase 루프 전체를 동일 agentId 로 관통.

압축 임계(메인 토큰장부 단독 주도, task-notification.usage.total_tokens 가시; U5 자가감지 불가 보완): 임계 도달 *시에만* 해당 역할에 🔑 키블록 출력 지시 → execution-log.jsonl 기록:
```
{"role":"<R>","ev":"handoff_key","remaining":"...","last_done":"...","next_cmd":"...","verify":"...","ts":...}
```
메인이 키블록 읽어 신규 agentId dispatch prompt 에 주입(원본 worker-context-threshold-defense 1:1). 그 외엔 resume 으로 무한 누적.

## 9. SR (Strategic Reviewer)

- 자율 타이머 순찰 금지 — Supervisor 가 `teammate-spawn.sh spawn-one <h2dir> SR` 으로 트리거(MODE 동봉) 시에만. 리서치/렌즈 허용, ckpt/compact/psmux/Agent스폰 금지(SR.prompt disclaimer).
- MODE: **C=Pre-Review(harness.md 작성 직후 강제, §12.0-SR)** / T1~T4=Phase 이벤트(T3=FAIL Creative Window) / **A=Post-Review(매 phase 의무, §12.5-(4))** / **G=Gate-Review(phase 완료 시, 3-reviewer 커버 시 ev:sr_skip 명시 후 skip 가능)**.
- 보고 SSOT = `ev:sr_review` execution-log append(본문 텍스트 출력만 = 미수신, Phase 1 버그). SR=spawn-one 이라 Supervisor 가 그 자리서 회수(SendMessage 불요).
- 출력 final JSON: `{mode, type, sparks, ignite, score:{A1,A2,A3,A4}, proposal}`.

## 10. 비서(secretary) 의존 = 0

harness 런타임은 레거시 비서 호출·의존 일절 없음. (a)죽은세션부활=patrol 키블록 재dispatch 대체 (b)ctx-warn 주입=불필요+유해(부작용 벡터, 메인 단독장부+disclaimer 가 차단) (c)JSONL감사=직교. 비서는 레거시 psmux harness-wf 전용 유지(병행).

## 11. 종료 ⑧

전 phase PASS → S10 → 각 역할에 "summarize and stop" → improvement-registry.md 행 추가(5필드) → artifacts 아카이브 → active-agents 비우기 → ⛔ **watchdog 종료 (순서 필수)**: 먼저 `touch <h2dir>/.watchdog-stop` — watchdog 는 blocking watch 루프 중엔 shutdown_request SendMessage 를 **수신조차 못 한다**(2026-06-28 실측). 따라서 .watchdog-stop 이 **반드시 선행**해 watch 를 다음 폴 ≤60s 안에 `status:"stopped"` 로 끝내 idle 로 만든 **뒤에만** shutdown_request 가 처리된다. 그 후 각 역할 shutdown_request(disclaimer 의 shutdown 지시대로 SendMessage 응답하게) → **전 팀원 `teammate_terminated`/`shutdown_approved` 수신 후에만 TeamDelete**(idle teammate 는 shutdown 메시지 받아야 처리 — 미선행 시 active 잔존 cleanup 실패 실측). scope-disclaimer 가 자율 ckpt/compact 차단(측정 3회 연속 입증). ⛔ **S10 진입 전 O12 불변식 필수 확인**: 각 SO 최신 ev = `Verifier verdict=PASSED` 이고 그 `git_head` 가 SO 최종 commit sha 와 일치(동일 Sub Healer ev:fix/Worker done ts 초과)인가? 아니면(Healer fix/Worker done 이 마지막) S10 금지 — `teammate-spawn.sh spawn-one` 으로 Verifier 재가동해 재검증 강제 후 진입. 미통과 = 종료 누락 아니라 **미완료 상태 종료**(verdict-integrity 위반).

## 12. Supervisor 충실 프로토콜 (harness-wf supervisor-* 무누락 포팅)

**12.0 진입 게이트 ⓪ (entry-gate)**: 트리거 즉시 protocol.md Read → 5전제: (1)Agent tool 가능 (2)plan.md/요구사항 존재 (3).env 유효 (4)규칙 사전리뷰(plan ↔ harness.md §3~7 대조, 모순 식별 사용자 보고) (5).harness/improvement-registry.md 확인. + progress.md 존재(없으면 plan 기반 생성), 각 step model:X 또는 wf:Y 정확히 1. 사용자 질문 금지(Supervisor=Opus 자가보완), 심각 불확실만 확인.
⛔ **12.0-SR SR Pre-Review 강제 게이트 (발견1 fix — "harness.md 생성 시 SR 발동"=사용자 원 요청)**: harness.md 작성(h2-bootstrap) **직후, phase 루프(Worker dispatch) 진입 전**, SR mode C 를 1회 spawn-one 한다: `bash teammate-spawn.sh spawn-one <h2dir> SR <team>` (MODE=C 동봉) → 스폰 직후 `bash teammate-spawn.sh ... ` 없이 **`h2-agents.sh register <h2dir> <agentId> SR 0`** 로 agentId 영속(이후 SendMessage 재사용 앵커). SR 의 `ev:sr_review(mode=C)` append 회수 + directive §평가(ACCEPT/논의/DROP) 후에만 phase 루프 진입. ⛔ **`ev:sr_review(C)` 부재 시 Worker dispatch 금지**(묵시 skip 차단 — Phase 1 만 SR 받고 2~6 누락한 drift 의 진입점 봉쇄). Supervisor 가 harness.md 작성 직후 이미 깨어있는 지점이라 추가 wake 불요.
⛔ **SR 재사용 (SR churn 차단 — 2026-06-28 fix, skill.md §진입 6 정합)**: SR 은 **첫 트리거(위 mode C)에서만 spawn-one**. 이후 모든 트리거(T1~T4 / Post A / Gate G)는 **새 spawn-one 으로 SR 을 재생성하지 않는다**(= 직전 SR kill 금지). 살아있는 idle SR teammate 에게 `SendMessage(to=agents.json[SR], message="MODE=<C|T1|T2|T3|T4|A|G> ...")` 1회로 재트리거한다(SR.prompt PERSIST 가 그 MODE 를 받아 재리뷰 후 다시 idle). agents.json 에 SR agentId 부재(첫 회)일 때만 spawn-one. SR 의 fresh 컨텍스트보다 phase 간 리뷰 맥락 누적이 낫다(사용자 "SR 자꾸 죽이지 마라" 2026-06-28).

**12.1 Sub-obj 4원칙 (checklist-4)**: ①관찰가능성(Verifier Read/Bash 확인가능 — "깔끔"→"50줄이하") ②원자성(단일동작 PASS/FAIL — "전체동작"→"/health 200") ③커버리지(전부PASS=Final Obj?) ④독립성(타Sub 무관 검증, 의존시 순서명시).

**12.2 이벤트 상태머신 (event-state-machine)**: IDLE→이벤트→MONITOR/CHECK/RESPOND/EVALUATE/ORCHESTRATE→IDLE. turn-based=IDLE 0토큰(주기 폴링 금지). Phase완료를 단순 RESPOND 처리해 SR Post 누락 금지.

**12.3 에스컬레이션 체인 (escalation-chain, 4단계 retry-limit 3)**: ①Worker/Healer 자동재시도(retry<3) →②Supervisor 중재(retry≥3) →③Supervisor 직접수정 →④[DEADLOCK] 인간+improvement-registry. ⑦ 사이에 SR T3 Creative Window(②실패 후). 건너뛰기 금지(명백 타이포/사용자 긴급만 예외).

**12.4 목표관리 (goal-management)**: Phase완료 시 충분성 2방향(↑세부→Phase Final / ↓Phase Final→Pipeline Goal) + 5기준(사용자가치/커버리지갭/통합정합/부작용/범위드리프트). 세부수정 자율, Phase Final 이상 사용자 승인.

**12.5 Phase 완료 체크리스트 8항목 (phase-completion-checklist)**: watchdog 의 `phase_complete` 완료알림으로 Supervisor 가 기상하면(§6): (1)Healer 완료대기(미가동=정상) (2)파일소유권 정리 (3)**Phase Gate Review = security/quality/performance reviewer Agent 3 병렬 dispatch(model:sonnet, scope-disclaimer) + 요약 ev:gate_review 기록 + SR Gate-Review(mode G) — ⛔ 3-reviewer 가 G1~G4 커버 판단 시 SR mode G skip 허용하되 `ev:sr_skip {mode:"G",reason}` 명시 기록(묵시 skip 금지=발견1 drift). SR 트리거 = **SendMessage(to=agents.json[SR], MODE=G)** 재사용(spawn-one 재생성 금지=SR churn 차단, §12.0-SR). MUST-FIX 라우팅 = §7 격자(코드결함→Healer 9-step) + 전체 PASS 후 전환** (4)**SR Post-Review(mode A) = 매 phase 의무**(살아있는 SR 에 **SendMessage MODE=A** 재트리거 — 첫 회 외 spawn-one 금지, KNOWLEDGE/PATTERN→promotion-log directive). ⛔ skip 불가 — phase_snapshot/S10 전 `ev:sr_review(A)` 존재 invariant(부재 시 진입 금지). (5)watchdog 재무장 = REARM SendMessage(이벤트 종료 시 .self-wake-ts stale→dedup 통과, §6)→IDLE (6)SR 지시서 §평가 ACCEPT/논의/DROP (7)harness.md Sufficiency Check 기입 + Sub-obj 체크박스 [x] (8)ev:phase_snapshot 기록.

**12.6 워치독 6판단 (watchdog-role)**: 완료푸시/watchdog STUCK 수신 시: (1)execution-log 마지막 상태 Read (2)판단필요(STUCK 재dispatch / 동일실패 2회 에스컬 / SR Ignite 가중평가) (3)기록의무 감시(Worker done 누락?) (4)진행정체 (5)🔑 handoff_key 감지→다음명령 직접실행 (6)규칙 자율개선(동일문제 2회→protocol.md 직접수정). ev:watchdog 기록(미실행 시 ev:watchdog_skip).

**12.7 longlived-mode**: 다중 Phase + 압축경계 다수 예상 시: guide 역할 = progress ckpt + agents.json(agentId 영속) + execution-log wf_header + plan lazy. resume = progress ckpt + digest + agents.json 으로 동일수준 재개.

**12.8 role-prompt SSOT = teammate-spawn.sh build() (drift 정정 2026-05-29)**: ⛔ **dispatch prompt 의 실제 SSOT = `lib/teammate-spawn.sh` 의 `build()` inline heredoc** (Worker/Standby/Verifier/Watchdog/Healer/SR.prompt 전부 여기서 생성 → `$H2/dispatch/*.prompt`). `templates/role-*.txt` 는 **현재 어디서도 read 안 되는 orphan**(레거시 — 역할 프롬프트 수정 시 손대지 말 것, teammate-spawn.sh 만 수정해야 런타임 반영). h2-dispatch.sh·disclaimer-*.txt·haiku-watchdog.txt 도 동일 orphan. Worker.prompt 만 harness.md Sub-obj 배정 + taskspec 참조, Verifier/Healer/SR 은 prompt 자체완결. (과거 본 항목이 "role-*.txt = SSOT" 로 서술해 명세가 orphan 파일을 가리키는 drift 유발 → 정정.)

**12.9 보고 템플릿 (report-templates)**: Heartbeat = ev 로만(이상 시만 사용자 출력). Phase 완료보고 = 사용자 출력(결과/산출물/SR 요약). §9 종료분석 = 에이전트 4축 ★ + 지표표.

**12.10 추가-task = Supervisor 직접 (2026-05-28 Inv 실증, 사용자 확정)**: phase 초기 dispatch 묶음(resume_baseline+KICKOFF)에 **없던** 추가 SO(Gate Review 보강·hotfix·phase 완료 후 발견분)는 teammate 중계 대신 **Supervisor 가 직접 수정 + 직접 검증**(execution-log 에 `ev:verdict by:supervisor-direct` 기록). 근거 3중 마찰: ① teammate 가 완료출력(exit_code:0) 후 종료모드 → SendMessage 재기동 불응(Standby 승계 강제) ② 승계 Standby 는 KICKOFF 미경유라 ev:done 규약(role 필드/sub 키) 반복 누락 → Verifier wait-since 매칭 실패 → 매번 Supervisor done 보정 ③ Verifier 도 완료모드라 추가분 자동 폴링 미지속 → 매 SO 수동 깨움. = 중계 비용(보정·수동깨움 N회) > 직접 작업. ⛔ **단, phase 초기 묶음 SO 는 teammate 자율 연쇄 유지**(SO-1~5 = Supervisor 개입 0·FAIL 0 입증) — 본 원칙은 "초기 묶음 외 추가분" 한정. 가능하면 보강을 phase 시작 전 taskspec 에 선반영해 추가분 자체를 줄인다.

## 13. execution-log.jsonl ev 스키마 (harness-wf 이모지 마커 → JSON 정규화, 무손실)

| harness-wf 마커 | harness ev | 쓰는 역할 |
|---|---|---|
| `<!-- WF header -->` | `ev:wf_header {wf,phase,started}` | Supervisor(bootstrap) |
| 🚀 Phase 시작 | `ev:phase_start {phase}` | Supervisor |
| 🔍 Watchdog Check | `ev:watchdog {checks}` / `ev:watchdog_skip {reason}` | Supervisor |
| (Worker 완료) | `ev:done {sub,git_head}` | Worker (보조 신호; Verifier 는 commit 으로 픽업) |
| (Phase 완료) | `ev:phase_complete {phase}` | Worker (마지막 SO PASS 후 → watchdog 가 Supervisor 깨움) |
| 📐 Design Decision | `ev:design_decision {action,target,choice,alt,rationale}` | Worker |
| 🔑 인수인계 키 | `ev:handoff_key {completed,next,git_head,pending_verdict?}` | Worker (프로세스 kill 복구 앵커, standby 인계 아님) |
| 📋 Verifier 판정 | `ev:verdict {scope,sub,git_head,verdict(PASSED\|PARTIAL_PASS\|FAILED),risk_level,passed,failed,reason}` | Verifier (**git_head = 검증한 commit sha, O12 매칭 키**) |
| 💡 Fix 패턴 | `ev:fix_pattern {fix_type,pattern,retry,...}` | Healer |
| (에스컬/블록) | `ev:escalate {reason,retry,sub}` / `ev:blocked {reason,sub}` | Worker/Healer (watchdog 가 감지→Supervisor) |
| 🎯 SR Pre/Post | `ev:sr_review {mode,lenses,typeA,typeB,sparks,ignite,score}` | SR |
| ⚡ 중재 | `ev:mediation {decision}` | Supervisor |
| 🔧 Rule Fix | `ev:rule_fix {file,change}` | Supervisor |
| 📸 Phase 스냅샷 | `ev:phase_snapshot {from,to,summary}` | Supervisor |
| Gate Review 요약 | `ev:gate_review {security,quality,performance,sr_g}` | Supervisor |
| 상태 전이 | `ev:transition->S{n}` | Supervisor(h2-state) |

§9 종료분석 카운트 = 이 ev 들 grep. 마커 누락 = 분석 유실 → ev 필수.

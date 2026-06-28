---
tags: [type/protocol, domain/collaboration, topic/debate]
date: 2026-05-20
status: active
---

# debate — 메인 Supervisor 런타임 프로토콜 (SSOT)

> 트리거 `debate` / `토론` / `반론`. psmux send-keys+ACK파일 멀티라운드 토론의 in-process teammate 실현형.
> 근거: debate(psmux) 1:1 transport 전환 — lightweight2-wf/harness-wf 검증 패턴 준용. 기존 debate(psmux)·harness-wf·lightweight2-wf 병행 보존(삭제 금지).
> **메인 세션(Opus, TeamCreate/SendMessage/Agent 보유) = Supervisor.** teammate = in-process(TeamCreate "debate" + `Agent(team_name,name)`, `run_in_background` 금지, scope-disclaimer 강제 — harness-wf transport 정합). Challenger 상주, Judge = Step4 on-demand(fresh = 구조적 Clean Room).

## DA 1:1 대조 (원본 debate → 본 protocol §)

| 원본 DA | 본 protocol § |
|---|---|
| debate-roi-gate | §⓪ ROI 게이트 |
| debate-full-flow | §1 전체 흐름 |
| debate-step1-spawn | §2 Challenger dispatch (스폰 등가) |
| debate-step2-round | §3 라운드 (ev 랑데부) |
| debate-step3-convergence | §4 수렴 판정 |
| debate-step4-judge | §5 Clean Room Judge (on-demand) |
| debate-step5-collect | §6 회수 + 종료 |
| (신규) | §7 Supervisor wake 메커니즘 (O11 동형) |

## ⓪. ROI 게이트 (debate-roi-gate)

Debate = Opus 멀티세션·멀티라운드 고비용. 진입 직전 Supervisor 자가 ROI 판정:
- **적합**: 아키텍처/설계 결정(되돌리기 어려움)·복잡 트레이드오프·고불확실성·고위험(보안/데이터/프로덕션).
- **부적합**: 구현 세부(함수명/파일구조/스타일)·검증된 패턴 적용·단순 버그/리팩토링·실험으로 빠른 검증 가능.
- 부적합 → 직접 구현 권장 1줄 보고 후 종료(스폰 금지). 적합 → §1.

## 1. 전체 흐름 (debate-full-flow)

```
[⓪] ROI 게이트 → [§2] TeamCreate "debate" + Challenger dispatch + 도메인 주입 (ev:domain_ack)
                       │
                 [§3] 라운드 (Steelman → Score(Sup) → Attack → Rebuttal+Keypoints) — ev 랑데부
                       │
                 [§4] 수렴? → NO → [§3] (max 4라운드, R1-2 압축)
                       │YES
                 [§5] Clean Room Judge on-demand spawn (fresh teammate) → ev:verdict_done
                       │
                 [§6] verdict 회수 + 보고 + 팀 종료(shutdown_request)
```

⛔ 각 단계 게이트 = **execution-log.jsonl ev** (구 acks.txt grep + send-keys 폐기). Supervisor 무폴링, teammate idle_notification→log Read(§7).

## 2. Challenger dispatch (debate-step1-spawn 등가)

psmux `spawn-session.sh debate` + `psmux_send_message` 도메인주입 + acks.txt grep → 공식 프리미티브:
- `bash ~/.claude/skills/debate/lib/debate-bootstrap.sh .debate <context_spec>` → scaffold + dispatch prompt(Challenger) + manifest(transport=teammate-in-process) 원샷.
- ⛔ **in-process teammate 불변식 (절대 — harness-wf transport 정합)**: **(STEP-1)** `TeamCreate` **1회** → **(STEP-2)** `Agent` (한 메시지). **`run_in_background` 부여 절대 금지**. `name`/`team_name` **필수**. Agent.prompt = 멤버 prompt 전문 VERBATIM(포인터/Read-지시 주입 금지). raw 즉흥 Agent 금지. **정확한 호출 시퀀스 (그대로 복사):**

```
# STEP-1 (1회만)
TeamCreate(team_name="debate", agent_type="supervisor", description="debate <topic> 토론 team")

# STEP-2 (한 메시지 병렬, prompt = 각 파일 전문 VERBATIM)
Agent(team_name="debate", name="Challenger", model="opus",  subagent_type="general-purpose", prompt=<.debate/dispatch/Challenger.prompt 전문>)
Agent(team_name="debate", name="watchdog",   model="sonnet", subagent_type="general-purpose", prompt=<.debate/dispatch/watchdog.prompt 전문>)
# ⛔ run_in_background 인자 자체를 넣지 않는다 (구 teamless 폐기 경로)

# STEP-3 Challenger agentId 등록 (watchdog = silent-death backstop, active-agents 미등록 — monitor=monitee 아님)
bash ~/.claude/skills/harness-wf/lib/h2-agents.sh register .debate "<Challenger agentId>" Challenger 1800
```

- **도메인 독립 이해 강제 (편향 차단 핵심)**: Challenger 는 *제안(brief)을 보기 전에* `debate-context.md` + 나열 파일을 독립적으로 Read 해 도메인을 자기 언어로 이해한 뒤 **`ev:domain_ack`** append. Supervisor 는 ev:domain_ack 수신 전 §3 절대 진입 금지(제안 프레이밍으로 도메인 읽는 편향 방지 = debate 핵심 가치).
- **name resume = first-class**: 라운드 연쇄·재개 모두 `SendMessage(to="Challenger")` **이름으로만(agentId 금지)** — in-process teammate 동일 transcript 보존(이전 라운드 Steelman/Attack 논지 기억).
- ⛔ psmux/spawn-session.sh/acks.txt/self-wake 일절 미사용.

## 3. 라운드 (debate-step2-round 등가 — ev 랑데부)

한 라운드 = **Steelman → Score(Supervisor) → Attack → Rebuttal+Keypoints(Supervisor)**. 순서 우회 절대 불가.

| 단계 | 발화 | 산출물(파일 SSOT) | 게이트 ev | Supervisor 행동 |
|---|---|---|---|---|
| Steelman | Challenger | `debate-R{n}-steelman.md` | `ev:steelman_done {round}` | brief(`debate-brief.md`) 작성 후 `SendMessage(to="Challenger")` "Steelman R{n}" |
| Score | **Supervisor** | `debate-R{n}-steelman-score.md` | (ev 없음, Supervisor 직접) | 항목별 PASS/WEAK/FAIL(단일 종합점수 통과 금지). FAIL 1+ → 해당 항목만 재Steelman 1회(`SendMessage`). FAIL 0 → Attack 진행(WEAK 항목 첨부) |
| Attack | Challenger | `debate-R{n}-attack.md` | `ev:attack_done {round}` | `SendMessage(to="Challenger")` "Attack R{n}: score 반영 + Evaluation Grid(PASS/WARN/FAIL+Evidence 인용) + 구체 대안 1+ 필수". 그리드 없으면 재작성 1회 |
| Rebuttal+Keypoints | **Supervisor** | `debate-keypoints.md` 갱신 | (Supervisor 직접) | Attack 에 반론 + keypoints 누적 → §4 수렴 판정 |

⛔ **이전 파일을 현재 라운드 결과로 간주 금지**: 게이트 = `ev:{steelman,attack}_done` 의 `round` 필드가 **현재 라운드 N 과 일치**해야 유효(stale 파일 재매칭 차단 — harness wait-since watermark 동형). Score 파일 없으면 Attack 요청 금지. 그리드 없는 Attack 수락 금지.

## 4. 수렴 판정 (debate-step3-convergence)

매 라운드 Rebuttal+Keypoints 후 3조건 **AND** 점검:

| 수렴 조건 | 설명 |
|---|---|
| 신규 논점 0개 | 이번 라운드 새 주장 미등장 |
| 미해결 = 전부 "데이터/실험 필요" | 토론으로 해결 불가 유형만 잔존 |
| 핵심 충돌 해소 | 양측 합의 또는 명확 분기점 식별 완료 |

- 3조건 충족 → §5 Judge. 1+ 미충족 → §3 다음 라운드.
- **max 4라운드 강제 수렴**(무한루프 방지). 4라운드 진입 시 R1-2 를 `debate-summary-R1R2.md` 로 압축(Challenger 컨텍스트·Supervisor 양쪽 절감).
- 신규 논점이 구현 세부 수준 → Supervisor 재량 Judge 전환 가능(근거 keypoints.md 기록).

## 5. Clean Room Judge (debate-step4-judge — on-demand fresh teammate)

수렴/4라운드 도달 → Judge **on-demand spawn**(harness Healer/SR on-demand 동형, 기존 team join):

```
# 기존 debate 팀에 join (TeamCreate 재호출 금지 — §2 에서 생성됨)
Agent(team_name="debate", name="Judge", model="opus", subagent_type="general-purpose", prompt=<.debate/dispatch/Judge.prompt 전문>)
```

- **구조적 Clean Room (psmux 대비 강화)**: Judge = **신규 teammate 컨텍스트**(Challenger transcript 완전 격리 — 별 agent 루프). psmux 별세션보다 강한 격리(공유 pane/스크롤백 0). A/B 익명성 목적 = 완전익명 아닌 *논점 출처 무관 사실·논리·증거 평가 강제* — judge-brief 에 A/B 배정 + judge-protocol.md 풀 템플릿 그대로 포함(verdict 간소화 금지: Argument Decomposition/Per-Claim/Conflict Resolution/Synthesis/Traceability Map/Action Items 필수).
- judge-brief(`debate-judge-brief.md`) 필수: Judge 역할 / 심판기준(가중치) / context·keypoints 경로 / 자체확인 포인트 / 양측 원문 A·B 경로 / verdict 템플릿 전문([judge-protocol.md](./judge-protocol.md)).
- Judge 작업: context Read → keypoints Read → 자체확인 → 양측원문 A/B Read → 분해 → Per-Claim 평가 → Conflict Resolution → Synthesis → `debate-verdict.md` 저장 → **`ev:verdict_done`**.

## 6. 회수 + 종료 (debate-step5-collect)

- `ev:verdict_done` 수신(§7 wake) → `debate-verdict.md` Read → 사용자 보고(수렴요약/판정/Action Items).
- enhanced-planning-wf Phase 0α 호출이면 verdict 를 plan.md 반영 제안.
- 종료: ⓐ **먼저 `touch .debate/.watchdog-stop`**(F3 fix — watchdog 블로킹 loop 다음 폴 ≤PL초 안에 break) → ⓑ `SendMessage(to="Challenger", {type:"shutdown_request"})` + `SendMessage(to="watchdog", {type:"shutdown_request"})` + (Judge 스폰됐으면) `SendMessage(to="Judge", ...)` → ⓒ 전 팀원 `teammate_terminated`/`shutdown_approved` 수신 후 TeamDelete(idle teammate 는 SendMessage 받아야 shutdown 처리 — 미선행 시 active 잔존 cleanup 실패 실측). `.debate/` 정리 질문. ⛔ `pkill`/psmux 일절 불요.

## 7. ⛔ Supervisor wake 메커니즘 — wake-ping 다중보장 (lw2/harness O11 정정판 동형, critical)

**실측 결함 (lw2 E2E)**: dormant 메인 Supervisor 는 teammate `idle_notification` 으로 **신뢰성 있게 안 깨어난다**(자율 완주 시 첫 완료 누락). "못 깨어났는데 깨어나면 ev 읽어라" = **순환 모순**. dormant 메인 확정 wake = agent 가 team-lead 에게 명시적 `SendMessage`.

⛔ **해소 = teammate wake-ping 다중보장 (debate = Challenger 상주 / Judge 가 구조적 최종 발화자 = harness Verifier 동형)**:
1. **(층1) Challenger 의무 wake-ping**: gating ev(`domain_ack` / `steelman_done` / `attack_done` / `relay`) append **직후** `SendMessage(to="Supervisor", message="ev:<종류> round=<n> — 확인 요망")` 실제 invoke. 이게 Supervisor 가 Score/Rebuttal/다음라운드 진행하는 주(主) 확정 경로.
2. **(층1') Judge 의무 wake-ping (최종)**: Judge 는 `ev:verdict_done` append **직후** **반드시** `SendMessage(to="Supervisor", message="ev:verdict_done — verdict 완료, 회수 요망")` 실제 invoke. Judge = 토론의 **구조적 마지막 발화자**(harness O12 Verifier 동형) → 이 wake-ping 미발신 = Supervisor 영영 안 깨어남 = §6 회수 누락 = "끝났는데 알림 못 받음" 그 자체.
3. **(층2) disclaimer/role 강제**: role-challenger-debate / role-judge-debate / disclaimer-strict-debate 에 위 wake-ping 의무 명문(누락 시 작업 무효).
4. **(층3) watchdog backstop 복원**: bootstrap 이 Sonnet watchdog teammate 1개 동반 dispatch(harness haiku-watchdog.txt 재사용). 역할 = wake-ping 도 못 남기고 죽은 *진짜 silent-death* 만 staleness 감지→Supervisor 깨움. 1차 wake 아님(보조). (이전 초안의 "watchdog 없음" = 결함, 사용자 적발 → 복원.)
5. **(공통) Supervisor 행동**: wake-ping(주) | idle_notification(best-effort) | watchdog stuck 수신 = **무조건 `bash ~/.claude/skills/harness-wf/lib/h2-log.sh last .debate` 1회 Read** → ev 분류 → §3 표·§5·§6. idle 1건=Read 1회(주기폴링 금지). 일반 Team idle-무시 가이드 OVERRIDE.

## 8. ev 스키마

| ev | 의미 | 쓰는 역할 |
|---|---|---|
| `ev:wf_header {wf:"debate",topic,started}` | bootstrap 헤더 | Supervisor |
| `ev:domain_ack {note}` | 도메인 독립 이해 완료 (제안 보기 전) | Challenger |
| `ev:steelman_done {round}` | Steelman 파일 작성 완료 | Challenger |
| `ev:attack_done {round}` | Attack 파일 작성 완료 | Challenger |
| `ev:rebuttal {round,converged:bool}` | Supervisor 반론+수렴판정 | Supervisor |
| `ev:verdict_done` | Judge verdict 파일 완료 | Judge |
| `ev:relay {last_round,reason}` | 압축 self-relay(긴 토론 시) | Challenger |
| `ev:review {verdict,note}` | Supervisor 최종 회수 | Supervisor |

⛔ 완료·진행 판정 = execution-log ev 가 SSOT(git/fs 단독추론 금지). ev `round` 필드 = stale 재매칭 차단 watermark.

## 9. 압축 관리 (긴 토론 — harness turn-카운터 벤치마크, 경량)

debate 는 보통 4라운드 내 단명이라 lw2/harness 만큼 압축 빈발 안 함. 단 도메인 리서치+4라운드가 길어질 때 Challenger:
- CTX-INVISIBLE — ctx 추정 금지. `turn >= 50 + jitter`(bootstrap 산출) AND 라운드 경계 → `ev:relay {last_round,reason}` append → **직후 `SendMessage(to="Supervisor", "ev:relay — 압축 임박, Challenger 재dispatch 요망")` 실제 invoke**(§7 층1 wake-ping) → idle. Supervisor 가 wake-ping 으로 깨어나 동일 `Agent(team_name="debate", name="Challenger", ...)` 재dispatch(새 Challenger 가 debate-keypoints.md + 직전 라운드 파일 흡수해 연쇄, 이전 transcript 불요). Standby 풀 없음 = just-in-time respawn.
- 라운드 산출물(steelman/attack/keypoints .md) 자체가 압축 복구 앵커 — handoff_key 별도 불요(파일 SSOT).

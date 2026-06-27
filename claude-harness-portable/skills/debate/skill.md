---
tags: [type/skill, domain/collaboration, topic/debate, load/trigger]
name: debate — in-process teammate 멀티라운드 토론 (Steelman + Clean Room Judge)
description: |
  psmux send-keys+ACK파일 debate 의 in-process teammate 실현형. Steelman+Attack 강제,
  Constitutional 평가 그리드, Clean Room Judge(구조적 격리), 수렴 자동 감지,
  Verifier/Judge-주체 wake-ping 다중보장(dormant 메인 확정 wake). 기존 debate(psmux)·harness-wf·lightweight2-wf 병행 보존.
  트리거: "debate", "토론", "반론", "토론해봐"
date: 2026-05-20
status: active
---

# debate — 공식 프리미티브 토론 워크플로우 (psmux send-keys 제거)

**Kind**: scenario

**Trigger**:
- Keywords: `debate`, `토론`, `반론`, `토론해봐`, `다른 AI한테 물어봐2`
- Context: 설계/아키텍처 결정·고위험·복잡 트레이드오프를 멀티라운드 검증하되 psmux 키입력주입을 안 쓰려 할 때

**When**: 사용자가 위 키워드로 진입 지시 시 (기존 `debate`/`토론해봐` = psmux 원본 — 병행 보존, 혼동 금지)

**If**: §⓪ ROI 게이트 적합(아키텍처/되돌리기 어려운 선택·복잡 트레이드오프·고불확실·고위험). 부적합 = 직접 구현 권장 후 종료.

**Then**: 메인 세션(Opus) = Supervisor 로서 [protocol.md](./protocol.md) ⓪~7 단계 수행. 역할 = TeamCreate "debate" 후 **in-process teammate Challenger(opus, 상주)** + **Haiku watchdog** + **Judge(opus, Step4 on-demand fresh=구조적 Clean Room)** — `Agent(team_name="debate", name=...)`, `run_in_background` 금지, name resume 관통.

**Because**: send-keys 타이핑+ACK파일 grep+spawn-session.sh 제거. 통신 = `execution-log.jsonl` ev SSOT + **gating ev 마다 teammate→Supervisor wake-ping SendMessage**(dormant 메인은 idle_notification 으로 신뢰성 있게 안 깨어남 — lw2 E2E 실측, 순환모순 정정). Judge = 구조적 마지막 발화자 → 최종 wake-ping 주체(harness Verifier/O12 동형). Clean Room = Judge 별 teammate 컨텍스트(psmux 별세션보다 강한 격리). Supervisor = 매 라운드 Score/Rebuttal 능동 진행.

## DA 1:1 대조 (원본 debate → protocol §)

| 원본 debate DA | debate protocol § |
|---|---|
| debate-roi-gate | §⓪ |
| debate-full-flow | §1 |
| debate-step1-spawn | §2 (TeamCreate+Agent) |
| debate-step2-round | §3 (ev 랑데부) |
| debate-step3-convergence | §4 |
| debate-step4-judge | §5 (on-demand Clean Room) |
| debate-step5-collect | §6 |
| (신규) Supervisor wake | §7 (wake-ping 다중보장) |

## 진입 체크리스트 (Supervisor = 메인)

1. **§⓪ ROI 게이트**: 적합 판정(부적합 → 직접구현 권장 종료).
2. **scaffold + bootstrap**: `bash ~/.claude/skills/debate/lib/debate-bootstrap.sh .debate <context_spec>` → debate.md + dispatch(Challenger+watchdog+Judge prompt) + manifest(transport=teammate-in-process, jitter).
3. **dispatch**: manifest spawn_rule — STEP-1 `TeamCreate(team_name="debate")` 1회 → STEP-2 `Agent(team_name="debate", name="Challenger", model:opus)` + `Agent(... name="watchdog", model:haiku)`. ⛔ `run_in_background` 금지. Challenger register.
4. **도메인 독립 주입**: debate-context.md 작성 → Challenger `ev:domain_ack`+wake-ping 수신 전 §3 진입 금지(편향 차단).
5. **라운드 turn-loop**: Challenger gating ev wake-ping 수신 → `h2-log.sh last` Read → Score/Attack지시/Rebuttal/수렴판정. max 4R.
6. **§5 Judge on-demand**: 수렴 시 `Agent(team_name="debate", name="Judge", model:opus)` 기존 team join → judge-protocol.md verdict → `ev:verdict_done`+wake-ping.
7. **§6 회수**: verdict 보고 + 팀 shutdown_request.

## 자산

- [protocol.md](./protocol.md) — 런타임 SSOT (ROI·흐름·dispatch·라운드 ev랑데부·수렴·Clean Room Judge·**wake-ping 다중보장 §7**·압축) **반드시 Read 후 수행**
- `lib/debate-bootstrap.sh` — scaffold + dispatch + manifest(transport=teammate-in-process, JITTER, harness lib 재사용)
- `templates/{disclaimer-strict-debate,role-challenger-debate,role-judge-debate}.txt` — wake-ping 의무 내장
- `challenger-constitution.md` / `judge-protocol.md` — 원본 debate verbatim 재사용(내용 불변, transport 만 전환)
- **재사용(harness-wf)**: `lib/{h2-state,h2-log,h2-agents,h2-env}.sh` + `templates/haiku-watchdog.txt`

**Signal-to-Action**: 트리거 → §⓪ ROI → debate-bootstrap → TeamCreate "debate" + Challenger(opus)·watchdog(haiku) dispatch(run_in_background 금지) → 도메인 독립주입(ev:domain_ack+wake-ping) → 라운드(Steelman/Score/Attack/Rebuttal, ev 랑데부, 매 gating ev teammate→Supervisor wake-ping) → 수렴(max4R) → Judge on-demand Clean Room(verdict_done+wake-ping) → 회수+shutdown. psmux/send-keys/acks.txt/self-wake 0.

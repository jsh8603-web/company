---
name: harness-wf — psmux send-keys 제거 공식프리미티브 5역할 워크플로우
description: 트리거 하네스wf 시 메인=Supervisor 가 protocol.md 로드→harness.md 작성→role-*.txt dispatch 로 harness-wf 와 동일 문서체계 구동. 기존 harness-wf(psmux) 병행 보존.
type: reference
tags: [type/skill, domain/harness-wf, topic/harness, load/trigger]
date: 2026-05-19
status: active
---

# harness-wf — 공식 프리미티브 5역할 워크플로우 (psmux send-keys 제거)

**Kind**: scenario

**Trigger**:
- Keywords: `하네스wf`, `harness-wf`, `harness`, `하네스 wf`
- Context: 다파일 코딩 task 에 독립검증(환각차단) + 진짜 병렬이 필요하고, psmux 키입력주입 통신을 쓰지 않으려 할 때

**When**: 사용자가 위 키워드로 진입 지시 시 (기존 `하네스wf`/harness-wf = psmux 원본, 병행 보존 — 혼동 금지)

**If**: plan.md 존재 + Phase/Sub-obj 분해 가능 + 3+ 파일 변경 규모

**Then**: 메인 세션(현재 Opus 세션) = Supervisor 로서 [protocol.md](./protocol.md) 8단계·상태머신 S0~S11 수행. teammate 모드 미사용(U1/U2 측정 확정). 역할 4개 = teamless bg Agent dispatch + agentId resume 관통.

**Because**: send-keys 타이핑+인코딩+capture 폴링(초~수십초) 제거. 통신 = `execution-log.jsonl` SSOT(메인=relay 아님). Worker↔Verifier zero-main peer 랑데부(측정 3.4s) + 완료푸시 트리거. 컨텍스트 = agentId resume 관통(측정 recalled 8642). 환각차단 = 독립 컨텍스트 구조적 분리(채널 무관 보존).

## 진입 체크리스트 (Supervisor = 메인)

1. **Immutable 확인**: plan-harness-wf-official-migration-2026-05-19.md §핵심 유지 사항 (teammate 금지 / 기존 harness-wf 삭제 금지 / scope-disclaimer 강제 / 비서 의존 0 / agent resume 관통).
2. **scaffold**: `mkdir -p .harness/{verdicts,artifacts}`; `h2-state.sh transition .harness S0 IDLE 0`; **dead-man's switch 등록** `bash lib/h2-registry.sh register "$(cd .harness && pwd)"` (button 이 워치독 `.self-wake-ts` 생존 감시 → 사망 시 Supervisor 재스폰).
3. **dispatch (④⑤)**: 역할별 `h2-dispatch.sh` 로 prompt 조립(disclaimer-strict = Worker/Verifier/Healer, disclaimer-sr = SR) → Agent tool 호출(run_in_background) → `h2-agents.sh register` 로 agentId 영속.
   - ⚠️ **TeamCreate 교착 해소** (다음 phase 팀 생성 시 자주 발생): 새 팀 TeamCreate 가 `Already leading team <X>` 로 막히면 = 이전 phase 의 **완료모드 teammate(exit_code:0 후)** 가 shutdown_request 에 SendMessage 를 invoke 하지 않아 TeamDelete `active member` 가 실패하는 데드락. **해소**(spawn PLAN STEP-0 와 동일): (a) `bash lib/teammate-spawn.sh unblock-leader <X>` → 팀 메타 mv 백업(rm 은 home-guard 차단) (b) **TeamDelete tool 1회** → 파일 없어 active 체크 우회, in-memory leader 정리 (c) TeamCreate <new> 재시도 → spawn. 실증=2026-05-28 Inv Phase0.
4. **watchdog (patrol ①)**: ③ dispatch 배치에 sonnet watchdog 포함(teammate-spawn.sh) — KICKOFF 에서 `h2-watchdog.sh watch` **self-respawn 루프** 1회 기동(cap→자가 재호출, Supervisor 미경유 = ZERO-MAIN). 별도 `run_in_background` loop 기동 아님(v1 폐기). 워치독 생존감시 = button dead-man's switch(`.self-wake-ts` mtime staleness).
5. **⑥ SR Pre-Review** (MODE=C) → **⑦ Phase 루프**(상태머신 + §6 code-sanity 6트리거 + §7 FAIL 9-step) → **⑧ 정리**.
6. **resume 관통**: 역할 재호출 = `SendMessage(to=agents.json[role])` (죽이지 않음). 압축 임계 시에만 🔑 키블록 인계.

## 자산

- [protocol.md](./protocol.md) — 런타임 SSOT (상태머신·통신·patrol·에스컬·컨텍스트·SR·종료) **반드시 Read 후 수행**
- `templates/disclaimer-strict.txt` / `disclaimer-sr.txt` — 역할별 scope-disclaimer (측정 부작용 0)
- `lib/h2-state.sh` `h2-log.sh` `h2-watchdog.sh` `h2-dispatch.sh` `h2-agents.sh` `h2-env.sh`
- E2E 검증: plan §E2E (psmux 원본 A/B 평행 비교, 합격 7기준)

**Signal-to-Action**: 트리거 수신 → Immutable 확인 → .harness scaffold → protocol.md Read → 4역할 dispatch(disclaimer 부착)+watchdog 기동 → 상태머신 루프(메인=relay 아님, content=execution-log) → 종료 정리. psmux/비서 호출 일절 금지.

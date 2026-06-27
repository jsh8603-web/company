---
tags:
  - type/skill
  - domain/collaboration
name: Debate Challenger Constitution
description: |
  Challenger 브리프 템플릿 + Steelman 의무 + 평가 그리드.
  skill.md Step 2에서 참조.
date: 2026-04-06
---

# Challenger Constitution

## Challenger 브리프 템플릿

`debate-brief.md`에 아래 구조로 작성. Challenger는 이미 debate-context.md로
도메인을 이해한 상태에서 이 파일을 받는다.

```markdown
# Debate Brief: {주제}

## Your Role
You are a Challenger. You have already read the domain context.
Now read this proposal and evaluate it rigorously.

## Communication Protocol
- All files: C:\Users\jsh86\ (Windows absolute paths)
- All content in Korean
- Each round has TWO separate files (never combine):
  1. steelman file (restate proposal at its strongest)
  2. attack file (critique the steelman + evaluation grid)
- **파일 작성 → ACK → sendkey-back 3-Step 순서 필수**: thinking만 하고 파일 미작성 + ACK 미전송 + sendkey 미송신은 파이프라인을 정지시킨다.
- **ACK 기록**: Bash 도구(tool call)로 `echo '{step}_done' >> /c/Users/jsh86/debate-acks.txt`
- **⛔ sendkey-back 필수 (2026-04-20 신설)**: ACK 파일 기록 직후 Supervisor 세션에 완료 통지 전송. Supervisor 가 능동 폴링하지 않도록 **이벤트 기반 통지**가 debate 흐름 연속성의 핵심.
  ```bash
  # debate-context.md 에서 Supervisor Session 읽기 (1회만, 캐시 가능)
  SUPERVISOR_SESSION=$(grep -A1 "^## Supervisor Session" /c/Users/jsh86/debate-context.md | tail -1 | tr -d '[:space:]')
  source "$HOME/.claude/scripts/lib/psmux-send.sh"
  psmux_send_message "$SUPERVISOR_SESSION" "📢 {step}_done — Read C:\\Users\\jsh86\\debate-R{N}-{steelman|attack}.md 후 다음 단계 진행"
  ```
  `{step}` = `steelman_R1`, `attack_R1`, `steelman_R2`, `attack_R2`, ...

## Research Capability (도메인 이해 단계 1회만 허용)

domain context를 읽은 직후, **Steelman 작성 전에 1회** Gemini 리서치를 수행할 수 있다.
이후 라운드(R2+)에서는 리서치를 추가로 수행하지 않는다 — `debate-research.md` 참조만.

- **실행 방법**: [~/.claude/skills/search-engine/skill.md](~/.claude/skills/search-engine/skill.md) 참조 (Phase 1 + Phase 2)
- **결과 저장**: `C:\Users\jsh86\debate-research.md`에 핵심 발견 + 출처 URL 저장
- **When to research** (하나라도 해당하면 리서치 실행):
  - domain context에 없는 사실관계
  - 업계 표준/모범사례, 대안의 실효성 근거
  - **⚠️ 제안에 특정 플랫폼/API/라이브러리 호환성 가정이 포함된 경우** (예: "iOS Safari에서 opus 지원", "Gemini API가 X를 지원") — 반드시 사실관계를 리서치로 검증. 미검증 호환성 가정은 steelman에서 가장 흔한 straw man 원인
- **When NOT to**: 논리적 추론만으로 충분하고, 검증 가능한 사실관계 가정이 제안에 없는 경우

## Proposed Solution
{Supervisor의 제안 상세}

## Round 1 Instructions

### Step 1: Steelman (debate-R1-steelman.md)
Restate my proposal in its STRONGEST possible form.
- Fill in gaps I left out, charitably
- Make it MORE convincing than my original
- DO NOT critique in this file
- After writing, use the **Bash tool** (tool call) to run: `echo 'steelman_R1_done' >> /c/Users/jsh86/debate-acks.txt`

### Step 2: Attack (debate-R1-attack.md)
WAIT for my score on your steelman before writing this.
I will send you the score file path.

When approved, attack YOUR OWN steelman using the Evaluation Grid below.
You must also propose at least one concrete alternative.
```

## Steelman 검증 기준

Supervisor가 steelman을 **항목별로** 채점한다:

| # | Proposer 원 주장 | Steelman 재진술 | 판정 | 사유 |
|---|-----------------|----------------|------|------|
| 1 | {원 주장} | {재진술} | PASS/WEAK/FAIL | {근거} |

- **PASS**: 정확한 재진술 + 강화
- **WEAK**: straw man은 아니지만 핵심 논거 누락 또는 강화 불충분. Attack 진행하되, Supervisor가 약한 부분과 근거를 Attack 지시에 첨부한다.
- **FAIL**: 원 주장 왜곡 또는 핵심 누락으로 straw man. 해당 항목만 재steelman (1회).

> 단일 종합 점수(예: 9/10)가 아니라 항목별 PASS/WEAK/FAIL.
> 전체 이해도가 높아도 개별 항목이 straw man이면 해당 Attack이 낭비된다.

## 평가 그리드 — 도메인별 프리셋

Attack 파일에 반드시 포함되어야 하는 구조. **모든 칸을 채워야 함.**

### 범용 (기본)

```markdown
## Evaluation Grid

| Principle | Verdict | Evidence (quote from steelman) | Improvement |
|-----------|---------|-------------------------------|-------------|
| Logical consistency | PASS/WARN/FAIL | "..." | ... |
| Assumption validity | PASS/WARN/FAIL | "..." | ... |
| Edge cases | PASS/WARN/FAIL | "..." | ... |
| Scalability / Maintainability | PASS/WARN/FAIL | "..." | ... |
| Alternative exists | PASS/WARN/FAIL | "..." | ... |

## FAIL/WARN Detail (200+ chars each)
{Each FAIL/WARN item gets a dedicated analysis section}

## Proposed Alternative
{At least one concrete alternative approach}
```

### 아키텍처 토론

범용 그리드에 추가:

```markdown
| Coupling / Cohesion | PASS/WARN/FAIL | "..." | ... |
| Failure propagation | PASS/WARN/FAIL | "..." | ... |
| Deploy complexity | PASS/WARN/FAIL | "..." | ... |
```

### 코드 리뷰

범용 그리드에 추가:

```markdown
| Type safety | PASS/WARN/FAIL | "..." | ... |
| Testability | PASS/WARN/FAIL | "..." | ... |
| Performance impact | PASS/WARN/FAIL | "..." | ... |
```

### 운영 결정

범용 그리드에 추가:

```markdown
| Rollback feasibility | PASS/WARN/FAIL | "..." | ... |
| Observability | PASS/WARN/FAIL | "..." | ... |
| Team capability fit | PASS/WARN/FAIL | "..." | ... |
```

## 후속 라운드 (R2+) 지시 패턴

```bash
# Supervisor가 rebuttal 작성 후:
source "$HOME/.claude/scripts/lib/psmux-send.sh"
psmux_send_message debate 'Read C:\Users\jsh86\debate-R{N}-rebuttal.md for counter-arguments. Write steelman to C:\Users\jsh86\debate-R{N+1}-steelman.md'
```

후속 라운드에서도 Steelman → 검증 → Attack 순서는 동일.
Challenger는 매 라운드 새로운 steelman을 작성해야 한다
(이전 라운드의 rebuttal을 반영한 Proposer의 강화된 입장을 재진술).

## Keypoints 업데이트 구조

매 라운드 후 Supervisor가 debate-keypoints.md에 추가:

```markdown
## Round {N}
### New Claims (first appeared this round)
- [{ID}] {Agent}: {claim summary}

### Status Changes (existing claims progressed)
- [{ID}] → {new status}: {reason}

### Agreements
- [{ID}] {what was agreed}

### Unresolved
- [{ID}] vs [{ID}]: {what needs resolution}
```

"New Claims" 섹션이 비어있으면 → 수렴 신호.

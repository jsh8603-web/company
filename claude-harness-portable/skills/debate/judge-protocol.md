---
tags:
  - type/skill
  - domain/collaboration
name: Debate Clean Room Judge Protocol
description: |
  Clean Room Judge 프로토콜. 의견 제거 맥락 + 익명 논거 + 자체 확인 +
  Argument-Level Synthesis (분해 → 개별 판정 → 충돌 해소 → 유효 논점 조립).
  skill.md Step 4에서 참조.
date: 2026-04-06
---

# Clean Room Judge Protocol

## 원칙

Judge는 토론에 참여하지 않은 제3자. 어느 쪽 편도 없다.
"누가 이겼나"를 판정하지 않는다. **논점 단위로 분해하여 유효한 것만 조립**한다.

## Judge Brief 템플릿

Supervisor가 `debate-judge-brief.md`에 작성:

```markdown
# Judge Brief

## Your Role
You are an impartial Clean Room Judge. You have NO prior involvement 
in this debate. Evaluate arguments on merit, not on who said them.

## Judging Criteria (weighted)

| Criterion | Description | Weight |
|-----------|-------------|--------|
| Factual accuracy | Does the claim match what you can verify? | 30% |
| Logical consistency | No leaps from premise to conclusion? | 25% |
| Feasibility | Achievable under current constraints? | 20% |
| Risk awareness | Does the agent acknowledge its own weaknesses? | 15% |
| Alternative quality | Did it propose better options, not just criticize? | 10% |

## Bias Guardrails
- **Position bias**: 주장의 제시 순서(A가 먼저, B가 나중)에 영향을 받지 마라. 
  먼저 읽은 주장이 더 설득력 있어 보이는 것은 인지적 착각이다. 
  반드시 A와 B를 동등하게 재검토한 후 판정하라.
- **Verbosity bias**: 더 길거나 상세한 주장이 더 품질이 높다고 판단하지 마라. 
  간결하고 핵심을 찌르는 논거가 장황한 서술보다 상위이다. 
  불필요한 반복이나 장황함은 오히려 감점 요인이다.

## Step-by-Step Instructions

### Step 1: Domain Understanding
Read C:\Users\jsh86\debate-context.md
(This contains only objective facts — no opinions.)

### Step 2: Debate Map
Read C:\Users\jsh86\debate-keypoints.md
(Overview: what was agreed, what is unresolved, what claims exist.)

### Step 3: Self-Verification
Verify these specific points yourself. Save findings to 
C:\Users\jsh86\debate-judge-findings.md:
{Supervisor가 여기에 확인 포인트 나열}
- Example: "Read file X and check if dependency structure matches claims"
- Example: "Grep for pattern Y to verify if alternative approach is viable"

### Step 4: Read Arguments (ANONYMOUS)
Agent A files (read in order):
{파일 경로 목록 — A/B 배정은 랜덤}

Agent B files (read in order):
{파일 경로 목록}

NOTE: You do not know which agent is the original proposer.
Evaluate arguments purely on their merit.

### Step 5: Write Verdict
Follow the verdict template below exactly.
Save to C:\Users\jsh86\debate-verdict.md
Then use the **Bash tool** (tool call) to run: `echo 'verdict_done' >> /c/Users/jsh86/debate-acks.txt`
```

> **A/B 배정과 merit-based 평가**:
> 파일 유형(steelman/attack vs brief/rebuttal)에서 역할이 추론 가능한 구조적 한계가 있다.
> 따라서 A/B 배정의 목적은 **완전 익명이 아니라 merit-based 평가 강제**이다.
> Brief에 반드시 다음을 명시: "역할을 추론할 수 있더라도, 각 논점은 출처와 무관하게
> 사실·논리·증거로만 평가하라. Verdict에서 '어느 Agent가 이겼다'는 판정을 하지 마라."
> 
> **Supervisor 요약 배제**: arguments를 요약하지 않고 원문 파일 경로만 나열.
> 요약 과정에서 Supervisor 편향이 들어가는 것을 원천 차단.

---

## Verdict 템플릿 — Argument-Level Synthesis

Judge가 채워야 하는 구조. **생략 불가.**

```markdown
# Debate Verdict

## 1. Self-Verification Findings
{debate-judge-findings.md의 핵심 요약}
- {확인 항목 1}: {결과}
- {확인 항목 2}: {결과}

## 2. Argument Decomposition

### Agent A Claims
- [A1] {claim}
  - Premise: {what must be true for this claim to hold}
  - Evidence: {cited from A's files, or "none provided"}

- [A2] {claim}
  - Premise: ...
  - Evidence: ...

### Agent B Claims
- [B1] {claim}
  - Premise: ...
  - Evidence: ...

- [B2] {claim}
  - Premise: ...
  - Evidence: ...

## 3. Per-Claim Evaluation

| ID | Claim | Premise valid? | Evidence sufficient? | Self-verified? | Verdict |
|----|-------|---------------|---------------------|----------------|---------|
| A1 | ... | Y/N/Partial | Y/N | {finding ref} | VALID / PARTIAL / UNVERIFIED / INVALID |
| A2 | ... | | | | |
| B1 | ... | | | | |
| B2 | ... | | | | |

Verdict definitions:
- **VALID**: Premise correct + evidence sufficient + consistent with my verification
- **PARTIAL**: Partially correct or conditionally true (scope-limited)
- **UNVERIFIED**: Claim is reasonable but evidence is insufficient to confirm
- **INVALID**: Premise wrong or contradicted by my verification

## 4. Conflict Resolution

{For each pair of claims that directly contradict:}

### [A{x}] vs [B{y}]: {topic}
- A's position: ...
- B's position: ...
- My verification shows: ...
- Resolution: {how both can coexist, or which one prevails and why}

## 5. Synthesis — Valid Claims Assembly

### Accepted Facts (VALID + PARTIAL)
- [A1] ... 
- [B1] ...
- [B2] ...

### Conflicts Resolved
- [A{x}] vs [B{y}] → {resolution}

### Assembled Conclusion
{NOT "Agent A wins" — instead, combine all valid points into the 
best possible answer. This may be neither A's nor B's original position.}

{Each part of this conclusion must trace back to a specific claim ID.}

> **⛔ 에이전트별 점수 비교/가중 합산 금지.**
> "Agent A: 4.05/5, Agent B: 3.35/5" 같은 에이전트 단위 점수를 산출하지 마라.
> 이는 "누가 이겼나"를 판정하는 것이며, Argument-Level Synthesis 원칙에 위배된다.
> Verdict의 목적은 **유효한 논점을 조립**하는 것이지 에이전트를 평가하는 것이 아니다.

### Traceability Map
| Conclusion element | Source claim(s) |
|-------------------|----------------|
| {element 1} | A1(VALID) + B2(VALID) |
| {element 2} | A3(PARTIAL) + B1(VALID) conflict resolved |
| ... | ... |

### Coverage Check
{debate-keypoints.md의 Unresolved 항목을 모두 열거하고, 
각각이 이 verdict의 어느 섹션에서 다루어졌는지 확인하라.
누락된 항목이 있으면 해당 항목에 대한 판정을 추가하라.}

### Self-Review
{verdict를 최종화하기 전에 다음을 자문하라:
- 특정 Agent의 주장에 치우친 판정이 있는가?
- 사실 검증 없이 한쪽 주장을 수용한 곳이 있는가?
- Traceability Map에서 근거 없는 결론이 있는가?
문제가 발견되면 해당 섹션을 수정한 후 최종화하라.}

### Unresolved (needs data, not debate)
- [{ID}]: {what additional data/testing is needed}

### Action Items
- [ ] {concrete next step, traceable to claim ID}
- [ ] {concrete next step}
```

---

## Judge 실행 순서 요약

```
1. debate-context.md Read        → 도메인 (의견 없음)
2. debate-keypoints.md Read      → 토론 지형도 (쟁점/합의 파악)
3. 지정 포인트 자체 확인          → debate-judge-findings.md 저장
4. 양측 원문 Read (A/B 익명)     → 각 주장을 원자적으로 분해
5. Per-Claim Evaluation          → VALID/PARTIAL/UNVERIFIED/INVALID
6. Conflict Resolution           → 충돌 쌍 해소
7. Synthesis                     → 유효 논점만 조립 + 추적 가능성 매핑
→ debate-verdict.md 저장
```

## 핵심: 왜 이 구조가 편향을 막는가

| 편향 위험 | 차단 메커니즘 |
|----------|-------------|
| Supervisor가 brief에 의견 삽입 | context.md는 사실만, 원문은 경로만 전달 (요약 배제) |
| "Agent A = 제안자"로 추론 | 파일 유형에서 추론 가능하나 merit-based 평가 강제 |
| 한쪽 전체를 지지 | 에이전트 단위 판정 불가 구조 → 논점별 테이블 필수 |
| 근거 없는 결론 | Traceability Map으로 모든 결론이 claim ID에 매��� |
| 자체 확인 없이 논거만 믿음 | Step 3에서 핵심 사실 직접 검증 |

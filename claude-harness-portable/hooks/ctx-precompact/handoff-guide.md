# 핸드오프 작성 가이드 (ctx-precompact 세트)

> ctx-precompact 훅의 일부. 압축/세션종료로 대화 컨텍스트가 끊길 때, **다음 세션이 대화 로그 없이
> 이 파일 하나만으로 동등 수준으로 재개**할 수 있는 핸드오프 md 를 작성하는 기준이다.
> ctx-precompact 의 PreCompact 게이트가 핸드오프 없는 /compact 를 막으므로 "압축 전 무조건 작성"이
> 보장된다. (별도 스킬 아님 — 압축 훅 세트로 묶임.)

## 1. 언제 작성하나

- **압축 직전** (ctx-precompact critical 도달) — 핸드오프를 써야 /compact 가 풀린다.
- **세션 종료·인계 직전** — 다음 세션/사람에게 넘길 때.
- 단발 1턴 작업·진행 마커만 필요하면 제외(progress.md 한 줄로 충분).

## 2. 작성 기준 — 6섹션 + 작업단위 5필드

핸드오프 md 경로: `~/.claude/memory/handoff-{topic}-{YYYYMMDDHHMM}.md`
(memory 디렉토리 없으면 프로젝트 루트 `handoff-{topic}-{YYYYMMDDHHMM}.md`).

### frontmatter (필수)
```yaml
---
tags: [type/handoff]
date: YYYY-MM-DD
next-action: "다음 세션 첫 행동 1줄"
---
```

### 필수 6섹션 (하나라도 비면 위반)
| # | 섹션 | 내용 |
|---|---|---|
| 1 | 현재상태·첫행동 | 지금 어디까지 왔나 + 다음 세션이 할 첫 행동 |
| 2 | 진행맵 | 전체 작업 중 완료/잔여 (무엇을 했고 뭐가 남았나) |
| 3 | 사용자박제 | **대화에서만 나온 결정**(요약 불가, 원문 그대로 박제) |
| 4 | 파일 inventory | 산출물·수정 파일 **절대경로** 목록 |
| 5 | 미해결·실패 | 삽질 위험 있는 실패 시도·우회법 |
| 6 | 자문종합 | 외부 자문·subagent 결론 (RESULTS 전체 항목 1:1 매핑, **누락 0**) |

### 작업·지표 단위별 5필드 (요약표 금지 — 단위마다 박제)
- (a) 완료지점 (b) 멈춘 이유 (c) 잔여 작업 (d) 자문·subagent **원문 경로 링크** (e) 재현 레시피

### Write 전 자가체크 3
1. 빈 섹션 없음
2. 외부 참조는 모두 절대경로
3. **"파일만으로 §1(현재상태·첫행동) 재개 가능한가"**

### 핵심 판정 한 줄
> *다음 세션이 대화 로그 없이 이 파일 하나만으로 나와 동등 수준으로 재개 가능한가.*
> 아니면 부족한 섹션을 채운다.

## 3. 압축 게이트 통과 절차 (무조건 강제)

ctx-precompact 의 PreCompact 훅이 핸드오프 존재를 검사한다:

```bash
# (1) 위 6섹션 기준으로 핸드오프 md 작성 (Write)
#     예: ~/.claude/memory/handoff-{topic}-{YYYYMMDDHHMM}.md

# (2) sentinel 에 핸드오프 md 의 절대경로 기록 (cwd 기준)
mkdir -p "$(pwd)/.ctx-precompact"
echo "/absolute/path/to/handoff-{topic}-{YYYYMMDDHHMM}.md" > "$(pwd)/.ctx-precompact/handoff-done"

# (3) 세션이 스스로 압축
bash ~/.claude/hooks/ctx-precompact/self-compact.sh
```

- **PreCompact 게이트**: `<cwd>/.ctx-precompact/handoff-done` 가 있고 그 안에 적힌 md 가 실제
  존재 + 최소 크기(기본 400B) 이상이면 통과(압축 진행), 아니면 `exit(2)` 로 **모든 압축 경로
  (수동 /compact + native auto-compact)를 차단**한다. 통과 시 sentinel 은 소비(삭제)되어 다음
  압축 때 재작성을 강제한다.
- **긴급 우회** (subagent 진행 중 등 핸드오프를 못 쓰는 상황): `touch "$(pwd)/.ctx-precompact/handoff-skip"`
  1회용. 단 이건 다음 세션 컨텍스트 인계를 포기하는 것이라 가급적 핸드오프를 쓴다.

## 4. ctx-precompact 와의 관계

- **handoff-guide.md** (이 문서) = 무엇을(6섹션/5필드) + 게이트 통과 절차
- **ctx-precompact.js** (PostToolUse) = 언제(critical 임계) → 핸드오프 작성 지시 주입
- **ctx-precompact-pre.js** (PreCompact) = 강제(핸드오프 없으면 압축 차단)
- **self-compact.sh** = 세션 자율 압축 + sentinel 2차 확인

critical 도달 → 핸드오프 작성 지시 주입 → 세션이 이 가이드대로 작성 → sentinel 기록 →
self-compact → PreCompact 게이트 통과 → 압축. 핸드오프 없으면 압축 자체가 막힌다.

# 핸드오프 작성 가이드 (ctx-precompact 세트)

> ctx-precompact 훅의 일부. 압축/세션종료로 대화 컨텍스트가 끊길 때, **다음 세션이 대화 로그 없이
> 이 파일 하나만으로 동등 수준으로 재개**할 수 있는 핸드오프 md 를 작성하는 기준이다.
> ctx-precompact 의 PreCompact 게이트가 핸드오프 없는 /compact 를 막으므로 "압축 전 무조건 작성"이
> 보장된다. (별도 스킬 아님 — 압축 훅 세트로 묶임.)
>
> 핸드오프는 **볼트(BGE RAG 색인 대상) 안 프로젝트별 폴더**에 쌓인다 → 나중에 의미 검색으로 찾는다.

## 1. 언제 작성하나

- **압축 직전** (ctx-precompact critical 도달) — 핸드오프를 써야 /compact 가 풀린다.
- **세션 종료·인계 직전** — 다음 세션/사람에게 넘길 때.
- 단발 1턴 작업·진행 마커만 필요하면 제외(progress.md 한 줄로 충분).

## 2. 어디에 쓰나 — 볼트 안 프로젝트별 폴더

핸드오프 루트는 환경마다 다르므로 `~/.claude/.handoff-vault` 파일에 1회 지정한다(볼트 안 한 폴더):
```bash
echo "/path/to/vault/handoff" > ~/.claude/.handoff-vault   # PC 별 1회. 볼트(RAG 색인 대상) 내부 경로
```

작성 경로 결정:
```bash
ROOT="$(cat ~/.claude/.handoff-vault 2>/dev/null)"
PROJ="$(basename "$(pwd)")"
if [ -n "$ROOT" ]; then DIR="$ROOT/$PROJ"; else DIR="$(pwd)/handoff"; fi   # 미설정 시 프로젝트 로컬 fallback
mkdir -p "$DIR"
# 파일명 = 시간순 정렬 + 토픽 식별
MD="$DIR/$(date +%Y%m%d-%H%M)-{topic}.md"
```

- `.handoff-vault` 설정 시 → `<볼트루트>/<프로젝트명>/YYYYMMDD-HHMM-{topic}.md` (RAG 색인됨)
- 미설정 시 → `<프로젝트>/handoff/YYYYMMDD-HHMM-{topic}.md` (로컬, git 추적)

## 3. 작성 기준 — frontmatter + 6섹션 + 작업단위 5필드

### frontmatter (RAG 색인·필터용, 필수)
```yaml
---
title: {한 줄 제목 — 무슨 작업인지 자연어로}
project: {프로젝트명}
date: YYYY-MM-DD
status: active        # active(미해결) | done(완료)
tags: [handoff, {도메인}, {토픽}]
next-action: "다음 세션 첫 행동 1줄"
---

> **요약**: {이번 세션이 한 일 + 다음 할 일 2~3줄}  ← BGE 임베딩 검색 품질의 핵심
```
RAG 가 의미 검색하므로 `title` + 요약 문단을 **자연어로 충실히** 쓴다(키워드 나열 금지).

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

## 4. 이후 "무슨 작업 했는지" 조회 (3단)

1. **RAG 의미 검색 (주)** — 볼트가 BGE 색인 대상이라, "X 관련 핸드오프" 식 자연어로 검색.
   frontmatter `title`·요약 문단이 검색 품질을 좌우한다.
2. **ls 시간순 (보조)** — `ls <볼트루트>/<프로젝트>/` → 파일명(YYYYMMDD-HHMM-topic)으로 일람.
3. **INDEX (선택, 빠른 훑기)** — `<볼트루트>/<프로젝트>/INDEX.md` 맨 위에 한 줄 prepend:
   ```
   - 2026-06-27 18:30 [topic](20260627-1830-topic.md) — next: {다음 행동} · status: done
   ```
   미해결만 보려면 `status: active` 로 grep.

## 5. 압축 게이트 통과 절차 (무조건 강제)

```bash
# (1) §2~§3 대로 핸드오프 md 작성 (위 ROOT/PROJ 규칙)
# (2) sentinel 에 핸드오프 md 의 절대경로 기록 (cwd 기준 — 볼트 경로여도 OK)
mkdir -p "$(pwd)/.ctx-precompact"
echo "$MD" > "$(pwd)/.ctx-precompact/handoff-done"
# (3) 세션이 스스로 압축
bash ~/.claude/hooks/ctx-precompact/self-compact.sh
```

- **PreCompact 게이트**: `<cwd>/.ctx-precompact/handoff-done` 가 가리키는 md 가 실제 존재 + 최소
  크기(400B) 이상이면 통과(압축 진행), 아니면 `exit(2)` 로 **모든 압축 경로(수동 /compact + native
  auto-compact)를 차단**. 통과 시 sentinel 소비 → 다음 압축 때 재작성 강제.
- **긴급 우회**: `touch "$(pwd)/.ctx-precompact/handoff-skip"` (1회용, 인계 포기).

## 6. ctx-precompact 와의 관계

- **handoff-guide.md** (이 문서) = 무엇을(frontmatter/6섹션/5필드) + 어디에(볼트) + 게이트 절차
- **ctx-precompact.js** (PostToolUse) = 언제(critical 임계) → 핸드오프 작성 지시 주입
- **ctx-precompact-pre.js** (PreCompact) = 강제(핸드오프 없으면 압축 차단)
- **self-compact.sh** = 세션 자율 압축 + sentinel 2차 확인

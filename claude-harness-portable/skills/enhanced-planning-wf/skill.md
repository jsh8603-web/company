---
tags:
  - type/skill
  - domain/planning
name: Enhanced 계획 워크플로우 (portable)
description: |
  "계획 wf", "강화 계획", "상세 계획" 트리거 시 동작하는 다관점 계획 검증 스킬.
  Phase 0α(debate 전략 검증) + Phase 0~4 구조로 계획의 허점을 사전 제거한다.
  조사는 네이티브(WebSearch/WebFetch) + finance db(ODBC) + 메모(회의록·메일) 3-소스로 추상화.
  외부 인프라(psmux·registry·remote Guard·외부 자문 스킬) 의존 없음 — 다른 PC 에서 바로 적용.
---

# enhanced-planning-wf (portable) — 강화 계획 워크플로우

> 복잡한 계획을 **다관점 검증**으로 허점을 제거하는 Opus 권장 스킬. Phase 0α(전략 검증, in-process
> teammate `debate` 위임) + Phase 0~4(실현가능성·코드 컨텍스트·Agent Team·UI/UX·실행 엔진) 구조.
> Pre-flight 에서 각 Phase 필요성을 자동 판정한다. 신규 프로젝트 [A] 와 기존 코드 기능 추가 [B]
> 두 경로를 Phase 0.5 에서 분기한다.
>
> **portable 특징** (button 원본 대비): psmux·registry·remote Guard·`/ultraplan`·`model-switch-and-send.sh`
> 의존 제거. 외부 자문 스킬(search-engine·cross-verify) 대신 **네이티브 웹 + 사내 데이터 소스** 사용.
> 실행 엔진은 **harness 단일**(없으면 직접 실행). 동반 의존 = `harness-wf` + `debate` 둘뿐.

---

## 0. 진입 — 모델·WF 상태

- **Opus 권장**: 이 WF 는 다관점 검증·전략 판단이 핵심이라 사고 돌파가 필요하다. Opus 세션에서
  실행한다. (모델 전환 헬퍼는 환경마다 다르므로 강제하지 않음 — 단일 세션이면 그냥 Opus 로 시작.)
- **WF 마커**(선택): WF 진입 시 프로젝트 루트에 `.wf-active`(`{"type":"planning"}`) 를 만들면,
  다른 모니터링이 WF 상태를 감지할 수 있다. 환경에 그런 hook 이 없으면 생략해도 무방하다.
  Phase 4 에서 실행 엔진으로 넘어갈 때는 `type` 만 바꾼다(`{"type":"harness"}`), 삭제 후 재생성 금지.
- 온디맨드 Read 만: 프로젝트 CLAUDE.md / 도메인 문서. WF 자체가 절차를 담으므로 별도 파이프라인
  문서 Read 는 불필요하다.

---

## 1. Pre-flight — Phase 실행 범위 자동 판정

WF 시작 직후, Phase 0 직전에 plan.md(또는 사용자 요구사항) 전체를 읽고 각 Phase 의 필요성을 판정한다.
**사용자 확인 없이** 판정 후 첫 해당 Phase 로 바로 진행한다.

| Phase | 스킵 조건 | 실행 조건 |
|---|---|---|
| 0α 전략 검증 | `DEBATE-VERDICT` 마커 있음 / 기존 코드 내부 개선(리팩토링·버그·튜닝) | 새 아키텍처·외부 서비스·3일+·10파일+·미결정 분기·접근법 불확실 중 하나 |
| 0.5 코드 컨텍스트 | [A] 신규이고 코드 컨텍스트 이미 포함 / 수정 2파일 이하 | [B] 3+ 파일 |
| 1 Agent Team | 단일 파일 단순 변경(외부 의존 0 + 회귀 위험 0) | 거의 항상 |
| 2 UI/UX | UI 없음(CLI·배치·hook·API·**finance .py/excel 모델**) | 웹·모바일 + UI 신규/대폭 변경 |
| 3 Coder Readiness | — | 항상 |
| 4 실행 엔진 | — | 항상 |

판정 테이블을 출력한 뒤, plan.md 상단에 마커를 남긴다(압축 복원용):
```
<!-- PRE-FLIGHT: phases=[1,3,4] skipped=[0a,0.5,2] -->
```

**예외**: 사용자가 "전체 Phase 실행" / "0α부터" 명시 → 판정 무시, 지시 적용. Phase 1 결과에서
UI 위험 발견 → 스킵했던 Phase 2 복원.

> **finance 노트**: 재무 모델링(.py / excel)은 보통 UI 가 없으므로 Phase 2 가 자동 스킵된다.
> 핵심은 Phase 0(데이터 실현가능성)·Phase 1(가정·계산 다관점 검증)·Phase 3(입출력 계약 = 실제
> 테이블 스키마)이다.

---

## 2. Phase 0 — 실현가능성 + 경로 분류

5단계:
1. plan.md / 요구사항 읽기
2. **실현가능성 판별** — 기술·비용·데이터 가용성·API 제한. (finance 면 **db 조회로 데이터 실재·값
   범위 확인** → §조사 소스 참조)
3. 불가능·비현실 항목을 사용자에게 보고 + 대안 제시
4. 사용자와 대화로 포함/제외 결정 + MVP 범위 확정 (AskUserQuestion 사용 — remote Guard 없음)
5. **경로 판별**:
   - 새 프로젝트·빈 코드베이스 → **[A] 신규** (Phase 0.5 에서 스켈레톤 1~3개)
   - 기존 코드에 기능 추가/변경 → **[B] 기능추가** (Phase 0.5 에서 코드 컨텍스트 패킷)

경로는 Phase 0.5 분기의 전제다.

---

## 3. Phase 0α — 전략 검증 (debate 위임)

plan.md 의 **접근 방식 자체**가 목적 달성에 최선인지 검증한다. 반드시 **`debate` 스킬**로 실행한다
(직접 Agent 단발 스폰·자체 steelman 금지 — A/B 익명성·Clean Room Judge·수렴 감지가 빠지면 형태만
같고 품질이 사라진다).

**실행**:
1. `~/.claude/skills/debate/protocol.md` 를 읽는다.
2. `bash ~/.claude/skills/debate/lib/debate-bootstrap.sh .debate <context_spec_file>` 로 scaffold.
3. protocol 대로 `TeamCreate(team_name="debate")` → `Agent(Challenger, opus)` + `Agent(watchdog, haiku)`
   → 수렴 시 `Agent(Judge, opus)` on-demand.
4. verdict(`.debate/debate-verdict.md`)의 Assembled Conclusion + Action Items 를 plan.md 에 반영하고
   `<!-- DEBATE-VERDICT -->` 마커 + "Debate 검증 결과" 섹션을 남긴다.

**debate-context 범위**: 문제 정의·현재 상황·제약·토론 질문. **제외**(= Phase 1 영역): 기술스택 비교·DB
스키마·API 설계·라이브러리 선택.

| 허용 (전략) | 금지 (Phase 1) |
|---|---|
| 목표 재정의 / 범위 축소·확대 / 다른 접근법 / MVP 재정의 | DB 스키마 / API 설계 / 기술스택 / 라이브러리 |

**스킵 경로 둘뿐**: (1) `DEBATE-VERDICT` 마커 존재, (2) Pre-flight 조건 충족. 비용 부담이면 plan.md
범위를 줄여 트리거 자체를 해제한다.

> finance 전략 검증이면 debate-context 에 **메모(회의록·메일) 검색 결과**를 넣어 "과거에 왜 이 방식으로
> 합의했나"를 Challenger 가 공격할 수 있게 한다(§조사 소스).

---

## 4. Phase 0.5 — 코드 컨텍스트

추상 계획만 주면 에이전트도 추상 의견만 낸다. 구체 코드를 보여줘야 "토큰 만료 처리 누락" 같은 구체적
지적이 나온다. 산출물을 **Phase 1 에이전트 프롬프트에 반드시 포함**한다.

- **[B] 기존 코드**: 수정 대상 함수/파일 Read → 컨텍스트 패킷(시그니처 + 핵심 로직 30~100줄 +
  수정 전/후 예상 변경점 + line number).
- **[A] 신규**: 가장 위험·불확실한 핵심 로직 1~3개 스켈레톤(시그니처 + 핵심 분기 + 외부 의존성 +
  입출력 예시). 선정 기준 = 가장 복잡·외부 의존 많음·동시성/상태 변경.

```python
def compute_impairment(cgu, fvlcd, viu):
    # 1. 회수가능액 = max(FVLCD, VIU)
    # 2. 손상차손 = max(장부가 - 회수가능액, 0)
    # 3. CGU 경계 검증 (사람 승인 게이트)
    # 반환: { recoverable, impairment_loss, cgu_boundary_ok }
```

---

## 5. Phase 1 — 다관점 검증 (Agent Team)

4단계를 순서대로:

**(1) [필수] Round 1 — 내부 Agent Team 3개 병렬 스폰** (스킵 금지, [B]면 컨텍스트 패킷 포함):

| Agent | 관점 | 초점 | 모델 |
|---|---|---|---|
| Technical Architect | 확장성 | 기술 부채·의존성·성능·장애 시나리오 | `model:"sonnet"` |
| Devil's Advocate | 구현 위험 | 설계가 실패할 기술 시나리오 | Opus 상속 |
| Cost Optimizer | 비용 효율 | 운영 비용·과잉 설계 | `model:"sonnet"` |

> finance 면 관점을 도메인에 맞춰 읽는다 — Technical Architect = **계산 정합성·tie-out**,
> Devil's Advocate = **가정·시제·자기참조 편향**(self-referential base, contemporaneous vs predictive),
> Cost Optimizer = **과잉 모델링·불필요 granularity**.

**(2) [조건부] Round 1-2b — 외부/사내 조사** (트리거 없으면 SKIP):
- "X vs Y 어느 쪽?" / "알려진 이슈" / "신규 기법·표준" → **WebSearch/WebFetch** (네이티브)
- "이 데이터·수치가 실제로 있나/값이 뭐냐" → **finance db (ODBC)**
- "과거에 왜 이렇게 결정했나 / 합의 배경" → **메모 (회의록·메일)**
- 코드 동시성·설계 반론이 필요하면 → 짧은 코드 스니펫(100줄 이하)으로 Devil's Advocate 재호출
  (별도 자문 스킬 없이 in-team 으로 흡수)

**(3) [필수] Round 2 — Devil's Advocate 수렴**: Round 1(+1-2b) 전체를 전달 → 구현 위험 vs 과잉 우려
분류 + 미지적 허점 추가 + 위험도 판정표(항목·위험도·근거·수정 제안).

**(4) Opus 종합 + 평가 그리드**:

| Verdict | 조건 |
|---|---|
| ACCEPT | 근거 명확 + plan.md 즉시 반영 |
| DISMISS | 과잉 우려 — **반드시 반론 근거 명시** |
| DEFER | 트레이드오프 존재 → 사용자 최종 결정 |

각 항목에 출처·Evidence(원문 인용)·판정 근거를 단다. "종합적으로 판단" 식 빈 결론 금지.
리서치 원본은 `~/.claude/docs/archive/research-raw/{project}-planning-phase1-{날짜}.txt` 에 보존,
plan.md 위험도 테이블엔 요약만.

---

## 6. Phase 2 — UI/UX (해당 시에만)

Pre-flight 가 "UI 있음"으로 판정한 경우(웹·모바일 + UI 신규/대폭 변경)에만 실행. **finance .py/excel 은
보통 자동 스킵**된다.

2단계: (1) 경쟁앱 조사(**WebSearch/WebFetch** 네이티브, 한국+해외 5+, UI 패턴 추출, 레퍼런스 테이블),
(2) 디자인 방향(원칙 1~2줄 + 레퍼런스 앱 2~3개 + 참고 이유 + 컴포넌트 목록). 색상 hex·행간·와이어프레임
같은 세부 스타일은 구현 단계로 이관.

---

## 7. Phase 3 — Coder Readiness (5항목)

코더가 plan.md 만으로 구현을 시작할 수 있는지 확인한다. 항상 실행하되 해당 없는 항목은 자연히 PASS.
모호 표현("적절히", "필요시")은 구체 수치/조건으로 **즉시 보완**(사용자 확인 불필요).

| # | 항목 | 확인 내용 |
|---|---|---|
| 1 | 외부 의존성 | API/DB/파일/서비스 — 엔드포인트·스키마·경로 |
| 2 | 환경 설정 | env/config/secrets — 변수명·용도·발급처 |
| 3 | 입출력 계약 | 함수/API/이벤트 — 파라미터·응답 형식 |
| 4 | 핵심 알고리즘·조건 | 판단 기준·수치·예외 처리 |
| 5 | 실행 환경 | 스케줄·배포·런타임 — 주기·트리거·실패 처리 |

> finance 면 #1·#3 을 **finance db(ODBC) 실제 테이블 스키마·컬럼명·타입**으로 확정한다(추정 금지).
> 결과를 표로 출력(항목·판정·내용) 후 Phase 4 진입.

---

## 8. Phase 4 — 실행 엔진 + progress.md

4단계:

**(1) Worker Handoff Check**: 수정할 함수명 + 파일:줄번호 / 변경 전후 동작 차이 / 신규 모듈 공개 API /
핵심 판단 조건. Ready / ⚠️보완 판정(보완은 Opus 즉시 수행).

**(2) 실행 엔진 라우팅**: portable 동반 엔진은 `harness` 단일이다.
- **harness 사용**: 순차 + 검증 필요 / 핵심 로직 변경 / 신규 연동 / 회귀 위험 / DB·상태 변경
- **직접 실행**: 위에 해당 없는 단순·독립 작업은 Supervisor(Opus)가 직접 또는 단일 Agent 로 처리
- (button 의 코딩wf·경량화 3-way 는 portable 미포함 → 위 2택으로 단순화)

**(3) progress.md 생성** (실행 엔진 진입 게이트 전제 — 누락 시 차단). 각 step 은 `model: X` **또는**
`wf: harness` 정확히 하나(XOR):
```markdown
- [ ] Step 1: {설명} (model: sonnet)
- [ ] Step 2: {설명} (model: opus)
- [ ] Step 3: {설명} (wf: harness)
```

**(4) Sonnet-executable verify** — 각 `model: sonnet` step 이 5항목을 만족하는지 확인:

| # | 내용 |
|---|---|
| 1 | 대상 파일 절대경로 1개+ |
| 2 | 수정 라인 번호 또는 함수/심볼명 |
| 3 | before/after snippet 또는 신규 코드 블록 |
| 4 | 건들지 말 경계 (의존성/side-effect) |
| 5 | 완료 판정 기준 1줄 (검증 방법) |

1-2 누락 → 자가 보완 / 3+ 누락 → `model: opus` 재분류 + plan.md 수정. 엔진 배정을 plan.md 최상단
`## 실행 엔진 확정` 블록에 기록(압축 내성) + `<!-- PHASE-4-COMPLETE: {ISO timestamp} -->` 마커.

---

## 9. 조사 소스 추상화 (3-소스)

button 원본은 외부 자문 스킬(search-engine·cross-verify)에 의존했으나, portable 은 환경에 맞는 소스를
직접 고른다. **판정 한 줄**: "데이터가 있나/값?" → db / "왜 이렇게 정했나?" → 메모 / "외부 표준·신규?" → 웹.

| 소스 | 도구 | 쓸 때 | 주요 Phase |
|---|---|---|---|
| 외부 웹 | `WebSearch` / `WebFetch` (네이티브) | 외부 표준·신규 기법·규정·경쟁앱 | 0, 1-2b, 2 |
| finance db | ODBC 조회 | 데이터 실재·값 범위·테이블 스키마 | 0(실현가능성), 3(입출력 계약) |
| 메모 | 회의록·메일·메시지 수집본 검색 | 과거 의사결정 맥락·합의 배경 | 0α(전략), 1(다관점) |

**환경 고유 부분은 아래 설정 지점에 채운다** (다른 PC 적용 시 여기만 수정):
```
# === 사내 데이터 소스 설정 지점 (환경별로 채움) ===
# finance db (ODBC):
#   예) python -c "import pyodbc; cn=pyodbc.connect('DSN=...;UID=...;PWD=...'); ..."
#   또는 환경에 준비된 db 조회 MCP / 스크립트 경로
# 메모 (회의록·메일):
#   예) grep -r "<키워드>" <메모_수집_디렉토리>
#   또는 메모 검색 MCP / 인덱스 경로
# ================================================
```

조사 소스를 쓴 경우 plan.md 위험도 테이블에 **출처(웹 URL / db 쿼리 / 메모 파일)**를 명시한다.

---

## 10. 사용자 대화 지점

각 Phase 완료 후 결과 공유 + 다음 Phase 진행은 **AskUserQuestion** 으로(remote Guard 없으므로 그냥 사용).

| Phase | 대화 규칙 |
|---|---|
| 0α | `debate` 위임 — verdict 결과만 plan.md 반영 |
| 0~1 | 반복 가능 (사용자 피드백 → 재설계) |
| 1 내부 Agent Team | 필수 (스킵 시 Phase 2 진행 불가) |
| 1-2b 조사 | 조건부 (트리거 없으면 SKIP) |
| 2~3 | 자율 실행 (조사/검증 결과만 보고) |
| 3 | 항상 실행 (plan.md 기존 항목 자동 PASS) |

사용자가 "매 Phase 확인 받아" 명시하면 자율 실행 원칙 대신 사용자 선택 우선.

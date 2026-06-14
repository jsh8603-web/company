# 범용 카드 Flow 엔진 + 고정비 FP&A — 마스터 빌드 스펙 (구현 가능 수준)

> 수신자: 회사 로컬 Claude Code. 전제: Outlook COM 송수신, Teams 송수신, SharePoint, BGE RAG 인입, 개별 헤드리스 호출 가능 — 모두 구동 확인됨.
> 런타임 의존성: **stdlib + sqlite3 + openpyxl(+et_xmlfile)만**. pandas/numpy/pydantic/dbt/GE/jsonschema 라이브러리 설치 금지(검증은 stdlib 재구현).
> 이 스펙은 범용 카드 flow 엔진을 정의하고, 고정비 fcst/실적 모델을 그 엔진의 **첫 번째 적용**으로 싣는다. 선행 `fpna-fixed-cost-tables` 스킬은 테이블 셋 생성기로 호출된다.
> 실행: Opus로 `plan.md` 작성·승인 → Sonnet 구현. 시드 플레이북 3개로 범용성 증명 후 확장.

===== PROMPT START =====

# 구축 지시: 범용 카드 Flow 엔진 (고정비 FP&A 첫 적용)

## 0. 설계 척추 (불변)

1. **세 종류 카드, 전부 사람 게이트로 생성.** 신뢰 수준이 다르다:
   - **Playbook 카드** = 메타층. "이 클래스의 일은 이렇게 처리하라." 일하는 법 자체. 시드 + 생성(제안), 항상 사람 승인.
   - **Decision 카드** = 인식론적. "무엇을 믿는가"(데이터+신뢰도+출처). 기계검사+신뢰도+무출처금지 게이트 통과 시 자동반영, 아니면 검토.
   - **Task 카드** = 행위적. "무엇을 하는가"(부작용 동반). **항상** 사람 승인, 자동실행 절대 없음.
2. **읽고 믿는 것은 조심스레 자동화 가능, 행동·규칙변경은 자동화 불가.** 이게 거버넌스의 단일 컷.
3. **자기확장 = 플레이북 생성.** 새 task 종류 → 매칭 플레이북 없음 → `propose_playbook` 자동 방출 → 사람 승인 → 능력 추가. 추상 엔진을 선설계하지 않고, 플레이북이 늘며 범용해진다.
4. **삭제 없음, deprecate/retract만.** 모든 카드·상태전이·실행은 append-only + bitemporal(valid_time/transaction_time) + PROV 계보. 하드 삭제 금지.
5. **숫자의 소스 오브 트루스 = 구조화 마스터/ledger.** RAG는 검색·계보용. 외부 발신은 인입 트리거에서 절대 자동 발화 안 됨.

## 1. 핵심 엔티티

- **work_item**: 외부에서 들어온 처리 단위(메일 회신, 계약 파일, 노트 등). dedup_key로 멱등.
- **playbook**: work_item 클래스 → 처리 절차 매핑. 버전드.
- **work_order**: work_item × playbook 결합(1회 실행 단위). 헤드리스 워커가 소비.
- **decision_card / task_card**: 워커의 출력. 위 신뢰 규칙대로 게이트.
- **assumption_ledger + evidence_event**: fcst 라인별 가정·근거 원장(append-only).
- **request_register**: 내가 보낸 자료요청과 회신 상관(correlation)·기한.
- **audit_log**: 전 구간 append-only 계보.

## 2. 범용 Flow (닫힌 루프, end-to-end)

```
[감지 watcher(LLM無)] 
   → 정규화 → work_item INSERT(dedup)            # §5
[router: 스케줄 드레인]
   → work_item을 active playbook에 매칭            # §6
      ├ 매칭O → work_order 생성 → dispatch
      └ 매칭X → task_card{propose_playbook} 방출 → work_item=awaiting_playbook
[worker: work_order당 헤드리스 Claude Code 1회]
   → 플레이북 절차 실행(+RAG/ledger 컨텍스트)       # §7
   → JSON으로 decision_cards[] / task_cards[] 반환(stateless)
[gates]                                            # §8
   ├ decision → 스키마+신뢰도+출처 → 통과:applied(ledger) / 실패:review
   ├ task     → 항상 pending_approval(승인 큐)
   └ propose_playbook → 항상 playbook 승인 큐
[approval & execution: 사용자가 큐 비움 / 드레인이 승인분 실행]  # §9
   ├ decision 승인 → ledger 반영
   ├ task 승인 → executor 부작용 실행(멱등·로그) → 새 work_item 생성 가능 ↺
   └ playbook 승인 → status=active → awaiting_playbook work_item 재라우팅 ↺
[audit/lineage 전 구간 append-only + PROV]          # §12
```

## 3. 데이터 모델 (sqlite3, WAL 모드)

```sql
CREATE TABLE work_item(
  id INTEGER PRIMARY KEY, dedup_key TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL,                 -- outlook|sharepoint|teams|note|internal
  raw_ref TEXT NOT NULL,                -- EntryID/driveItemId/path (본문 아님, 포인터)
  correlation_token TEXT,              -- [REQ-xxxx] 또는 ConversationID
  received_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|routed|awaiting_playbook|processing|done|failed|dead
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL);

CREATE TABLE playbook(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|proposed|active|deprecated
  trigger_spec TEXT NOT NULL,            -- json: 매칭 피처/조건
  procedure_ref TEXT NOT NULL,           -- repo 내 플레이북 파일 경로
  allowed_emits TEXT NOT NULL,           -- json: 허용 decision/task 타입 화이트리스트
  gates TEXT NOT NULL,                   -- json: 신뢰도 임계 등
  provenance_required INTEGER NOT NULL DEFAULT 1,
  supersedes INTEGER, author TEXT, approved_by TEXT, approved_at TEXT, created_at TEXT NOT NULL,
  UNIQUE(name, version));

CREATE TABLE work_order(
  id INTEGER PRIMARY KEY, work_item_id INTEGER NOT NULL, playbook_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'dispatched', -- dispatched|running|completed|failed
  worker_run_id TEXT, started_at TEXT, finished_at TEXT,
  FOREIGN KEY(work_item_id) REFERENCES work_item(id),
  FOREIGN KEY(playbook_id) REFERENCES playbook(id));

CREATE TABLE decision_card(
  id INTEGER PRIMARY KEY, work_order_id INTEGER NOT NULL,
  target_ref TEXT NOT NULL,              -- fcst line / contract field / ledger key
  claim TEXT NOT NULL,
  direction TEXT NOT NULL,               -- strengthen|weaken|contradict|supersede|new
  value_impact TEXT,                     -- json
  confidence REAL NOT NULL, provenance TEXT NOT NULL,  -- json source uris (필수)
  schema_ok INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'proposed', -- proposed|review|applied|superseded|retracted
  valid_time TEXT NOT NULL, transaction_time TEXT NOT NULL, applied_at TEXT,
  FOREIGN KEY(work_order_id) REFERENCES work_order(id));

CREATE TABLE task_card(
  id INTEGER PRIMARY KEY, work_order_id INTEGER,
  task_type TEXT NOT NULL,               -- send_request|send_reminder|save_attachment|write_fcst|post_teams|propose_playbook|...
  payload TEXT NOT NULL,                 -- json (발송 본문/대상/플레이북 초안 등)
  idempotency_key TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed', -- proposed|pending_approval|approved|executing|done|failed|rejected|expired
  approved_by TEXT, approved_at TEXT, executed_at TEXT, result TEXT, expires_at TEXT, created_at TEXT NOT NULL,
  FOREIGN KEY(work_order_id) REFERENCES work_order(id));

CREATE TABLE assumption_ledger(
  line_id TEXT PRIMARY KEY, fcst_value REAL, basis TEXT,
  confidence REAL, status TEXT,          -- confirmed|provisional|stale|contradicted|superseded
  next_review_date TEXT, owner TEXT, updated_at TEXT);

CREATE TABLE evidence_event(             -- append-only
  id INTEGER PRIMARY KEY, line_id TEXT NOT NULL, decision_card_id INTEGER,
  direction TEXT NOT NULL, weight REAL, source_uri TEXT NOT NULL,
  valid_time TEXT NOT NULL, transaction_time TEXT NOT NULL,
  FOREIGN KEY(line_id) REFERENCES assumption_ledger(line_id));

CREATE TABLE request_register(
  request_id TEXT PRIMARY KEY, fcst_line TEXT, owner TEXT, requested TEXT,
  due_date TEXT, correlation_token TEXT, status TEXT,  -- drafted|sent|fulfilled|overdue|escalated
  created_at TEXT NOT NULL);

CREATE TABLE audit_log(                  -- append-only, 하드삭제 금지
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, -- system|user|worker
  entity_type TEXT, entity_id TEXT, action TEXT, from_state TEXT, to_state TEXT,
  detail TEXT, prov_links TEXT);
```

## 4. 상태기계 (허용 전이만)

- **work_item**: pending→routed→processing→done | →awaiting_playbook→(playbook 승인)→routed | processing→failed→(재시도)→processing | failed→dead.
- **playbook**: draft→proposed→active→deprecated. (active는 동일 name 내 1버전만; 새 버전 active 시 이전 버전 deprecated, supersedes 기록.)
- **decision_card**: proposed→(gate)→applied | proposed→review→applied/retracted | applied→superseded.
- **task_card**: proposed→pending_approval→approved→executing→done | →failed→(재시도 제한) | pending_approval→rejected | pending_approval→expired.
- **work_order**: dispatched→running→completed | →failed.
모든 전이는 audit_log에 from_state/to_state 기록.

## 5. 감지 (watcher, LLM 없음) — 현실적 결정론

결정론은 *인입 분류*가 아니라 *내가 보낸 발신의 상관키*에 둔다.
- **Outlook**: 전용 폴더를 **워터마크 폴링**(마지막 처리 ReceivedTime 이후만). 회신 상관 = **ConversationID** + RFC `In-Reply-To`/`References` + 제목 토큰 `[REQ-xxxx]`. dedup_key = **InternetMessageId**(폴더 이동에도 불변). 첨부는 콘텐츠 해시.
- **SharePoint**: webhook 구독 가능하면 사용, 아니면 Graph delta/폴링. dedup = driveItemId+eTag.
- **Teams**: 데이터 회신 경로에서 제외(스레딩·첨부 약함). 알림·독촉·ack 전용. 인입은 기껏 "언급됨" 검토 항목만.
- **본인 노트/음성 전사**: 작성 시 태깅 → source=note, 결정론.
- 모든 감지는 **dumb**: 정규화 후 work_item INSERT(dedup 위반 시 무시)만. LLM 호출 없음.

## 6. Router & 디스패치

스케줄 드레인(Windows Task Scheduler, N분; 항상 떠 있는 프로세스 불필요)이 매 회차:
1. watcher 폴링 → work_item enqueue.
2. pending work_item 매칭:
   - **결정론 피처 우선**: correlation_token이 open request와 매칭 → 해당 클래스 플레이북. source+경로 규칙(예: /contracts) → 계약 플레이북.
   - **폴백 의미매칭**: 플레이북 trigger_spec 설명에 대해 **LanceDB/BGE 검색(기존 DA 검색 재사용)**. top score ≥ 임계 → 매칭, 미만 → **매칭 실패**.
   - 매칭 → work_order 생성, work_item=routed→processing.
   - 매칭 실패 → `propose_playbook` task_card 방출, work_item=awaiting_playbook.
3. dispatched work_order를 헤드리스 워커로 실행(직렬 1워커 권장; 병렬 시 line_id 파티션).
4. 만료 task_card expire, failed work_item 백오프 재시도(상한 초과→dead + 검토).

## 7. Worker 계약 (헤드리스, 항목당 1회, stateless)

- 입력 envelope(JSON): work_order, work_item(raw_ref로 본문/첨부 로드), 매칭 playbook(procedure_ref 로드), 검색 컨텍스트(RAG/ledger 관련분), allowed_emits 화이트리스트.
- 절차: 플레이북 procedure를 따른다(자유행동 금지). 부작용 직접 수행 금지 — **부작용은 전부 task_card로 제안만**.
- 출력(JSON, 엄격): `{decision_cards:[...], task_cards:[...], notes, status}`. allowed_emits 밖 타입 방출 시 work_order=failed.
- 상태는 전부 DB/파일. 워커는 무상태. execution-log.jsonl append.

## 8. 게이트

- **Decision 게이트**: ① stdlib JSON Schema 검증(target_ref/claim/direction/confidence/provenance 필수) ② confidence ≥ 플레이북 임계 ③ **provenance 비어있으면 강화 불가**(무출처 confidence 상승 0). 셋 다 통과 → applied(ledger 반영 §9). 하나라도 실패 또는 direction=contradict → review 큐.
- **Task 게이트**: 무조건 pending_approval. 예외 없음.
- **Playbook 게이트(propose_playbook)**: 초안을 playbook(status=proposed)로 적재 + playbook 승인 큐. 사람이 편집·승인해야 active.

## 9. 승인 & 실행

- 큐 3종(콘솔/CLI 뷰, SQLite 위): decision-review, task-approval, playbook-approval. 사용자가 매일 비움. 드레인이 승인분을 실행.
- **executor(부작용, 각 멱등·로그)**: task_type별 핸들러.
  - `send_request`/`send_reminder`: Outlook COM 발송(초안은 이미 작성됨, 승인이 발송으로 전환). 본문에 "메일 첨부로 회신" 문구 + `[REQ-xxxx]` 토큰 고정. request_register 갱신.
  - `save_attachment`: COM 첨부 → SharePoint 저장 + 해시 dedup + RAG 등록 + request fulfilled.
  - `write_fcst`: 선행 스킬 호출해 openpyxl 모델 기록(evidence health 컬럼·가정변경 bridge 포함).
  - `post_teams`: Teams 알림/독촉.
  - `propose_playbook`: 외부 부작용 없음(승인이 곧 사람 저작). 승인 시 playbook active → awaiting_playbook work_item 재라우팅.
- 멱등: executor는 idempotency_key 선확인(중복 발송·중복 쓰기 차단). 실행 결과 result에 기록, 실패 시 재시도 상한.
- 실행이 새 work_item 생성 가능(루프 폐쇄): 예) send_request 실행 → 이후 회신 인입이 새 work_item.

## 10. 플레이북 파일 포맷 (repo, 버전드 YAML+MD)

```yaml
name: inbound_reply_to_request
version: 1
trigger_spec: { source: [outlook], requires_correlation: true, description: "내가 보낸 자료요청에 대한 회신 처리" }
allowed_emits:
  decision: [contract_field, fcst_assumption]
  task: [save_attachment, write_fcst, send_reminder, propose_playbook]
gates: { decision_confidence_min: 0.7, provenance_required: true }
procedure: |   # 워커가 따르는 단계(요지). 구체 지시는 동봉 .md.
  1) 회신을 request_register의 [REQ] 토큰으로 상관.
  2) 첨부가 반환 양식(JSON Schema) 통과하는지 기계검사. 실패→ send_reminder task 제안 + review.
  3) 통과→ save_attachment task, 추출→ decision_card(direction 판정), write_fcst task 제안.
```

**시드 플레이북 3개(+메타 1개)**:
- `inbound_reply_to_request` (위)
- `contract_ingest` — SharePoint 계약 PDF → 마스터 필드 추출(decision) + 누락 필드 → send_request task.
- `overdue_escalation` — request_register overdue 스캔 → send_reminder(메일)+post_teams task(묶음·횟수 상한).
- `playbook_gap_handler`(메타) — 매칭 실패 work_item 패턴에서 신규 플레이북 초안 작성 → `propose_playbook` task.

## 11. 자기확장 메커니즘 (명시)

새 종류의 일 도착 → §6 매칭 실패 → router가 `playbook_gap_handler`로 라우팅 → 워커가 패턴 분석해 플레이북 초안 + `propose_playbook` task 방출 → 사람이 playbook-approval 큐에서 검토·편집·승인 → playbook active → awaiting_playbook work_item 재라우팅되어 처리. **시스템은 코드 변경 없이 플레이북 추가만으로 새 업무 클래스를 흡수**한다. 모든 확장은 사람 게이트를 통과한다.

## 12. 감사 / 계보 / bitemporal

- 모든 카드·전이·실행 → audit_log append. 하드삭제 금지: "삭제"=deprecate(playbook)/retract(decision).
- bitemporal: decision/evidence는 valid_time(사건)·transaction_time(기록) 분리 → "board pack 시점에 이 라인을 무엇으로 믿었나" 재구성.
- 계보: fcst 숫자 → assumption_ledger → evidence_event → source_uri → 원문서까지 클릭 추적(PROV Entity/Activity/Agent 매핑).

## 13. 모듈 구조

```
card-flow/
  db/            schema.sql, migrations, sqlite WAL 핸들
  detect/        outlook_poll.py, sharepoint_delta.py, teams_notify.py, note_tag.py  (dumb)
  router/        match.py(결정론 피처+LanceDB 폴백), drain.py(Task Scheduler 진입점)
  worker/        run.py(헤드리스 호출 래퍼), envelope.py, output_contract.py
  cards/         playbook.py, decision.py, task.py  (상태기계)
  gates/         json_schema.py(stdlib 재구현), decision_gate.py, task_gate.py
  execute/       executor.py + handlers/{send_request,save_attachment,write_fcst,post_teams,propose_playbook}.py
  ledger/        assumption.py, evidence.py(append-only), variance bridge 연동
  playbooks/     *.yaml + *.md (시드 3+메타1)
  audit/         log.py, prov.py
  queues/        review/approval/playbook 콘솔 뷰
  vendor/        openpyxl + et_xmlfile
  CLAUDE.md      3카드 신뢰컷 + 게이트 + "발송 무조건 승인" + bitemporal 요약(10줄)
```
선행 `fpna-fixed-cost-tables` 스킬은 `execute/handlers/write_fcst`에서 호출.

## 14. 레퍼런스 (개념·표준 차용, 설치 금지)

- **W3C PROV — https://www.w3.org/TR/prov-overview/** : §12 계보 모델(Entity/Activity/Agent).
- **Fowler, Event Sourcing — https://martinfowler.com/eaaDev/EventSourcing.html / Bitemporal — https://martinfowler.com/articles/bitemporal-history.html** : §3·§12 append-only·이중시간.
- **JSON Schema — https://json-schema.org/** : §8 기계검사(stdlib 재구현).
- **Kimball / dbt-utils — https://github.com/dbt-labs/dbt-utils** : write_fcst가 부르는 테이블 셋의 grain·관계 단언(선행 스킬에서).
- (방법론 연속성) 사내 DA(316 YAML) + LanceDB/BGE 검색 → §6 플레이북 의미매칭 재사용. WeightAssumptionCard 생명주기 → §2 decision/evidence 규율.
- 근거 기준: 자기확장 워크플로(자료요청·독촉)는 캐논 repo가 아니라 계보·이력·스키마 표준(W3C PROV·트랜잭셔널 outbox·SoD)에 근거를 둔다.

## 15. 수용 기준 (테스트 가능)

- **결정론 인입**: `[REQ]` 토큰+ConversationID 보유 회신만 자동 work_order, 미보유/스키마 실패는 review 큐. dedup으로 동일 회신 2회 처리 0.
- **게이트**: 무출처 decision의 confidence 상승 0건. 모든 task_card는 pending_approval 경유(자동실행 0건). allowed_emits 위반 방출 시 work_order failed.
- **자기확장**: 미매칭 work_item → propose_playbook 자동 생성 → 승인 후 동일 work_item이 새 플레이북으로 처리됨(엔드투엔드 1케이스 골든).
- **멱등**: 동일 idempotency_key 재실행 시 중복 발송·중복 쓰기 0.
- **계보**: 임의 fcst 숫자에서 원문서까지 클릭 추적. deprecate/retract 후에도 과거 시점 신념 재구성 가능.
- **fcst 출력**: evidence health 컬럼, stale/contradicted 플래그, 가정변경 bridge 레인(선행 스킬 View Contract v2 통과).
- 네트워크 차단·재부팅 후 드레인 재개 시 pending 유실 0.

## 16. 실행 순서

`plan.md` 먼저 작성·승인: 전체 DDL, 상태기계 전이표, worker 입출력 계약, JSON Schema 예시, 시드 플레이북 4개 본문, executor 핸들러별 멱등키 설계, 승인 큐 UX, audit/PROV 스키마, 선행 스킬 연동 지점. **특히 "어느 task_type을 반자동 허용할지"의 기본값(초기 전수 수동 권장)을 plan에서 내 승인**. 승인 후 Sonnet으로 db→cards→gates→detect→router→worker→execute→queues→playbooks(시드3+메타1) 순 구현, 마지막에 자기확장 골든 1케이스로 닫는다.

===== PROMPT END =====

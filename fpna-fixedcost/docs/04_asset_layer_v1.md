# 자산·데이터 레이어·버전 관리 플랜 — 카드 Flow 엔진 동반 (구현 가능 수준)

> `card_flow_engine_master_spec.md`의 동반 문서. 마스터 스펙의 테이블·핸들러에 그대로 꽂힌다.
> 저장소 역할 고정: **SharePoint = 데이터(민감)**, **git repo = 프로그램(플레이북·스키마·템플릿·코드)**, **SQLite = 제어 평면(카드·큐·감사)**, **BGE RAG/LanceDB = 색인(파생, 재생성 가능, 진실의 출처 아님)**.
> 원칙 계승: append-only · bitemporal · 하드삭제 금지 · PROV 계보 · stdlib만.

===== PLAN START =====

# 자산 / 레이어 / 버전 관리 플랜

## 1. 데이터 레이어 4층 (저장 티어)

| 층 | 내용 | 가변성 | 저장 | 진실성 |
|----|------|--------|------|--------|
| **L0 Raw/Landing** | 캡처된 원본(계약 PDF, 메일·첨부, 전사) | **불변(write-once)** | SharePoint `raw/` + sha256 | 근거 substrate |
| **L1 Extracted** | 타입 박힌 구조화 추출(JSON) | 재생성 가능 | SharePoint `extracted/` | L0 계보 보유 |
| **L2 Curated/Ledger** | assumption_ledger, evidence_event, 차원 마스터 | **append-only(bitemporal)** | SQLite + tidy export | 믿는 진실 |
| **L3 Serving/Report** | fcst 워크북, board pack | 불변(발행 후) | SharePoint `reports/` | 재생성 가능 |

규칙: L0는 절대 변형 안 함. L1~L3는 하위로 내려갈수록 **재빌드 가능**. 숫자의 소스 오브 트루스는 L2. RAG는 L0+L1에서 파생된 색인일 뿐 언제든 재구축.

직교 저장: **SQLite**(카드·큐·감사 = 제어 평면, 레이어 아님), **repo**(플레이북·스키마·템플릿·코드 = 메타/프로그램 자산).

## 2. 폴더 토폴로지 (구체 경로)

**SharePoint (데이터, 민감도별 권한)**
```
/fpna-fixedcost/
  raw/<source>/<yyyymm>/<sha256>.<ext>          # L0 불변 원본
  raw/<source>/<yyyymm>/<sha256>.meta.json       # provenance 사이드카(출처·수신·해시·민감도)
  extracted/<doctype>/<sha256>__<extractor_ver>.json   # L1
  curated/exports/<table>__<txn_time>.csv        # L2 tidy 스냅샷(감사·외부 피벗용)
  outbox/<request_id>/<draft_id>.json            # L0.5 발신 초안(승인 전, 발송 후 보존)
  reports/<as_of>/<report>__<run_id>.xlsx        # L3
  reports/<as_of>/<run_id>.manifest.json         # L3 빌드 매니페스트(§5)
```
**git repo (프로그램)**
```
card-flow/
  playbooks/<name>/v<semver>/playbook.yaml + procedure.md + fixtures/   # 플레이북 자산
  schemas/<name>__v<semver>.json                 # JSON Schema(검증 핀)
  templates/request/<doctype>__v<semver>.md       # 요청 메일 양식
  templates/return-form/<doctype>__v<semver>.xlsx # 회신 반환 양식(셀잠금)
  golden/<case>/...                               # 회귀 골든
```
**작업/스크래치**: `/work/<run_id>/` (휘발, 산출만 SharePoint로 승격).

## 3. 카드별 자산 — 수집 vs 생성

**Playbook 카드 (메타)**
- *수집*: 매칭 실패 work_item 패턴(=신규 능력의 씨앗).
- *생성*: `playbooks/<name>/v<semver>/`(yaml+md+fixtures), trigger 설명 임베딩(RAG 등록), 골든.
- *경로*: `playbook_gap_handler` → `propose_playbook` task → 사람 승인 → repo 커밋 + playbook 테이블 active.

**Decision 카드 (인식론)**
- *수집*: L0 원본(계약/메일/전사) — detection이 sha256·dedup·민감도 태깅으로 적재 + RAG.
- *생성*: L1 추출(provenance: L0 해시+페이지/조항) → 게이트 통과 시 L2 evidence_event/ledger 갱신.
- *불변식*: provenance 없으면 생성 불가. 모든 L1/L2 레코드는 상위 L0 해시로 역추적.

**Task 카드 (행위)**
- *수집*: 없음(행위 제안). 입력은 L2 상태(만기 request, 누락 필드 등).
- *생성*: 발신 초안(`outbox/`), 회신 반환 양식 인스턴스, 실행 영수증(audit), `write_fcst`의 경우 L3.
- *불변식*: 부작용 전 idempotency_key 확인, 발송본·결과 보존(재현·감사).

## 4. 버전 관리 정책 (자산 클래스별)

| 자산 | 버전 스킴 | 가변성 | 승계(supersede) |
|------|-----------|--------|------------------|
| L0 raw | 콘텐츠 주소(sha256) | 불변 | 새 파일=새 해시. 승계는 L2 마스터가 "현행 계약 버전" 포인터로 관리 |
| L1 extracted | `sha256 + extractor_ver` | 재생성 | 추출기/플레이북 변경 시 재추출(과거판 보존) |
| L2 ledger | bitemporal(transaction_time) | append-only | 덮어쓰기 없음. 신념 변경=새 evidence_event |
| L3 report | `as_of + run_id` | 발행 후 불변 | 재실행은 새 run_id. 매니페스트로 입력 고정 |
| Playbook | **SemVer**(repo) + DB status | active 1버전 | 새 버전 active 시 이전 deprecated, supersedes 기록 |
| Template(요청/반환양식) | SemVer | 불변판 | outbound가 `template_ver` 참조 → 회신은 그 버전 스키마로 파싱 |
| Schema(JSON Schema) | SemVer | 불변판 | decision/task 검증을 `schema_ver`로 핀 |

핵심: **발신 양식·검증 스키마·플레이북은 SemVer로 핀**되어, 회신이 들어왔을 때 "어느 버전 양식으로 보냈는지" 기준으로 정확히 파싱·검증된다(버전 드리프트로 인한 오파싱 차단).

## 5. 빌드 매니페스트 (재현성의 핵심)

모든 L3 산출은 매니페스트를 동반 기록한다:
```json
{ "run_id":"...", "as_of":"2026-06", "built_at":"...",
  "playbook_versions": {"contract_ingest":"1.2.0", ...},
  "schema_versions": {"fcst_assumption":"1.1.0", ...},
  "template_versions": {"lease_return_form":"2.0.0"},
  "ledger_txn_time":"2026-06-30T18:00:00",      // 이 시점 L2 신념으로 빌드
  "input_source_hashes": ["sha256:...", ...],   // 들어간 L0 전부
  "builder":"fpna-fixed-cost-tables@<ver>",
  "output_hash":"sha256:..." }
```
효과: 임의 과거 board pack을 **동일 입력·동일 신념 시점으로 비트 동일 재생성**, 그리고 "이 숫자 왜 이랬나"를 입력 해시까지 감사. (manifest 테이블도 SQLite에 미러링.)

## 6. 자산 생명주기 (수집→생성→승격→폐기)

1. **수집**: detection → L0 write-once(sha256, dedup, `.meta.json` 민감도) → RAG 등록.
2. **생성**: 워커가 L1 추출 → decision 게이트 → L2 append.
3. **승격**: 게이트 통과분만 L2 반영. report task 승인 시 L3 빌드 + 매니페스트.
4. **폐기**: 하드삭제 금지. playbook=deprecate, decision=retract, 계약=마스터에서 expired 표시 + 신규 버전 활성. 전부 이력 보존.
5. **보존(retention)**: 법적 문서(계약)는 IT 보존 정책 준수(보존창 메타에 기록, 만료 전 자동삭제 금지·검토 큐).

## 7. 거버넌스 / 민감도

- 민감도 태그 `S0(사내일반)/S1(기밀: 계약·동료 통신)`. S1은 SharePoint 권한 제한 + RAG 인덱스 접근 통제.
- 외부 네트워크 송신 0. 발신은 승인 후 Outlook COM만.
- 접근·이동·삭제(=deprecate) 전부 audit_log.

## 8. 마스터 스펙 연동 훅

- `detect/*` → L0 적재 + dedup + RAG.
- `gates/decision_gate` 통과 → L1/L2 기록(provenance 필수).
- `execute/handlers/write_fcst` → 선행 스킬로 L3 빌드 + §5 매니페스트.
- `execute/handlers/propose_playbook` 승인 → repo 플레이북 커밋(SemVer) + RAG trigger 임베딩.
- `audit/prov` → L0~L3 PROV 체인.
- DB 추가 테이블: `asset(sha256 PK, layer, path, source, sensitivity, retention_until, created_at)`, `build_manifest(run_id PK, json, output_hash)`.

## 9. 레퍼런스 (개념 차용, 설치 금지)

- **DVC — https://github.com/iterative/dvc (14k+ star)** : 콘텐츠 주소 데이터 + 파이프라인 lock 개념(§1·§5). 라이브러리는 안 씀, 모델만 stdlib 재구현.
- **Medallion(bronze/silver/gold) 레이어드 아키텍처** : §1 L0~L3 분리의 업계 표준 패턴.
- **SemVer — https://semver.org/** : §4 플레이북·템플릿·스키마 버전.
- **W3C PROV — https://www.w3.org/TR/prov-overview/** : §6 계보(마스터 스펙과 동일).
- 근거 기준: 콘텐츠 주소·매니페스트는 git/DVC 모델에 근거를 두고, 폐쇄망·stdlib 제약상 직접 구현한다.

## 10. 수용 기준

- L0는 write-once: 동일 sha256 재수집 시 중복 0, 기존 변형 0.
- 임의 L3 → 매니페스트의 입력 해시·ledger_txn_time으로 재실행 시 output_hash 동일(재현성).
- 회신 파싱은 발송 시 `template_ver` 기준으로 수행(버전 드리프트 오파싱 0).
- deprecate/retract 후에도 과거 시점 신념·과거 board pack 재구성 가능.
- S1 자산은 권한·보존창 메타 보유, 만료 전 자동삭제 0.

## 11. 실행 순서

`plan.md`에 추가: `asset`/`build_manifest` DDL, 민감도·보존 정책표, SemVer 커밋 규칙, 매니페스트 필드 확정, RAG 재색인 트리거(어떤 L0/L1 변경 시). **보존창·민감도 분류 기본값은 IT 정책 확인 후 내 승인** 받고 진행. 이후 마스터 스펙 구현에 자산층을 동시 배선.

===== PLAN END =====

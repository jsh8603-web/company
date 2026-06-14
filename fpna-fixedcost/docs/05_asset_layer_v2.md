# 자산·데이터 레이어·버전 관리 플랜 v2 — 누락 축 보완 + 정밀도 상향

> `asset_layer_version_plan.md`(v1) 증강. v1의 L0~L3 저장 레이어·폴더·매니페스트는 유지하고, 그 위를 덮는 **7개 축**을 추가하고 일부 항목을 정밀화한다.
> 모든 추가 도구는 **모델만 차용**: 회사 폐쇄망·stdlib+sqlite+openpyxl 제약상 어떤 플랫폼도 배포하지 않고 최소 구현으로 재현한다.

===== PLAN v2 START =====

## 0. 갭 요약 (v1에 빠졌던 축)

| 축 | 왜 이 시스템에 필요한가 | 차용 표준/repo |
|----|------------------------|----------------|
| A. **데이터 계약(Data Contract)** | v1의 JSON Schema는 구조만. freshness·보존·소유·DQ규칙·SLA가 일급이 아님 | ODCS(Bitol/LF), datacontract.com |
| B. **데이터 품질/관측(DQ/Observability)** | 게이트 시점만 검증. 저장 자산의 침묵 실패·stale·드리프트 미탐지 | Great Expectations, Soda, Pandera |
| C. **메타데이터 카탈로그/용어집** | 자산 발견·영향분석·소유권·비즈니스 용어 정의 부재 | OpenMetadata, DataHub |
| D. **참조/마스터 데이터** | CoA·조직계층·회계캘린더·FX/CPI 등 외부소싱 SCD가 ledger와 안 섞여 관리돼야 | dbt seeds, MDM/SCD2 |
| E. **시맨틱/지표 정의** | "무엇이 고정비인가/variance 레인 정의/run-rate 식"의 의미가 코드에 묻힘 | OpenMetadata Glossary, 지표 레이어 |
| F. **레코드 관리·삭제 긴장** | append-only ledger vs PII 삭제(파기요청)·법적보존 충돌 | crypto-shredding, tombstone |
| G. **백업/DR(제어평면)** | SQLite가 상태 단일 진실 → 단일 장애점 | sqlite backup, PITR |

## A. 데이터 계약 레이어 (정밀화: JSON Schema → Data Contract)

각 L1/L2 데이터셋에 **계약 YAML**(repo, SemVer)을 둔다. ODCS 모델 차용 — 구조뿐 아니라 의미·소유·품질·SLA를 한 파일에 핀.
```yaml
# contracts/extracted__lease.v1.2.0.yaml
id: extracted__lease
version: 1.2.0
owner: fixedcost-fpna          # 책임자(C 카탈로그와 연결)
schema: [ ... ]                # 구조 (기존 JSON Schema 흡수)
semantics: { lease_term: "리스 약정 개월수", ... }   # E 시맨틱과 연결
quality:                        # B DQ 규칙(상시 검증)
  - { rule: not_null, columns: [asset_id, monthly_amount] }
  - { rule: row_count_min, value: 1 }
  - { rule: amount_ties_gl, tolerance: 0 }
service_levels:                 # 정밀도 공백 보강
  freshness: { threshold: "P35D", field: observed_at }   # 35일 넘으면 stale
  retention: { period: "P10Y", basis: "계약 법적 보존" } # F 보존과 연결
  latency:   { threshold: "PT24H" }
```
효과: outbound 발송·게이트·DQ 체크·보존이 **하나의 버전드 계약**을 참조 → 버전 드리프트로 인한 불일치 차단. 검증은 stdlib로 계약 YAML을 읽어 수행(ODCS 라이브러리 미설치).

## B. 데이터 품질/관측 레이어 (신규)

게이트(생성 시점)와 **별개로**, 저장된 L1/L2 자산에 상시 체크를 건다(GX의 Expectation 모델). 드레인이 N회차마다 실행:
- freshness(계약 SLA 위반 시 stale 플래그), completeness(누락률), uniqueness(grain 중복), range/분포(이상 금액), schema conformity(계약 위반).
- 결과는 `dq_result`에 적재 + 위반 시 **검토 큐 + 해당 fcst 라인 evidence health 강등**.
- 탐지 대상: 추출기 침묵 실패, RAG stale(재색인 누락), ledger 드리프트.
```sql
CREATE TABLE dq_result(
  id INTEGER PRIMARY KEY, asset_id TEXT, contract_version TEXT, rule TEXT,
  status TEXT,           -- pass|warn|fail
  observed REAL, expected REAL, checked_at TEXT, detail TEXT);
```

## C. 메타데이터 카탈로그/용어집 레이어 (신규, 미니)

OpenMetadata/DataHub를 배포하지 않고 SQLite 미니 카탈로그로 모델만 구현. 목적: **발견 + 소유권 + 영향분석 + 비즈니스 용어**.
```sql
CREATE TABLE catalog_asset(           -- v1 asset 테이블 확장
  asset_id TEXT PRIMARY KEY, layer TEXT, contract_version TEXT,
  owner TEXT, steward TEXT, sensitivity TEXT, description TEXT, updated_at TEXT);
CREATE TABLE glossary(                 -- E 시맨틱의 저장처
  term TEXT PRIMARY KEY, definition TEXT, physical_fields TEXT, owner TEXT, version TEXT);
CREATE TABLE lineage_edge(             -- 영향분석: 컬럼 단위
  from_asset TEXT, from_col TEXT, to_asset TEXT, to_col TEXT,
  run_id TEXT, facet TEXT);            -- OpenLineage facet 모델
```
**영향분석 쿼리**: "이 계약 변경 시 어떤 fcst 라인·보고서가 깨지나"를 lineage_edge 역방향 순회로 답한다.

## D. 참조/마스터 데이터 레이어 (신규, L2에서 분리)

거래성 ledger와 **구분**되는 외부소싱·완속변경 자산: CoA, 조직 계층, 회계 캘린더, FX/CPI/인덱스율, 거래처 마스터. 별도 소유·SCD2 관리.
```sql
CREATE TABLE reference_data(           -- SCD2(이력보존)
  ref_set TEXT, natural_key TEXT, attributes TEXT,
  valid_from TEXT, valid_to TEXT, source TEXT, version TEXT);   -- valid_to=NULL → 현행
```
규칙: **CPI/FX 등 율(rate)이 사후 정정되면** 영향 fcst는 매니페스트의 ref 버전 기준으로 재빌드(재현성 유지). 누가 CoA 매핑을 소유하는지 catalog.owner에 명시.

## E. 시맨틱/지표 정의 레이어 (신규)

비즈니스 정의를 **버전드 자산**으로: 고정/변동 판정 기준, variance bridge 레인 정의, run-rate·commitment 산식. glossary + `metric_def`에 저장하고, fcst 빌더가 코드 상수 대신 이를 참조.
```yaml
# semantics/metric__fixed_cost_variance.v1.yaml
metric: fixed_cost_variance
lanes: [contract_change, new_asset, one_time, indexation, residual]
definition: "Actual - Budget, 각 레인은 evidence_event.direction로 귀속"
owner: fixedcost-fpna
```
효과: "이 숫자가 왜 고정비인가/이 variance가 왜 일회성인가"가 코드가 아니라 **거버넌스되는 정의**로 추적된다.

## F. 레코드 관리 — append-only ↔ 삭제 긴장 (정밀화)

진짜 충돌: bitemporal **불변 ledger** vs **PII 파기요청/법적보존**. 해소 패턴:
- **PII 분리 금고**: 동료 PII·민감 본문은 evidence 체인에 직접 넣지 않고 `pii_vault`에 키로 저장, ledger엔 포인터만. 파기요청 시 **crypto-shredding**(키 폐기)로 불변 체인을 깨지 않고 PII 무효화.
- **tombstone**: 삭제는 레코드 제거가 아니라 tombstone 마킹(이력·계보 보존).
- **legal hold**: 보존창 내 자산은 파기 차단 플래그, 만료 전 자동삭제 0(검토 큐 경유).
```sql
CREATE TABLE pii_vault(token TEXT PRIMARY KEY, ciphertext BLOB, key_id TEXT, shredded INTEGER DEFAULT 0);
```

## G. 백업/DR — 제어평면 (신규)

SQLite가 카드·큐·ledger의 단일 진실 → 보호 필수.
- WAL 체크포인트 + 주기 스냅샷: `VACUUM INTO`/온라인 백업 API로 시점 백업을 SharePoint 보존 경로에.
- L3는 매니페스트로 이미 재현 가능(§v1-5) → 백업 우선순위는 L0(불변 원본) + SQLite 제어평면.
- 복구 리허설을 수용 기준에 포함.

## H. 정밀화 — 계보를 PROV → OpenLineage facet 모델로

v1의 PROV 계보를 **OpenLineage run/job/dataset + facet**으로 구체화. 워커 1회 실행 = run, 플레이북 = job, L0~L3/참조 = dataset. facet에 schema·dataQuality·columnLineage를 첨부(커스텀 facet은 `_schemaURL`로 버전). 이로써 영향분석(C)과 계보가 같은 모델로 통일된다.

## 검증 레퍼런스 표 (2026 기준 — 전부 모델 차용, 미배포)

| 표준/repo | 상태·규모(2026) | 라이선스 | 주소 | 차용할 모델 |
|-----------|----------------|----------|------|-------------|
| **ODCS (Bitol/LF)** + datacontract.com | Linux Foundation 표준(PayPal 기원) | Apache-2.0 / MIT | github.com/bitol-io/open-data-contract-standard · datacontract.com | A: 구조+시맨틱+소유+DQ+SLA(freshness/retention) 한 계약에 |
| **OpenLineage** + Marquez | LF AI&Data **graduate** | Apache-2.0 | github.com/OpenLineage/OpenLineage · openlineage.io | H/C: run/job/dataset + facet, 컬럼 계보, `_schemaURL` 버전 |
| **OpenMetadata** | ~13.9k★, LF, 주간 릴리스, MCP 서버(1.12) | Apache-2.0 | github.com/open-metadata/OpenMetadata | C/E: 카탈로그·용어집·observability·소유 |
| **DataHub** | ~11.9k★, LinkedIn 기원 | Apache-2.0 | github.com/datahub-project/datahub | C: 컬럼 계보·70+ 커넥터 메타모델 |
| **DVC** | 15k+★, **2025.11 lakeFS(Treeverse) 인수** | Apache-2.0 | github.com/treeverse/dvc · dvc.org | 버전: 콘텐츠 주소 메타파일 + 파이프라인 lock |
| **lakeFS** / **Dolt** | lakeFS ~5.4k★ / Dolt=버전드 SQL | Apache-2.0 | github.com/treeverse/lakeFS · github.com/dolthub/dolt | Dolt: SQLite 제어평면 branch/merge/diff 시사 |
| **Great Expectations** / Soda / Pandera | GX ~9–10k★ | Apache-2.0 | github.com/great-expectations/great_expectations | B: Expectation(freshness/completeness/uniqueness/range/schema) + 결과 문서 |
| (v1 유지) PROV·SemVer·Kimball/dbt-utils·Medallion | — | — | (v1 표) | 계보·버전·차원·레이어 |

> 근거 기준: 위 플랫폼들은 MySQL/ES/객체스토어를 요구하는 무거운 스택이라 폐쇄망·stdlib 제약에서 배포하지 않고, **모델·어휘만 차용해 SQLite+stdlib로 재현**한다.

## 수용 기준 (델타)

- 모든 L1/L2 자산은 버전드 데이터 계약 보유. 계약 SLA(freshness) 위반 자산은 stale 플래그 + 검토 큐 진입.
- 상시 DQ 체크가 추출 침묵 실패·RAG stale·grain 중복을 탐지(dq_result fail → evidence health 강등).
- 임의 계약/참조 변경 시 영향 fcst 라인·보고서를 lineage_edge로 역추적 가능.
- PII 파기요청 시 crypto-shredding로 불변 ledger를 깨지 않고 PII 무효화. 보존창 내 자산 자동삭제 0.
- SQLite 제어평면 백업·복구 리허설 통과. L0+제어평면 시점 복구 가능.
- variance 레인·고정비 판정이 코드 상수가 아니라 버전드 시맨틱 정의를 참조.

## plan.md 추가 항목

A~H 각 DDL/계약 스키마, DQ 체크 카탈로그(자산별 규칙), 미니 카탈로그·용어집 시드, 참조데이터 소유·SCD2 규칙, 시맨틱 정의 파일 목록, PII 금고·crypto-shredding 키 관리, 백업 스케줄·복구 절차. **PII 분류·법적보존창·파기 정책 기본값은 IT/법무 확인 후 내 승인** 받고 진행.

===== PLAN v2 END =====

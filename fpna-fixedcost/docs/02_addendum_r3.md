# 통합 마스터 스펙 — R3 증강 (SSOT에 §7로 접합)

> `fpna_system_integrated_master_spec.md`(SSOT)에 병합. 흐름 3차 감사로 식별한 **14개 공백(§7.1–§7.14)** 을 보강하고, SSOT의 §8 레퍼런스 / §9 수용기준 / 모듈 구조를 갱신한다.
> 이번 라운드의 무게중심: **FP&A 방법론 본체(숫자를 실제로 어떻게 계산하는가)** + **NYSE 상장사 SOX/ICFR 컴플라이언스**.
> 제약 동일: stdlib + sqlite3 + openpyxl. 외부 repo는 모델만 차용.

===== ADDENDUM R3 START =====

## 0. 갭 요약

| # | 공백 | 무엇이 빠졌나 | 차용 |
|---|------|---------------|------|
| 7.1 | **fcst 투영 엔진** | 숫자를 미래로 *어떻게* 미는지 미정 | IFRS16 스케줄 역학, 드라이버 모델 |
| 7.2 | 배부 방법론 | driver 배부·2단계 풀·비교가능성 | ABC, dbt 드라이버 테이블 |
| 7.3 | 민감도/what-if | 다운사이드 케이스 부재 | FAST 모델 구조 |
| 7.4 | 발생/true-up | 발생추정 vs 실제 정산 | 회계 cutoff |
| 7.5 | 중요성 | 검토 강도 차등 부재 | ISA 320 |
| 7.6 | 출처 권위 계층 | 충돌 해소 정책 부재 | PROV authority, 데이터 계약 |
| 7.7 | 신뢰 감쇠 | 시간 기반 확신 하락 부재 | assumption-card 생명주기 |
| 7.8 | 계약 개정 감지 | 부속합의=새 버전 인식 부재 | 콘텐츠주소 버저닝(DVC) |
| 7.9 | 거래처 ER | 명칭 변형 dedup 부재 | Splink(Fellegi-Sunter) |
| 7.10 | 피드백 학습 루프 | 교정 환류 부재 | 능동학습, 골든 eval |
| 7.11 | 콜드스타트/백필 | 1일차 부트스트랩 부재 | — |
| 7.12 | 통계 이상탐지 | 규칙 너머 통계 이상치 부재 | 사내 퀀트 스택(stdlib) |
| 7.13 | **SOX/ICFR** | 통제 매트릭스·운영유효성 증거 부재 | COSO, PCAOB AS 2201 |
| 7.14 | 내러티브 생성 | 그라운딩된 CEO 코멘터리 부재 | Verifier 패턴 재사용 |

---

## 7.1 Forecast 투영 엔진 (지금까지 미명시된 "모델"의 핵심)

문제: 근거 원장은 *가정*을 저장하지만 fcst 숫자를 미래로 미는 **계산 로직**이 없었다.
보강: 고정비는 대부분 결정론적 스케줄로 투영 가능. **버전드·감사가능 투영기**를 정의:
- **상각 roll-forward**: 자산별 취득·내용연수·잔존 → 월 상각 스케줄 자동 전개(신규 CapEx 가동분 포함).
- **리스 step-up**: 계약 인상률·인덱싱 조항으로 월 임차료 전개(IFRS16 사용권자산·리스부채 동시).
- **갱신 가정**: 만기 계약은 assumption card의 갱신 가정(갱신 확률·예상 인상)으로 분기. 갱신 미확정은 provisional + 시나리오 분기.
- **commitment 소진 + run-rate**: 약정 잔액을 기간에 배분, 신규는 run-rate.
각 라인 fcst = 투영기 출력 × 활성 assumption card. 투영 로직은 코드 상수가 아니라 `projection_method` 버전드 정의 참조(시맨틱 레이어와 연결).
```sql
CREATE TABLE projection_method(name TEXT, version TEXT, kind TEXT, params TEXT, owner TEXT);  -- depreciation|lease_stepup|renewal|runrate
CREATE TABLE fcst_line_projection(line_id TEXT, period TEXT, value REAL, method TEXT, method_version TEXT, assumption_card_id INTEGER, built_at TEXT);
```
접합: SSOT §3(원장)와 §2(테이블셋) 사이. 매니페스트(§1)에 method_version 기록.

## 7.2 배부(Allocation) 방법론

문제: 공통 고정비를 cost center/분야로 배부하는 driver·기준이 미정. 기준 변경 시 비교가능성 깨짐.
보강(ABC 2단계):
- **풀→오브젝트**: 비용 풀(예: 본사 건물비)을 driver(면적·인원·사용량)로 cost object에 배부. driver 데이터는 reference_data(SCD2)로 버전드.
- **비교가능성**: 배부 기준 변경 시 **이전 기준 병행 산출**(restated basis) + 변경 사유 명시. variance bridge에 "배부기준 변경" 레인.
- **보존 invariant**: 배부 전 합 == 배부 후 합(누수 0, `assert_allocation_conserves`).
```sql
CREATE TABLE allocation_rule(pool TEXT, driver TEXT, basis_version TEXT, valid_from TEXT, valid_to TEXT, owner TEXT);
```
접합: SSOT §2 bridge/allocation 정밀화.

## 7.3 민감도 / What-if 엔진

문제: 시나리오는 차원으로 있으나 driver 파라미터 민감도(다운사이드) 부재.
보강: 투영기(§7.1)를 파라미터화 → CEO 케이스 생성. 예: 임차 인상 {3%, 5%}, 갱신 {예, 아니오}, FX ±10%. 케이스는 별도 시나리오 버전으로 산출(원장 불변), 출력에 base 대비 델타.
```sql
CREATE TABLE sensitivity_case(case_id TEXT, base_scenario TEXT, overrides TEXT, created_by TEXT, created_at TEXT);
```
접합: SSOT §2 시나리오 축 확장. 발송·자동적용 없음(분석 산출물).

## 7.4 발생주의 / True-up

문제: 발생 추정(인보이스 전 임차료·상각)과 실제 인보이스 차이 정산 부재.
보강: 기간말 발생 추정을 카드로 기록(provisional) → 실제 인보이스 인입 시 **true-up**(차이를 정산 + assumption card 확정 confirmed). 차이는 variance bridge "발생 정산" 또는 일회성 레인.
```sql
CREATE TABLE accrual(line_id TEXT, period TEXT, accrued REAL, actual REAL, trueup REAL, status TEXT, settled_at TEXT);  -- estimated|trued_up
```
접합: SSOT §6.4(마감)와 연동 — true-up은 post-close면 restatement.

## 7.5 중요성(Materiality) 프레임워크

문제: 모든 variance·가정을 같은 강도로 검토 → 비효율.
보강: 중요성 임계(절대액 + 비율) 정의 → **검토 깊이·에스컬레이션·승인 tier를 중요성으로 구동**. 미만 항목은 경량 처리(자동 통과 폭↑), 초과는 Verifier+사람 검토 강제. ISA 320 모델.
```sql
CREATE TABLE materiality(scope TEXT, abs_threshold REAL, pct_threshold REAL, period TEXT, owner TEXT);
```
접합: SSOT §6.8(승인 tier)·§6.9(eval) 구동 입력.

## 7.6 출처 권위 계층 / 충돌 해소

문제: 두 출처가 불일치할 때(메일 vs 계약) 누가 이기는지 미정 — contradict의 해소 정책 부재.
보강: **출처 authority 랭크**: 서명계약 > 공식 발주/인보이스 > 담당자 메일 > 구두/회의노트. 충돌 시 상위 authority 채택 + 하위는 evidence로 보존(폐기 아님). authority 동급 충돌만 사람 검토 큐.
```sql
ALTER TABLE evidence_event ADD COLUMN source_authority INTEGER;  -- 랭크(높을수록 권위)
```
접합: SSOT §3 방향판정에 authority 우선규칙 추가.

## 7.7 시간 기반 신뢰 감쇠

문제: 오래된 확인이 최신과 같은 confidence로 남음.
보강: assumption card confidence에 **감쇠 함수**(마지막 근거일로부터 경과 → confidence 하락). 임계 하회 시 status→stale + 재확인 Task(자료요청) 자동 제안. next_review_date와 연동.
- 감쇠는 결정론 함수(예: 반감기 파라미터, 계약성 근거는 감쇠 느리게/만기까지 유지, 구두 근거는 빠르게).
접합: SSOT §3 + §5 DQ freshness와 정렬.

## 7.8 계약 개정(Amendment) 감지

문제: 부속합의서·갱신을 신규 계약으로 오인 → 마스터 중복·스케줄 오류.
보강: 인입 계약을 기존 계약·자산과 매칭(계약번호·당사자·자산 → §7.9 ER 활용) → 매칭 시 **기존 계약의 새 버전**으로 적재(이전판 보존, supersede), 스케줄(상각·리스) 재도출, 영향 assumption card 갱신 + retraction 전파(§6.6). 신규일 때만 신규 계약 생성.
```sql
ALTER TABLE 계약마스터 ADD COLUMN supersedes_contract_id TEXT;
ALTER TABLE 계약마스터 ADD COLUMN amendment_seq INTEGER;
```
접합: SSOT §2 계약 마스터 + contract_ingest 플레이북.

## 7.9 거래처 Entity Resolution

문제: 동일 임대인·거래처가 명칭 변형으로 중복(㈜/주식회사/영문/오타).
보강: **Fellegi-Sunter 확률적 매칭**(Splink 모델, stdlib 재현): 명칭·사업자번호·주소 등 다컬럼 비교 + term-frequency 보정 → 클러스터 → canonical vendor_id. 자동 병합은 임계 이상만, 경계는 검토 큐. (Splink는 DuckDB 의존이라 미설치, 알고리즘만 구현.)
```sql
CREATE TABLE vendor_cluster(raw_name TEXT, canonical_vendor_id TEXT, match_score REAL, method TEXT, status TEXT);  -- auto|review|confirmed
```
접합: SSOT §2 거래처/자산 차원 + §5 마스터 데이터 품질.

## 7.10 피드백 → 학습 루프

문제: 사용자 교정·Task 거부가 로그만 되고 미래 행동에 환류 안 됨.
보강: 교정/거부를 신호로 → (a) 반복 패턴이면 플레이북 개정 제안(`propose_playbook`), (b) 게이트 임계 재보정 후보, (c) **골든 eval 세트에 케이스 추가**(§6.9). 환류는 전부 사람 승인(자동 임계 변경 금지). 루프: 교정 → 후보 → 승인 → 반영.
```sql
CREATE TABLE feedback(id INTEGER PRIMARY KEY, card_id INTEGER, kind TEXT, correction TEXT, proposed_change TEXT, status TEXT);  -- correct|reject|override
```
접합: SSOT §4(자기확장)·§6.9(eval) 연결 — 자기확장이 플레이북뿐 아니라 임계·골든도 학습.

## 7.11 콜드스타트 / 역사 백필

문제: 부임 1일차 빈 ledger·시드 외 플레이북 없음·기준선 없음.
보강: **부트스트랩 워크플로** — 기존 계약·자산 대장·과거 GL을 일괄 인입(L0) → 배치 추출 → 초기 assumption card 생성(provisional, 출처=기존문서) → 과거 N기간 백필로 variance 기준선 확보 → 사람 일괄 검토로 confirmed 승격. 일반 인입 플로 재사용(배치 모드).
접합: SSOT §6.5(GL 인입)·§4(플로) 재사용. 1회성 부트스트랩 플레이북.

## 7.12 통계 이상탐지 (규칙 너머)

문제: DQ는 규칙 기반(§5). 고정비 시계열의 통계적 이상치(급증·구조변화) 미탐지.
보강: 고정비 라인 시계열에 경량 통계 탐지(stdlib): robust z-score/IQR, 수준변화(level shift), 계절성 대비 이탈. 이상치 → **investigation Task 제안 + evidence health 강등**(자동 수정 아님). 보유하신 퀀트 역량(robust stats) 이식, 단 라이브러리 미설치.
```sql
CREATE TABLE anomaly(line_id TEXT, period TEXT, metric REAL, expected REAL, score REAL, method TEXT, flagged_at TEXT);
```
접합: SSOT §5 DQ에 통계층 추가, §6.7 관측과 정렬.

## 7.13 SOX / ICFR 통제 프레임워크 (NYSE 상장 — 핵심)

문제: Coupang은 NYSE 상장. 고정비는 재무제표에 흘러가니 **SOX 404 범위**. 지금 통제들이 *흩어져* 있고 통제 매트릭스·운영 유효성 증거로 정리되지 않음.
보강: 기존 장치를 **ICFR 통제로 명시 매핑**(COSO 프레임 / PCAOB AS 2201):
- **통제 매트릭스**: 각 통제(GL 대사 §6.5, SoD §6.8, 승인 게이트, 변경관리=플레이북 SemVer, 접근통제, 완전성=View Contract recon)를 리스크-통제 매트릭스로 문서화 — 통제 ID, 리스크, 빈도, 통제소유자, 증거 위치.
- **운영 유효성 증거**: append-only audit_log + 매니페스트 + dq_result + 승인 로그가 *통제가 실제 작동했다는 증거*. 통제별 증거를 자동 수집.
- **변경관리 통제**: 플레이북·스키마·투영기 변경은 SemVer + 승인 + eval 통과 = 변경관리 통제 증적.
- **SoD 통제**: 요청자 ≠ 승인자(§6.8) 위반 시 예외 보고.
```sql
CREATE TABLE control_matrix(control_id TEXT, risk TEXT, frequency TEXT, owner TEXT, evidence_query TEXT, last_tested TEXT, effective INTEGER);
CREATE VIEW control_evidence AS ...;  -- 통제별 audit/manifest/dq/approval 증거 집계
```
접합: SSOT §6.7(관측)·전 통제를 ICFR 관점으로 통합. **외부감사·내부감사 제출 가능한 증적**을 산출.

## 7.14 Variance 내러티브 생성 (그라운딩)

문제: 숫자·evidence health는 있으나 CEO용 *서술*("고정비 3%↑, 본사 임차 갱신·신규 차량 가동 주도") 자동생성 부재.
보강: variance bridge 레인 + assumption card에서 내러티브 생성. **§6.1 Verifier 재사용**: 내러티브의 각 주장이 bridge 수치·카드 근거로 뒷받침되는지 cite-back 검증 → 미지지 문장 차단. 환각 코멘터리 금지. 출력은 초안(사람 검토 후 보고).
접합: SSOT §6.1(Verifier)·§3(bridge) 결합. 발송 아님(보고 초안).

---

## 8′. 레퍼런스 추가 (SSOT §8 갱신)

| 표준/repo | 상태(2026) | 차용 |
|-----------|-----------|------|
| **Splink**(github.com/moj-analytical-services/splink, UK MoJ) | Apache-2.0, Fellegi-Sunter, 비지도, 100만건/분 | §7.9 거래처 ER(알고리즘만, DuckDB 미설치) · dedupe/Zingg 대안 |
| **COSO Internal Control** · **PCAOB AS 2201**(ICFR) | 표준 | §7.13 통제 매트릭스·운영 유효성 증거 |
| **ISA 320**(Materiality) | 표준 | §7.5 중요성 임계 |
| **Activity-Based Costing(ABC)** | 방법론 | §7.2 2단계 배부 |
| (재사용) IFRS16 · FAST · PROV · DVC · 사내 퀀트(robust stats) | — | §7.1·7.3·7.6·7.8·7.12 |

> 근거 기준: §7.1·7.3·7.6·7.7·7.10·7.11·7.14는 **FP&A 방법론·사내 패턴**에 근거를 둔다. §7.13은 표준(COSO/PCAOB)으로 기존 장치를 그 프레임에 *매핑*한다. §7.9는 외부 repo(Splink) 모델을 직접 차용한다. 폐쇄망상 무거운 의존(DuckDB/Spark)은 알고리즘만 재현한다.

## 9′. 수용 기준 추가 (SSOT §9 갱신)

- **투영**: 각 fcst 라인이 버전드 projection_method로 산출, 매니페스트에 method_version 기록, 상각·리스 스케줄 재계산 일치.
- **배부**: 배부 전후 합 일치(누수 0), 기준 변경 시 병행 산출 + bridge 레인.
- **민감도**: 케이스 산출이 원장 불변, base 대비 델타 노출, 자동발송 0.
- **true-up**: 발생 추정→실제 정산이 bridge/restatement로 추적.
- **중요성**: 미만 항목 경량 처리, 초과 항목 Verifier+사람 검토 강제.
- **출처 권위**: 충돌 시 상위 authority 채택·하위 보존, 동급만 검토 큐.
- **신뢰 감쇠**: 경과로 stale 전이 + 재확인 Task 자동 제안.
- **개정 감지**: 부속합의가 기존 계약 새 버전으로 적재(신규 중복 0), 스케줄 재도출+전파.
- **거래처 ER**: 명칭 변형 클러스터링, 임계 미만은 검토 큐(오병합 0).
- **피드백 루프**: 교정이 플레이북/임계/골든 변경 후보 생성, 자동 임계변경 0.
- **콜드스타트**: 기존 계약·GL로 초기 원장·기준선 부트스트랩.
- **이상탐지**: 통계 이상치가 investigation Task 생성(자동 수정 0).
- **SOX/ICFR**: 통제 매트릭스 + 통제별 운영 유효성 증거 자동 수집, SoD 위반 예외 보고, 외부감사 제출 가능.
- **내러티브**: 미지지 문장 0(Verifier 차단), 보고 초안만.

## 10′. plan.md 추가 + 사람 결정

추가 DDL/정의: projection_method 카탈로그, allocation_rule·driver 소유, sensitivity 케이스, accrual/true-up, materiality 임계, source_authority 랭크표, 감쇠 함수 파라미터, amendment 매칭 규칙, vendor ER 임계, feedback 환류 절차, 콜드스타트 부트스트랩 플레이북, 이상탐지 방법·임계, **SOX 통제 매트릭스(통제 ID·리스크·빈도·소유자·증거쿼리)**, 내러티브 Verifier 규칙.

**사람 승인 필수(신규)**: ① 중요성 임계(절대액·비율) ② 출처 authority 랭크 ③ 신뢰 감쇠 파라미터(근거 종류별) ④ 거래처 ER 자동병합 임계 ⑤ **SOX 통제 범위·소유자·테스트 빈도(내부감사/외부감사 합의)** ⑥ 투영 갱신 가정 정책.

구현 순서(SSOT §10에 삽입): db→...→ledger 다음에 **projection/allocation/sensitivity/accrual** → gates 다음에 **materiality·source_authority·decay** → catalog 다음에 **vendor ER·amendment** → eval 다음에 **feedback loop** → ops 다음에 **anomaly·control_matrix(SOX)** → 마지막 골든에 (d) SOX 통제 증거 골든 (e) 콜드스타트 부트스트랩 골든 추가.

===== ADDENDUM R3 END =====

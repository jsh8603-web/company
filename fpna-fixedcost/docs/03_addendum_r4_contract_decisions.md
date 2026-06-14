# 통합 마스터 스펙 — R4: 계약 중심 고정비 의사결정 (SSOT에 접합)

> SSOT(`fpna_system_integrated_master_spec.md`) + R3에 병합. 계약 중심 고정비 *의사결정*을 카드 모델에 녹인다.
> 핵심: 이 결정들은 데이터 *추출*이 아니라 **불확실성 하의 분석 + 권고**다 → 카드 분류 확장 + 버전드 분석 엔진 + 의사결정 레지스터.
> 근거: 회계·평가 표준(GitHub 아님). 엔진은 stdlib 구현(NPV/DCF는 단순 수학), *판단*(CGU 결정·IBR 선택·비교 조정)은 사람+Verifier+SOX 통제가 담당.

===== ADDENDUM R4 START =====

## 0. 프레이밍

추출 Decision 카드는 "계약 X의 임대료는 ₩Y"(사실)다. 계약 의사결정은 "이 임차는 시장 대비 12% 비싸고 갱신 시 ₩Z 절감, 80% CI [a,b]; 권고=재협상"(분석+권고)이다. 후자는:
- 계산으로 도출(추출 아님), 방법론 버전 보유,
- fcst로 흐르는 *숫자* = assumption(신뢰도+민감도),
- *행동 권고*(재협상/구매/손상인식) = Task(항상 사람 게이트),
- Verifier로 그라운딩(권고가 수치에서 실제 도출되는가),
- 생명주기 보유(트리거→분석→권고→결정→모니터).

## 1. 카드 분류 확장 — Decision Analysis 카드

기존 Decision(추출, 인식론)·Task(행위)에 **Decision Analysis**(계산·권고) 플레이버 추가.
```sql
CREATE TABLE decision_analysis(
  id INTEGER PRIMARY KEY, question TEXT,
  domain TEXT,                       -- lease_favorability|buy_vs_lease|impairment|depreciation_policy|...
  inputs TEXT,                       -- json[]: {value, source_uri, source_authority(§7.6), asof}  (provenance 필수)
  model TEXT, model_version TEXT,    -- §2 분석 엔진 버전
  result TEXT,                       -- json: {recommended_value, recommendation, alternatives}
  confidence REAL, conf_interval TEXT,
  sensitivity TEXT,                  -- json: 핵심 드라이버 × 범위 (§7.3 연동)
  materiality_band TEXT,             -- §7.5
  grounded INTEGER DEFAULT 0,        -- §6.1 Verifier
  status TEXT,                       -- draft|analyzed|recommended|decided|monitoring|stale
  linked_assumption_card TEXT,       -- fcst로 흐르는 산출(§3)
  next_review TEXT, created_at TEXT);
CREATE TABLE decision_register(       -- 결정 생명주기(append-only)
  decision_id TEXT, analysis_id INTEGER, event TEXT, actor TEXT, at TEXT);  -- triggered|analyzed|recommended|decided|monitored|retriggered
```
**불변 규칙**: ① 분석의 *숫자*는 assumption_card로 fcst에 반영(자동, 단 grounded+신뢰도+출처 통과). ② *행동 권고*는 항상 Task(승인). ③ 무출처 입력으로 권고 confidence 상승 금지. ④ 분석은 model_version을 매니페스트(§1)에 기록 → 재현·감사.

접합: SSOT §3(원장)와 §4(카드플로) 사이. 트리거(갱신 임박·손상 지표·차량 증설)가 work_item → 도메인 플레이북 → Decision Analysis 생성.

## 2. 버전드 분석 엔진 (projection_method §7.1과 동형)

엔진은 코드 상수가 아니라 버전드 정의. 판단 파라미터(할인율·CGU·비교 조정)는 사람 승인.

### 2.1 부동산 비교 엔진 (시장임대료 추정 + 유불리)
표준: RICS 비교법 + 증거 위계 + net effective rent. "지역 과거 → 신규 조건 추정" = MLA.
- 입력: 대상(입지·면적·임대조건·등급) + 비교 증거(reference_data의 지역 과거 계약). 조정(면적측정 기준, 인센티브/rent-free→net effective, 비용부담 구조, 시점).
- 산출: **시장임대료 추정 + CI**(증거 위계 가중·단일 과의존 금지), **유불리**=계약임대료 vs 시장 %, 권고(유지/재협상/이전), 재협상 목표가.
- 추정 규율: 보유하신 within-sector factor 추정 역량 이식(robust, 수축, CI) — 단 라이브러리 미설치, stdlib.
```sql
CREATE TABLE re_comparable(subject_id TEXT, comp_id TEXT, adj_factors TEXT, weight REAL, net_effective REAL, used_in_analysis INTEGER);
```

### 2.2 Lease-vs-Buy / TCO NPV 엔진 (트럭 구매·임차·리스)
표준: 세후 DCF + IFRS 16. 두 할인율 구분 — **리스부채 측정 = IBR**(리스 특정, ≠WACC), **자본 의사결정 = 허들레이트/WACC**.
- 소유 CF: capex, 감가상각 절세효과, 잔존가치, 정비·연료·보험, 처분. (TCO)
- 임차/리스 CF: IFRS 16 리스료(ROU·리스부채), 단기/소액 면제 검토.
- 산출: NPV(소유) vs NPV(리스) + 손익분기(보유 기간/주행거리) + 권고. 잔존·정비는 가정카드(불확실 → 민감도).
```sql
CREATE TABLE buy_vs_lease(asset_class TEXT, own_npv REAL, lease_npv REAL, discount_rate REAL, rate_basis TEXT, breakeven TEXT, recommendation TEXT, analysis_id INTEGER);
```

### 2.3 IAS 36 손상 엔진 (기계·설비)
표준: 회수가능액 = max(FVLCD, VIU). VIU = 세전 할인 DCF. CGU = 독립 현금유입 최소집합.
- 트리거 모니터링: 손상 지표(가동중단·시장악화·기술진부화) → 지표 발생 시 테스트(영업권/무한내용연수는 매년). §7.12 이상탐지·§5 DQ와 연동해 지표 자동 포착.
- CGU 매핑: **상향 집계 편향 차단**(감사 주의점) — CGU 결정은 사람 승인 + 근거 문서화(SOX 통제).
- 산출: 손상차손(있으면) + 핵심가정(공시 요건) + headroom + 민감도. 환입은 측정가능 개선 시(영업권 제외).
```sql
CREATE TABLE impairment_test(cgu_id TEXT, carrying REAL, fvlcd REAL, viu REAL, recoverable REAL, loss REAL, pretax_rate REAL, key_assumptions TEXT, headroom REAL, tested_at TEXT, analysis_id INTEGER);
```
- 상각 정책(IAS 16): 방법(정액/생산량비례)·내용연수·잔존·**구성요소 분리상각(componentization)**·재평가모형 — 정책은 시맨틱 레이어(§5) 버전드 정의.

## 3. 도메인별 카드화 (각 결정이 카드로 어떻게 되는가)

### 3.1 건물 임차 유불리 + 신규 추정
- 트리거: 갱신 D-X 임박 / 신규 입지 검토 → work_item.
- 플레이북 `lease_decision`: (a) 계약 추출 Decision(임대료·면적·조항) → (b) 2.1 엔진으로 시장임대료 추정·유불리·재협상 목표 → (c) **다기준 유불리 집계**: 시장대비 + 공간효율(₩/실면적 vs 총면적) + 기간 옵션가치(중도해지 가치) + 입지/접근(driver) → Decision Analysis(권고: 유지/재협상/이전) → (d) Task 제안: "재협상 목표 ₩Y' 협상안"/"비교 증거 3건 갱신 요청"(자료요청, 승인) → (e) fcst 반영: 갱신 가정 assumption(확정 전 provisional·시나리오 분기).
- 산출 숫자 = 갱신 후 임차료 fcst. 신뢰 감쇠(§7.7): 시장 추정 노후 → 재추정 트리거.

### 3.2 트럭 구매 vs 임차/리스
- 트리거: 물류센터 증설/차량 갱신 → work_item.
- 플레이북 `fleet_decision`: 2.2 엔진으로 소유 TCO vs 리스 NPV + 손익분기 → Decision Analysis(권고 + 민감도: 주행거리·잔존·금리) → Task: "구매 승인 요청"/"리스 견적 N사 요청" → fcst: 선택안의 상각/리스 스케줄을 §7.1 투영기로 전개.

### 3.3 기계·설비 상각 + 손상
- 상각: 자산 등록 시 §7.1 roll-forward 자동. 정책 변경은 Decision Analysis(정책)+승인.
- 손상: 지표 모니터(§7.12) → 발생 시 `impairment_test` 플레이북 → 2.3 엔진(CGU·recoverable·loss) → Decision Analysis(손상 ₩Z + 핵심가정 + headroom + 민감도) → **Task: 손상 분개 제안**(승인 필수, 금액 큼) → fcst·BS 반영은 승인 후. post-close면 restatement(§6.4).
- 환입도 동일 경로(영업권 제외).

## 4. 기존 서브시스템 통합 (접합 지도)

| 결정 요소 | 연결 |
|-----------|------|
| 산출 숫자 → fcst | §3 assumption_card, §7.1 투영기 |
| 행동 권고 | Task(승인), §6.8 risk_tier(손상=high) |
| 출처 충돌(계약 vs 견적 vs 추정) | §7.6 authority: 서명계약>발주/인보이스>견적>내부추정 |
| 추정 노후 | §7.7 신뢰 감쇠 → 재분석 트리거 |
| 분석 깊이 | §7.5 중요성: 미만 간이, 초과 풀 DCF+Verifier |
| 권고 그라운딩 | §6.1 Verifier: 권고가 수치에서 도출되는가 |
| 손상 지표 포착 | §7.12 이상탐지 + §5 DQ |
| 마감 타이밍 | §6.4 close/restatement(손상·true-up) |
| 다운사이드 | §7.3 민감도(headroom·손익분기·CI) |
| **SOX 통제** | §7.13: 손상·IBR·CGU·시장추정은 *중요 추정* → 핵심통제 + 핵심가정 문서화 + 경영진 편향 검토 + 감사 증적 |
| 계약 개정 | §7.8 amendment 감지 → 스케줄 재도출 |
| 거래처(임대인/리스사) | §7.9 ER |

## 5. 레퍼런스 (비-GitHub, 표준·전문기관)

| 표준/출처 | 주소 | 차용 |
|-----------|------|------|
| IFRS 16 / K-IFRS 1116 Leases | ifrs.org/issued-standards/list-of-standards/ifrs-16-leases | 2.2: ROU·리스부채·IBR(≠WACC, 개시고정·변경시 재산정)·리스기간(reasonably certain) |
| IAS 16 / K-IFRS 1016 PP&E | ifrs.org/.../ias-16-property-plant-and-equipment | 2.3: 상각방법·구성요소 분리·내용연수·잔존·재평가 |
| IAS 36 / K-IFRS 1036 Impairment | ifrs.org/.../ias-36-impairment-of-assets | 2.3: 회수가능액=max(FVLCD,VIU)·CGU·세전 DCF·지표·환입(영업권 제외)·핵심가정 공시 |
| IFRS 13 Fair Value | ifrs.org/.../ifrs-13-fair-value-measurement | FVLCD 측정 |
| RICS "Comparable evidence in real estate valuation" + Valuation Global Standards(Red Book) | rics.org | 2.1: 비교법·증거 위계·net effective rent·조정·기록유지 |
| IVS (International Valuation Standards, IVSC) | ivsc.org | 평가 기준·시장가치/시장임대료 |
| Market Leasing Assumption / Market Rent | (RE 모델링 개념) | 2.1: 미래 기간 시장임대료 추정 |
| 기업재무 NPV·lease-vs-buy·TCO (CFA Institute 커리큘럼 · Damodaran/NYU Stern) | cfainstitute.org · pages.stern.nyu.edu/~adamodar | 2.2: 세후 DCF·잔존·절세효과·허들레이트 |
| (재사용) ISA 320 중요성 · COSO/PCAOB AS 2201 | iaasb.org · pcaobus.org | §7.5·§7.13 |

> 근거 기준: 이 라운드 근거는 **회계·평가 표준·전문기관**이며 코드 repo가 아니다. 엔진 *계산*은 stdlib로 단순하고, *판단*(CGU 경계·IBR 선택·비교 조정·갱신 확률)에는 사람 승인·Verifier·SOX 통제가 붙는다(HITL 설계).

## 6. 수용 기준 (델타)

- 계약 결정은 Decision Analysis로 표현: inputs에 provenance+authority, model_version, grounded, 민감도 보유. 무출처 권고 confidence 상승 0.
- 임차: 시장임대료 추정이 단일 증거 과의존 0(증거 위계·범위), net effective 조정, 유불리·재협상 목표 산출. 행동 권고는 Task(승인).
- 트럭: 소유 TCO vs 리스 NPV + 손익분기, 리스부채=IBR/자본결정=허들레이트 구분 명시.
- 손상: 지표 트리거 자동, recoverable=max(FVLCD,VIU), CGU 결정 문서화+승인(상향집계 편향 검토), 핵심가정 공시 산출, 손상 분개는 Task(high tier·승인). 환입 영업권 제외.
- 모든 분석 model_version이 매니페스트에 기록, SOX 핵심가정 증적 자동 수집(§7.13).
- 노후 추정 재분석 트리거(§7.7), 분석 깊이 중요성 구동(§7.5).

## 7. plan.md 추가 + 사람 결정

추가 DDL/정의: decision_analysis·decision_register, 3개 엔진(re_comparable·buy_vs_lease·impairment_test) 버전드 정의, 도메인 플레이북 3개(lease_decision·fleet_decision·impairment_test), authority 랭크·중요성·감쇠 연동.

**사람 승인 필수(신규)**: ① **IBR 매트릭스**(관할·통화·기간·담보별 — 트레저리/회계 합의) ② **할인율·허들레이트** 정책 ③ **CGU 정의·경계**(감사 합의 — 상향집계 편향 통제) ④ 시장임대료 비교 증거 소스·조정 규칙 ⑤ 손상 지표 임계·테스트 주기 ⑥ 상각 정책(방법·내용연수·구성요소)·잔존가치 ⑦ 손상 분개 승인 권한(금액 임계·DOA). 특히 ③⑤⑦은 SOX 핵심통제라 내부/외부감사 합의 필요.

구현 순서(SSOT §10에 삽입): ledger·projection 다음에 **decision_analysis + 3 엔진** → catalog·semantic 다음에 **상각/CGU/IBR 정의** → ops·control_matrix(SOX) 다음에 **손상·IBR·CGU 핵심통제 증적** → 골든에 (f) 손상 결정 그라운딩 골든 (g) 임차 유불리 추정 골든 (h) buy-vs-lease 골든 추가.

===== ADDENDUM R4 END =====

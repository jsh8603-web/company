# 구현 가이드 — 고정비 리스 예측 (회사 데이터만 붙이면 동작)

이 문서 하나로 구현·배포가 끝나도록 작성했다. **로직은 전부 구현·검증됐고, 남은 일은
회사 데이터를 분석해 정해진 자리에 매핑·적재하는 것뿐이다.** 회계 기준은 US GAAP(ASC 842,
운영리스 정액). 숫자경로에 LLM 없음(결정론적).

---

## 0. 무엇이 됐고, 무엇만 남았나

**이미 됨(오프라인 검증 통과)**
- 엔진(`lease_fcst.py`): ASC 842 정액, sub_hub/mobile 분기, 모바일 권역 booster-drain,
  라이프사이클 4종(종료·손상·갱신·이전)+certainty 게이트, 신뢰밴드, 불변식 게이트,
  bitemporal(append-only+supersede+as-of), epoch 정렬, revision_bridge.
- 단가(`reb_parser.py`), 대사(`sap_recon.py`), 워커(`com_worker.py`, COM/SSPI),
  SharePoint 스키마, Power Automate 플로우, Power BI(DAX+모델), 엑셀·HTML 시안.

**남은 일 = 회사 데이터 6종 매핑(§4)**: 계약, SAP 실적, 유관부서 plan, 부동산원 CSV,
회계기준 확인, 계획정확도. 각각 "소스 → 타깃 필드 → 변환"이 §4에 표로 있다.

---

## 1. 아키텍처 (1장)

```
[계약/유관부서 입력]            [SAP 실적]
   SharePoint LeaseCards 폼        Actuals 리스트
        │ flow_event_validate          │
        ▼ (append-only)                ▼
   ┌──────────────── SharePoint Lists ────────────────┐
   │ Events(정본) · LeaseCards · Actuals               │
   │ ProjectionLines · Breaches · Bridge · PlanAccuracy │ ← 워커 출력
   └────────────────────────────────────────────────────┘
     ▲ 검증/알림(상시, Power Automate)   ▲ 읽기(Power BI)   ▲ 쓰기(간헐 Task)
                                                          com_worker.run_worker
                                                          (SSPI/COM, Graph·앱등록 없음)
                                                          Task Scheduler 야간 실행
```
- **상시부**(검증·알림) = Power Automate(M365 사용자 컨텍스트, 앱등록 불요).
- **컴퓨트** = 간헐 워커, Windows Task Scheduler가 사용자 세션에서 실행. SharePoint는
  REST `_api`+통합인증(SSPI)으로 접근(Graph 아님). 알림 보조는 Outlook COM.
- **리포팅** = Power BI(SharePoint Online 커넥터). 입력 UI는 SharePoint 기본 폼(Power Apps 미사용).

---

## 2. 파일 맵

| 파일 | 역할 | 핵심 |
|---|---|---|
| `lease_fcst.py` | 엔진(결정론) | `project_portfolio`, `revision_bridge`, `assert_invariants`, `EventStore` |
| `reb_parser.py` | 부동산원 단가 → 모바일 시장앵커 | `parse_reb_csv`, `to_cls_regions`, `mobile_market_rate`, `REGION_MAP` |
| `sap_recon.py` | SAP 실적 적재·대사·수렴 | `ActualRecord`, `SAP_GL_MAP`, `ingest_sap`, `reconcile`, `settle`, `bridge_segment` |
| `com_worker.py` | 간헐 워커(SSPI/COM) | `SharePointREST`, `OutlookCOM`, `run_worker`, `FakeSP`(오프라인 검증) |
| `sharepoint_schema.json` | 7개 리스트 정의 | Events/LeaseCards/Actuals/ProjectionLines/Breaches/Bridge/PlanAccuracy |
| `flows/` | Power Automate + Task | `flow_event_validate`, `flow_breach_notify`, `task_recompute.xml`, `run_worker_entry.py` |
| `powerbi_measures.dax`·`powerbi_model.md` | Power BI 측정값·모델·리포트 | 경영층/분석가 2페이지 |
| `selftest.py`·`pipeline_real.py`·`lifecycle_demo.py` | 검증 스크립트 | 데이터 없이 로직 증명 |
| `build_band_excel.py`→`lease_band.xlsx`·`build_dashboard*.py`→`lease_dashboard.html` | 엑셀·HTML 시안 | Power BI 레이아웃 참조 |

---

## 3. 데이터 모델 (구현자가 채울 구조)

### 3.1 LeaseCard (계약 1건 = 카드 1개)
`card.create` 이벤트의 payload. 필드와 의미:

| 필드 | 타입 | 의미 / 회사 데이터 |
|---|---|---|
| `id` | str | 카드 고유키(계약번호 기반) |
| `site_id` | str | 사이트 코드 |
| `cost_center` | str | SAP 원가중심점 |
| `facility_type` | "sub_hub"\|"mobile" | 시설 분류 |
| `region` | str | CLS 권역 |
| `classification` | "operating"\|"finance" | ASC 842 판정(대부분 operating) |
| `commencement` | "YYYY-MM-DD" | 사용가능일 |
| `term_months` | int | 계약기간(월) |
| `monthly_rent` | number | 월 임차료(정액 기준) |
| `escalation_annual` | float | 연 상승률(0.03=3%). **불규칙이면 `rent_schedule` 사용** |
| `rent_free_months` | int | 무상 개월 |
| `ibr` | float | 기본 0.04 고정(금융리스·ARO만 사용) |
| `restoration_est` | number | 원상복구 추정. **없으면 0 → ARO 라인 자동 OFF** |
| `cam_monthly` | number | 관리비 월 |
| `variable_monthly` | number | 변동임차료 월 |
| `parent_subhub` | str\|null | 모바일의 부모 sub_hub id |
| `certainty` | "confirmed"\|"uncertain" | **이것만 채우면 신뢰도/밴드 자동**(확정 0.92, 불확실 0.55) |
| `rent_schedule` | tuple | (선택) 연차별 월 임차료. 계약서가 불규칙 정액을 명시할 때. 있으면 escalation_annual 무시 |
| `drivers` | (생략 가능) | 증거 tier를 직접 줄 때만 |

### 3.2 Event kinds (append-only 정본)
| kind | payload | 용도 |
|---|---|---|
| `card.create` | LeaseCard 전체 | 카드 신설 |
| `card.amend` | {card_id, field, value} | 필드 정정/escalation(정정은 `supersedes`로 역분개) |
| `booster.create` | {region, planned_count, avg_unit_cost, start_month, dept_reliability} | 모바일 권역 plan |
| `booster.drain` | {region, count_delta, new_card} | plan→실제 캠프 전환 |
| `actual.post` | {site, gl, month, amount, doc} | SAP 실적 |
| `lifecycle` | {card_id, type:("termination"\|"impairment"\|"renewal"), month, …} | 라이프사이클 |

`lifecycle` 세부: termination{penalty}, impairment{loss, certainty}, renewal{add_months, new_rent, certainty}.

### 3.3 ProjectionLines (Power BI 단일 팩트, 워커 출력)
(AsOf, Month, Facility, GL, SourceCard, Scenario["base"\|"overlay"], Amount, Confidence).
base/overlay·세그먼트·GL·라인리지·밴드가 전부 여기서 집계된다.

---

## 4. ★ 회사 데이터 온보딩 (핵심 — 여기만 채우면 끝)

### 4.1 계약 데이터 → LeaseCards/Events
**소스**: 임대차계약서 / 계약관리대장. **타깃**: `card.create` 이벤트(=LeaseCards 행).
매핑은 §3.1 표 그대로. 규칙:
- 정액 `monthly_rent`=1차년 월 임차료, 균등% 상승은 `escalation_annual`.
  **연차별이 불규칙(계약서 명시)이면 `rent_schedule=[1년차월액,2년차,…]`** → ASC 842 정액 = Σ지급/기간으로 정확.
- 원상복구 의무가 계약에 **명시 + 추정 가능**할 때만 `restoration_est>0`(아니면 0).
- 갱신옵션: 행사가 reasonably certain이면 `term_months`에 포함, 불확실하면
  `lifecycle{type:"renewal", certainty:"uncertain"}` 이벤트로(한 줄 미포함, 밴드로만).
- sub_hub vs mobile 분류, region은 회사 시설 마스터 기준.

### 4.2 SAP 실적 → Actuals / 대사
**소스**: SAP 전표(BSEG/FAGLFLEXA 추출 또는 인터페이스 CSV). **타깃**: `Actuals` 리스트
→ 워커가 `actual.post`로 적재 후 `reconcile`.
- `ActualRecord(cost_center, site_id, sap_gl, month, amount, doc_id, posted_at)`로 정규화.
- **`SAP_GL_MAP`을 회사 실제 계정코드로 채운다**(`sap_recon.py` 상단). 예:
  `{"<임차료계정>": GL_LEASE, "<관리비계정>": GL_CAM, ...}`.
- `month`는 회계기간 'YYYY-MM' 가능 → `ingest_sap(records, store, recorded_at, epoch=EPOCH)`가
  `lf.abs_month(epoch,'YYYY-MM')`로 **포트폴리오 절대월로 변환**(투영월과 축 일치). epoch=예측 윈도우 시작.

### 4.3 유관부서 plan → booster.create
**소스**: 유관부서 권역별 신규/이전/종료 계획. **타깃**: `booster.create` 이벤트.
- `planned_count`=신규 캠프 수, `avg_unit_cost`=blend 결과(§4.4), `start_month`=개시 절대월,
  `dept_reliability`=그 권역 PlanAccuracy(§4.6)에서.
- 개수·이전·신설·종료는 **유관부서 plan 입력**이고, 비용 환산·변동 귀속은 엔진/FP&A가 한다.

### 4.4 부동산원 단가 → reb_parser → blend
**소스**: data.go.kr `15069766`(소규모상가 분기 지역별 임대료 CSV, 키 없이 다운로드 가능)
또는 오픈API(`fetch_reb_openapi`, 무료 인증키). 단위 천원/㎡.
- `parse_reb_csv(path)` → `to_cls_regions` → 권역별 천원/㎡.
- **`REGION_MAP`을 회사 권역 체계로 갱신**(부동산원 라벨 → CLS 권역).
- `mobile_market_rate(cls, region, area_m2=?, proxy_factor=?)`: 캠프 실면적과
  **proxy_factor를 캠프 실적 몇 건 vs 소규모상가로 1회 보정**(소규모상가는 1층 retail
  프록시라 말단 야적은 할인 필요, 대략 0.4~0.6).
- 시장단가 → `blend_unit_rate(market, dept_plan_단가, dept_reliability, actual=None)`.
  실적이 들어오면 actual이 이기며 수렴(`settle`).

### 4.5 회계기준 확인 → classification
**소스**: 본사(CPNG) 보고는 US GAAP(ASC 842) 고정. CLS 로컬 장부 기준(K-IFRS 1116 vs
일반기업회계기준)은 DART 감사보고서 주석으로 확인. **본 모델은 US GAAP 기준**이며 대부분
`classification="operating"`. 금융리스 해당분만 "finance"(이자에 `ibr` 사용).
IBR은 회사채AA-(예: 4.16%)−담보로 `ibr=0.04` 정적값; 운영리스 손익엔 영향 없음.

### 4.6 계획정확도 → PlanAccuracy
**소스**: 과거 유관부서 plan vs 실제(개수·단가)의 적중률을 권역별 집계(별도 잡 또는 수기).
**타깃**: `PlanAccuracy(Region, Accuracy 0..1, Samples, AsOf)`. 용도:
신뢰가중(booster `dept_reliability`)·입력 품질 피드백(Power BI). 콜드스타트는 0.5로 시작.

---

## 5. 핵심 로직 계약 (구현 시 반드시 유지)

1. **ASC 842 운영리스 = 정액**: 월 비용 = 총지급액/기간. IBR은 운영리스 손익을 바꾸지 않음
   (`_straight_line`). 무상·단계상승은 정액에 흡수.
2. **certainty 게이트**: 확정→base 한 줄, 불확실→overlay 밴드(별도). 손상·갱신 공통.
   `project_card`가 scenario("base"/"overlay")로 태깅, `aggregate(P,H,scenario)`로 분리.
3. **모바일 booster-drain**: 권역 plan = planned_count×단가. 서명되면 drain(−1) + 개별 카드(+1).
4. **신뢰도**: `card_confidence`(확정 0.92/불확실 0.55, 또는 drivers tier), booster=T3 0.60.
   밴드폭 = `band_halfwidth`(계단).
5. **불변식**: `assert_invariants`(월별 Σ GL=TOTAL, 대사 허용오차, 마감월 잠금) — 실패 시 중단.
6. **bitemporal**: 정본 append-only, 정정은 `supersedes`(역분개), `EventStore.as_of(t)`로 재현.
7. **epoch 정렬**: 시작일이 다른 카드는 `project_portfolio`가 절대월로 정렬(이전·신규캠프 정확).
8. **revision_bridge**: 직전 마감 이후 추가 이벤트별 Y1 영향 → 단가/대수/이벤트(잔차 0).
9. **워커는 Events 읽기전용**(정본 변조 금지). 파생만 기록.
10. **epoch 고정**: 워커 `epoch`=예측 윈도우 시작(고정). min(commencement) 자동추정 금지(스냅샷 간 Month 안정).
11. **멱등**: 같은 AsOf 재실행 시 파생행 삭제 후 재기록(중복 적재 방지).
12. **tickler 읽기전용**: 정액 escalation은 _payment에 이미 반영 → tickler는 rent를 amend하지 않고 '검토 일정'만 반환(이중계상 방지).
13. **actualization(마감월 고정)**: 실적 있는 **(site,gl,month) 단위로 실적 1줄**(base 제외) → 동일 site 복수 카드도 이중계상 없음. 닫힌 월은 정정에도 보고값 불변. 보고 한 줄=base+actual. Bridge는 결정(forecast) 델타만(actualization과 분리).

---

## 6. 배포 런북

1. **리스트 생성**: `sharepoint_schema.json`대로 7개 리스트 생성(Graph로 1회 또는 수기).
2. **워커 배치**: `lease_fcst.py reb_parser.py sap_recon.py com_worker.py flows/run_worker_entry.py`를
   사용자 PC(`C:\fpna\lease`)에. `pip install requests requests-negotiate-sspi pywin32`.
   `run_worker_entry.py`의 사이트 URL 수정.
3. **스케줄**: `schtasks /create /xml flows\task_recompute.xml /tn LeaseWorker`.
4. **상시 플로우**: `flow_event_validate.json`·`flow_breach_notify.json`을 Power Automate로 가져와
   사이트/Teams 채널/수신자 바인딩.
5. **회사 데이터 적재(§4)**: 계약→LeaseCards, SAP→Actuals, plan→booster, 부동산원 CSV→reb,
   PlanAccuracy. `SAP_GL_MAP`·`REGION_MAP`·`proxy_factor` 채우기.
6. **Power BI**: SharePoint Online 커넥터로 ProjectionLines/Breaches/Bridge/PlanAccuracy 연결,
   `powerbi_measures.dax` 추가, `powerbi_model.md`대로 2페이지 구성, 예약 새로고침.

---

## 7. 검증

**데이터 없이(이미 통과)** — 로직이 맞는지:
- `python selftest.py` → 불변식 37 checks, as-of 재현, tickler, 라인리지.
- `python lifecycle_demo.py` → 종료·손상·갱신·이전 + certainty + 부동산원 실값.
- `python pipeline_real.py` → 부동산원→blend→예측→SAP 대사→bridge→수렴.
- `python com_worker.py` → FakeSP로 워커 전 경로(ProjectionLines, breach).
- `python e2e_test.py` → **확장 E2E: 5개 마감 풀포트폴리오 운영, 51 checks**(fact==engine 교차검증, 멱등·epoch·actualization·bridge·relocation·AvF).
- `python edge_test.py` → **엣지 22종**(마감월 정정·부분전표·supersede체인·불규칙정액·relocation 경계 등).
- `python integration_test.py` → 흐름 무결성 8종.
- `python build_band_excel.py && python /mnt/skills/public/xlsx/scripts/recalc.py lease_band.xlsx` → 폼ula 에러 0.

**회사 데이터 적재 후** — 붙은 게 맞는지:
- ProjectionLines에 AsOf 1세트 채워짐, 월별 Σ GL=TOTAL(불변식 통과).
- 2회차 실행부터 Bridge 채워지고 Δ가 단가/대수/이벤트로 잔차 0 분해.
- Breaches가 SAP 실적 대비 허용오차+floor 위반만 잡힘.
- Power BI 경영층 페이지: 확정 Y1 + Δ + 밴드 + 정합성 표시.

---

## 8. 채울 자리 체크리스트

- [ ] `sap_recon.py` `SAP_GL_MAP` = 회사 실제 계정코드.
- [ ] `reb_parser.py` `REGION_MAP` = 회사 권역 체계, `mobile_market_rate` `area_m2`/`proxy_factor` 보정.
- [ ] `flows/run_worker_entry.py` SharePoint 사이트 URL **및 `epoch`(예측 윈도우 시작, 전 계약 이전 고정값)**.
- [ ] LeaseCards: 계약 데이터(특히 `facility_type`,`region`,`certainty`,`restoration_est`).
- [ ] Actuals: SAP 실적 인터페이스.
- [ ] booster.create: 유관부서 plan(권역·개수·개시월).
- [ ] PlanAccuracy: 권역별 초기값(없으면 0.5).
- [ ] 부동산원 CSV(data.go.kr 15069766) 다운로드 → 워커가 읽을 경로.
- [ ] Power Automate 사이트/채널/수신자, Power BI 사이트 URL·새로고침.

**바꾸지 말 것**: §5 핵심 로직 계약. 그 외(데이터·매핑·바인딩)만 채운다.

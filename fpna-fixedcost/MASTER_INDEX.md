# MASTER INDEX — 연결관계 + 공백→구현 추적

이 세션에서 쌓은 전부의 단일 지도. **설계(docs) ↔ 구현(fpna_fixedcost) ↔ 검증(tests) ↔ 데이터 흐름**을 명시한다.

## 1. 모듈 의존 그래프 (DAG — 임포트 방향, 순환 없음)
```
   common(0)   sox(0)
   engines      reference_data
   projection ← common, engines
   cards      ← common, engines, projection, sox
   analytics  ← common, engines, projection, cards
   lifecycle  ← cards            (route_note → enqueue_work_item)
   report     ← analytics, sox, cards
   main       ← (전부)
```
- 구현은 전부 `_core.py` 단일 코어. 위 모듈은 도메인별 **임포트 표면**(facade, 코어 재노출) — 깨끗한 경로 + 물리 분리 지점(구현 슬롯 B5). regression은 `tests/`로 가드.
- 순환 없음: cards→sox, analytics→cards, lifecycle→cards, report→{analytics,sox,cards}. 역방향 의존 없음.

## 2. 모듈 ↔ _core 섹션 ↔ 설계 문서
| 모듈 | _core 섹션 | 설계 docs | 역할 |
|------|-----------|-----------|------|
| common | 1 | — | dataclass·NPV/DCF·가중통계·gate_decision·중요성 |
| engines | 2-4 | 03(R4) | 임차 비교(RICS)·buy-vs-lease(IFRS16)·손상(IAS36) |
| projection | 5-6 | 01 §7.1 | 상각·리스 step-up·run-rate + 결정→fcst 배선 |
| reference_data | 16 | 06 | 외부지표(REB/ECOS)→reference_data SCD2, 엔진 조회 |
| sox | 7 | 01 §7.13 | ICFR 통제 매트릭스(COSO/PCAOB)+증적 |
| cards | 8·10·13·14·17·18 | 00·01 | 카드/게이트/DB·승인(SoD)·큐/outbox·variance·감쇠·콜드스타트 |
| analytics | 20-25 | 02(R3) | ER·계약개정·민감도·eval회귀·내러티브(그라운딩)·SLO |
| lifecycle | 26-27 | 07 | 노트 분류·라우팅 / 산출물 폴더링·매니페스트 |
| report | 11 | 04(v1)·01 §2 | openpyxl 5시트(전체 시간축·recon tie-out=0·evidence·ICFR·Variance·SLO) |

## 3. 데이터 흐름 (라이프사이클 — 함수·테이블로)
```
CAPTURE     Obsidian 노트 ─ lifecycle.route_note ─┐   메일/Teams ─┐   계약 ─┐
CLASSIFY    classify_note → note_register         ├─ cards.enqueue_work_item → work_item
PROCESS     cards.drain → route_work_item → run_worker
              engines.*(estimate_market_rent / analyze_buy_vs_lease / test_impairment)
              → cards.submit  [gate_decision: grounded·무출처금지·중요성·high-tier]
LEDGER      decision_analysis / fcst_line_projection  ◄ projection.project_fcst_lines
DECIDE      cards.approve_task(SoD) → enqueue_outbox → process_outbox(exactly-once)
              → sox.collect_control_evidence → icfr_summary(effective)
TRACE       analytics.build_variance_bridge(assumption_change → 결정 귀속)
              · apply_confidence_decay(stale→재확인) · detect_contract_change(개정)
              · resolve_entities(ER) · *_sensitivity · eval_deploy_gate · narrate_variance(grounded)
PRODUCE     report.build_report → fixed_cost_report.xlsx (5시트)
ORGANIZE    lifecycle.register_artifact(_drafts+manifest) → publish_artifact(불변)
              → artifact_register   [/reports/<YYYY>/<YYYY-MM>/<audience>/...]
DISTRIBUTE  Task → 승인 → outbox(발송)
RETAIN      deprecate/retract(이력) · 매니페스트 보존(재현)
```
외부지표: 인터넷 어댑터 → SharePoint 스냅샷 → reference_data.ingest_snapshot(SCD2) → 엔진이 regional_params/get_ibr로 조회(리터럴 아님).

## 4. 공백 → 구현 → 검증 추적
| 공백 | 출처 | 구현(모듈.함수) | 테스트 |
|------|------|-----------------|--------|
| 계약 결정 3엔진 | R4 | engines.* | test_impairment_recoverable_is_max |
| 투영+배선 | §7.1 | projection.* | demo 2·3 |
| 외부지표 수집 | 06 | reference_data.* | demo 0 |
| 트리거/큐·보안 | §4/§6.2 | cards.{enqueue,route,run}_work_item·drain | demo 4 |
| 그라운딩 Verifier | §6.1 | common.grounded_check·analytics.verify_narrative_claim | test_narrative_grounding |
| outbox exactly-once | §6.3 | cards.process_outbox | test_outbox_exactly_once |
| 승인(SoD) | §6.8 | cards.approve_task | test_sod_blocks_self_approval |
| ICFR/SOX | §7.13 | sox.* | demo 13 |
| Variance(가정변경 귀속) | §3 | cards.build_variance_bridge | test_variance_bridge_ties_out |
| 신뢰 감쇠 | §7.7 | cards.apply_confidence_decay | test_confidence_decay_marks_stale |
| 콜드스타트 | §7.11 | cards.bootstrap_from_history | demo 7 |
| 거래처 ER | §7.9 | analytics.resolve_entities | test_entity_resolution_clusters_by_biz_no |
| 계약 개정 | §7.8 | analytics.detect_contract_change | test_contract_amendment_supersede |
| 민감도 | §7.3 | analytics.*_sensitivity | demo 10 |
| eval/회귀·배포게이트 | §6.9 | analytics.eval_deploy_gate | test_deploy_gate_pass / router / gate_calibration |
| 내러티브 | §7.14 | analytics.narrate_variance | test_narrative_grounding_blocks_hallucination |
| 관측/SLO | §6.7 | analytics.compute_slos | demo 13 |
| 보고서(recon=0) | v1 | report.build_report | recalc 0 |
| 노트 분류·라우팅 | 07 §2 | lifecycle.{classify,route}_note | test_note_classification_routes |
| 산출물 폴더링·발행 | 07 §5 | lifecycle.{register,publish}_artifact | test_artifact_publish_immutable |

**구현 상태=전부 구현·검증(22 테스트)** → STATUS.md. 남은 건 운영 연결(외부 sender/데이터 fetcher 실계, 운영값 주입)뿐이며 기본값·오프라인 경로로 지금 동작 → plan.md(의존성 확인 + 구현). "추가 검토" 항목 없음.

## 5. 런타임 의존성·실행
- 런타임: **openpyxl 하나**(보고서). 코어=stdlib. pandas/numpy/pydantic/dbt/GE/jsonschema 불요.
```
python setup_check.py             # 의존성·임포트·스모크·테스트 점검 (가장 먼저)
PYTHONPATH=vendor python main.py  # 데모 0~15 + 보고서 5시트
python tests/test_invariants.py   # 13 invariants
```
보고서 시트: FixedCost_Forecast · Decision_Register · ICFR_Controls · Variance_Bridge · Ops_SLO.

## 6. 표준·출처 (코드 근거)
IFRS 16 / IAS 16 / IAS 36 / IFRS 13 · RICS 비교법·Red Book · IVS · COSO/PCAOB AS 2201 · ISA 320 ·
W3C PROV · SemVer · Fellegi-Sunter(ER) · ODCS/OpenLineage(모델). 한국: REB 임대동향조사·국토부 RTMS·한국은행 ECOS·통계청 KOSIS.

## 7. 외부 검토 반영 (docs/08_external_review.md)
별점 높은 구현·논문 대조 결과 **방향 오류 없음**(FP&A-agent 분야 베스트프랙티스와 일치). 정밀화 3건:
| 개선 | 근거 | 구현(_core §28) | 테스트 |
|------|------|-----------------|--------|
| ER u 직접추정(+λ 사전) | Splink(u 직접추정·m EM) | analytics.calibrate_u_from_data·fs_match_weight·fs_prior_weight | test_er_u_calibration_rare_value |
| eval baseline·비용 회귀 | promptfoo/DeepEval·Gartner(비용통제) | analytics.eval_regression_vs_baseline·eval_cost_regression·eval_deploy_gate(+cost) | test_eval_baseline_regression |
| 예측 정확도/편향 추적 | FP&A-agent 분야 핵심 열화신호 | analytics.forecast_accuracy·record_forecast_actual | test_forecast_accuracy_tracks_bias |
검증된 설계(변경 없음): 3카드 HITL·grounding/CoVe·FS ER·outbox·eval gate·중요성·계산vs판단·event-sourcing.
테스트 총 16개(13+3) PASS.

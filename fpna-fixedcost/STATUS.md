# STATUS — 구현 상태 (전부 구현·검증; 남은 건 운영값 주입과 외부계 연결)

이전 설계 문서에서 표준·방법론 기반이라 표기했던 정밀화 항목을 이 세션에서 전부 구현했다. 아래는 *구현 방법*과 *검증*이다. 미루는 항목 없음.
설계상 의도된 속성(불변식)은 마지막에 별도 표기.

## 해소 (구현 완료 · 검증)
| 항목 | 해소 방법 (근거) | 위치(_core) | 검증 |
|------|------------------|-------------|------|
| ER 가중치 데이터화 | u 직접추정 + **m을 EM 학습**(Splink) + λ 사전 | train_er_em·calibrate_u_from_data·resolve_entities(n≥30 자동) | test_er_em_learns_high_m (m=0.97) |
| ER 희소값 가중 | EM이 u를 데이터에서 산정 → 희소 사업자번호 강증거 | resolve_entities(EM 가중치 주입) | demo 17 (9.2 bits) |
| 서술 검증 비수치 확장 | **수치+어휘 하이브리드 검증**(CoVe/attribution) | verify_claim | test_verify_claim_hybrid |
| 워커 분기 | contract_ingest·overdue·note 실제 분기 구현 | run_worker | demo 9·14 |
| 발송 실행 | **sink 실행**(기본 log_sender→sent_log 기록, 멱등). 외부 sender 교체 지점 | process_outbox·SENDERS | test_outbox_sink_records_sent_log |
| 외부 데이터 연결 | **fetcher 어댑터**(file_fetcher 오프라인 + api_fetcher 키 기반, 동일 시그니처)→SCD2 적재 | fetch_and_ingest | test_external_adapter_offline_ingest |
| ABC 일반 배부 | driver 비중 배분(합 보존) | allocate_cost_abc | test_abc_allocation_conserves_total |
| IBR 매트릭스 값 | **완전 기본값**(KRW 기간×담보 6행, ECOS 벤치마크). 플레이스홀더 아님 | seed_full_ibr_matrix | demo 17 |
| 운영 설정값 | hurdle·CGU·house_style·보존·PII·택소노미 **작동 기본값** | DEFAULT_HURDLE·HOUSE_STYLE·RETENTION_POLICY·PII_POLICY·TAXONOMY_DEFAULT | demo 17 |
| PPT/PDF 산출물 | **콘텐츠 스펙 생성**(결론제목·exhibit·근거 각주·그라운딩); 렌더는 기존 BIGS deck_system/academic-slide | build_board_deck_spec·build_report_spec | test_board_deck_spec_grounded |
| eval 점진 퇴행·비용 | baseline 회귀 + 비용 회귀 게이트 | eval_regression_vs_baseline·eval_cost_regression | test_eval_baseline_regression |
| 예측 열화 감시 | MAPE·bias 추적 | forecast_accuracy | test_forecast_accuracy_tracks_bias |

검증 총괄: **22개 불변식 테스트 PASS**, 보고서 수식 오류 0(recalc), main 데모 0~18 정상.

## 운영 연결 (구현 행위 — 결정/검토 아님)
기본값·오프라인 경로로 *지금 동작*한다. 운영 투입 시 같은 인터페이스에 실값/실계를 꽂는다(plan.md):
- 외부 sender 등록: `SENDERS["outlook_com"]`(log_sender와 동일 시그니처) → process_outbox(sender=...). sender=통지 채널(메일/Teams), GL 기록 없음.
- 데이터 fetcher: `api_fetcher`에 OpenAPI 키(env)·승인 프록시 → file_fetcher 대신 사용(동일 반환).
- 운영값 오버라이드: IBR/CGU/SOX 범위/risk_tier/house_style 코퍼스/보존 기간을 기본값 위에 주입.
- 렌더 연결: 덱/문서 스펙을 BIGS deck_system/academic-slide·PDF 툴체인에 전달.

## 설계 불변식 (의도된 속성 — 바꾸지 않음)
- **단일 코어 + facade**: 폐쇄망 vendored 드롭인을 위해 구현은 `_core.py` 단일 모듈, 도메인 모듈은 임포트 표면. 한 파일 검토·벤더링이 쉽다.
- **단방향(GL 미기록)**: 확정 실적 SoT=외부 GL/ERP. 이 시스템은 해석·예측·근거의 SoT일 뿐 GL에 쓰지 않는다(통제 안전).
- **Fellegi-Sunter 채택**: 컬럼 조건부 독립은 FS(Splink) 표준 모델의 전제. 사업자번호가 지배 식별자라 영향이 작고, 경계 점수는 검토 큐로 보낸다.
- **수치 cite-back 우선**: 재무 서술의 1차 검증은 수치-ledger 일치(결정론). 비수치는 어휘 정렬로 보완. 수치 도메인에 적합한 선택.

## 흐름 보완 (이번 세션 — 끊긴 seam 3건 연결)
전체 파이프라인을 추적해 끊긴 곳을 연결했다(테스트로 고정, 23개 PASS):
- **결정→숫자 귀속**: `assumption_change_from_decisions`가 라벨만 반환하던 것을, 결정의 1차년 투영 − 예산으로 **귀속 금액을 산출**하도록 보완(`build_variance_bridge`가 사용, residual이 잔차 흡수, tie-out 유지). 근거: 유연예산/재예측 분산분해. 테스트 test_assumption_change_attributed_from_decisions.
- **하이브리드 검증 라이브 배선**: `verify_claim`(수치+어휘)이 데모에만 있던 것을 **보고 덱 생성 경로**에 연결 — 각 슬라이드 결론 제목을 레인 근거로 검증해 grounded 게이트(부호 차이 허용=방향은 어휘로). 환각 차단 유지.
- **ER 값별 TF 보정**: 스케일에서 EM의 m + **값별 term-frequency**(희소 사업자번호 강증거)를 적용하되 **고유 식별자는 기저 미만 약화 방지(min 경계)**. 소표본은 프라이어. 테스트로 스케일 군집 정확 병합 확인.

## 근거 (논문 · repo)
- ER: Fellegi & Sunter (1969); **Splink**(moj-analytical-services) term-frequency·EM·additive log2(m/u); **Xu, Li & Grannis (2021), J Appl Stat 49(11):2789** 빈도 기반 보정.
- 검증: **Chain-of-Verification**(arXiv 2309.11495)·**RARR**(arXiv 2210.08726)·ALCE 인용 평가.
- 발송: transactional outbox(microservices.io). eval 게이트: promptfoo/DeepEval(CI 지표 게이트).
- 회계/평가: IFRS 16·IAS 16·**IAS 36**(회수가능액=max(FVLCD,VIU)·CGU·pretax VIU)·IFRS 13·RICS; 통제: COSO·PCAOB AS2201; 데이터: 한국부동산원·한국은행 ECOS·통계청 KOSIS.

## 애매 항목 계획
운영 경계(렌더·발송·수집·검증 강화·ER 스케일)의 방향·근거·검증·구현은 **VERIFY_PLAN.md**에 확정.

## 미수정 엔진 재검토 (REVIEW.md)
RICS·IFRS16·IAS36·투영 엔진을 표준 대비 재검토 — MAJOR 2건 수정(IAS36 ¶105 바닥값+재배분, buy-vs-lease NAL 등가대출 병기), minor 5건(2 수정·3 문서화). 상세·근거는 REVIEW.md.

## 결선(seam) 2차 점검 (REVIEW.md)
큐/라우터·참조데이터·계약개정·eval·SLO 배선 추적 — MAJOR 1건(rebuild_request 미소비→무효화+재예측 연결), minor 4건(overdue 트리거·eval 실검증·freshness SLO·재스케줄 IBR) 수정. 테스트 28개 PASS.

## 카드 수명주기·조합 의사결정 추적 (CARD_FLOWS.md + tests/test_scenarios.py)
3종 카드(Playbook/Decision/Task)의 생성·전이·종결과 조합 흐름을 상태머신으로 추출, 22개 시나리오로 커버리지 누락 없이 검증(생성×게이트 5·전이 4·Task 수명주기 4·라우팅/보안 5·조합 전체 2·결함격리/dead-letter·Playbook 카드 2). 추적 중 결선 2건 추가 연결: drain 결함격리+retry→dead-letter, 미매칭→proposed Playbook 카드 영속화. setup_check가 시나리오까지 실행.

## 식별 약점 보완 (REVIEW.md 3차)
이전에 문서화만 했거나 미연결로 남긴 약점 전부 보완: 고정 confidence→민감도 안정성 산출, RICS CI ci_level 명시, SCD2 sha 멱등, stale↔재예측 Task 결정 연결, Playbook proposed→active(activate_playbook)+route 참조. 테스트 28 + 시나리오 23 PASS.

## 외부 경계 엔드포인트 구현 (INTEGRATION.md + connectors.py)
경계를 인터페이스→실제 커넥터로 구현: 파일 랜딩존 폴링(poll_inbox: 승인/거부/회신/계약/노트), file_sender(발송요청 기록), run_cycle(스케줄러 1주기, `python -m fpna_fixedcost.run_cycle`), reject_task(거부+SoD). 엔드포인트 E1–E12 전수조사 매니페스트 + E1 Teams Adaptive Card/Power Automate 상세. tests/test_connectors.py 6 PASS. setup_check가 커넥터까지 실행.

## 커넥터 의존성·ERP/COM 구체화 (INTEGRATION.md)
ERP 분리: E6=결산 READ 전용(ODBC DSN 있으면 파일 export 대체, odbc_actuals_fetcher SELECT 가드), E8 삭제(GL 쓰기 경로 없음 — 회계 사안은 회계팀 통지/이관). Outlook=COM(outlook_com_sender 발송·poll_outlook_replies 회신, win32com lazy-게이트), Teams=Power Automate. deps_check.py로 로컬 즉시 구현가능 여부 점검(파일랜딩존·Teams·보고서·E5=의존성0; COM/ODBC만 호스트 모듈). 작업순서: Phase 0(백본·스케줄러) 후 A(Teams)/B(COM)/C(ERP)/D(참조데이터)/E(렌더) 완전 병렬. test_connectors.py 8 PASS.


## 회계 이벤트 통지 정책 (기본 OFF, 이벤트별 토글)
회계 이벤트(lease_recognition·lease_remeasurement·asset_acquisition·impairment_loss) 식별 후, **기본은 포캐스트 반영**이고 **회계팀 통지는 기본 OFF**. `set_accounting_notify(event, True)`/env `FPNA_NOTIFY_<EVENT>`로 하나씩 ON→notify_accounting Task(사람 승인→통지). 손상 Task는 confirm_impairment(중립)로 환원, GL 쓰기 경로 없음. test_invariants 31 PASS(기본 OFF·토글 ON·독립).

# REVIEW — 미수정 엔진 재검토 (회계·재무 표준 대비, minor/major)

이번에 손대지 않았던 엔진(RICS 비교법·IFRS16 buy-vs-lease·IAS36 손상·투영)을 표준 대비 정밀 검토했다.
각 이슈에 심각도(major/minor)·근거·처리(수정/문서화)를 명시. 수정분은 테스트로 고정(25개 PASS).

## 요약
| # | 영역 | 이슈 | 심각도 | 처리 | 근거 |
|---|------|------|--------|------|------|
| A1 | IAS36 손상 배부 | 개별 자산 **바닥값(max FVLCD,VIU,0) 미적용** + 초과분 재배분 없음 | **MAJOR** | **수정** | IAS36 ¶104-105 |
| B2 | buy-vs-lease 할인 | 소유·리스를 **동일 허들로 할인**(리스=부채등가 무시) | **MAJOR** | **수정**(NAL 병기) | MDB1976·Ezzell-Miles1983·Brealey-Myers |
| A2 | IAS36 VIU | 유한수명 자산에 **영구성장 잔존가치** | minor | 수정(가드)+문서 | IAS36 ¶33 |
| B3 | 소유 처분 | **처분손실 세금절감 누락**(비대칭) | minor | 수정(대칭화) | 세무 잔액공제 |
| C1 | RICS 비교 | 신뢰구간 80% 휴리스틱 밴드 | minor | **수정**(ci_level 파라미터·결과 명시) | RICS는 통계 CI 미규정 |
| A3/B4 | 손상·구매 | confidence 고정(0.65/0.7) — 민감도 미반영 | minor | **수정**(민감도 안정성 산출) | DCF 신뢰도=섭동 안정성 |
| B5 | IFRS16 세금 | 현금주의 리스료 세금절감 ≈ 감가+이자(타이밍 근사) | minor | 문서화 | 기간 내 수렴 |

## MAJOR 1 — IAS 36 손상 배부 바닥값 (수정)
- **문제**: `allocate_loss`가 영업권 먼저→나머지 장부비례까지는 맞았으나, **개별 자산을 FVLCD/VIU/0 미만으로 감액 금지**(¶105)와 바닥에 닿은 초과분의 **타 자산 재배분**이 없었다. 자산을 회수가능액 아래로 과대 손상시킬 수 있음.
- **근거**: IAS36 ¶104(영업권 우선→장부비례), ¶105(개별 자산 바닥=max(FVLCD,VIU,0), 초과분 비례 재배분). "an asset's revised value cannot fall below its FVLCD or nil; excess reallocated to other assets."
- **수정**: `CGUAsset.recoverable_floor` 추가, `allocate_loss`를 바닥 한도 내 비례배분 + 초과분 반복 재배분으로 재작성. 테스트 test_impairment_floor_reallocation(A 바닥 90→10만 흡수, 70은 B로, 합 보존).

## MAJOR 2 — buy-vs-lease 할인율 (수정: NAL 병기)
- **문제**: `analyze_buy_vs_lease`가 소유·리스 현금흐름을 **단일 허들(WACC급)**로 할인. 리스는 계약상 부채등가라 재무이론상 **세후 차입금리**로 평가해야 하며, 할인율 선택이 결론을 바꾼다(데모: 허들9%→리스, 세후차입4.1%→구매로 역전).
- **근거**: 리스-vs-구매 NAL = capex − PV[세후 리스료 + 포기 감가세금절감]@세후차입금리 − PV[포기 잔존]. Myers·Dill·Bautista(1976), Ezzell·Miles(1983) "Analyzing leases with the after-tax cost of debt", Brealey·Myers·Allen. 이자 세금절감은 세후금리 할인에 내포되어 **별도 가산 시 이중계상**(Musumeci·O'Brien 2019).
- **수정**: `net_advantage_to_lease`(등가대출법) 추가, 잔존은 위험상이로 별도 할인. `analyze_buy_vs_lease`가 허들-NPV(자본예산 스크린)와 NAL(재무 결정)을 **둘 다 출력**하고 할인율 영향을 명시. 테스트 test_nal_equivalent_loan_discounts_at_after_tax_kd.

## minor (수정/문서화)
- **A2 VIU 영구성장**: 유한수명 CGU에 Gordon 영구성장 잔존가치는 ¶33(명시기간=유용수명, 성장률≤장기평균)과 상충. **수정**: growth<rate일 때만 잔존가치 가산(가드). 운영 시 유한수명 자산은 use_terminal=False·명시기간=잔여수명 권장.
- **B3 처분손실 세금**: `_own_cf`가 처분이익만 과세하고 손실 공제를 빠뜨림(보수적). **수정**: gain·tax 대칭(손실=세금절감).
- **C1 RICS 신뢰구간**: 가중평균 SE·z=1.2816은 **분산 휴리스틱 밴드**이지 표본 통계 보장이 아님. RICS 비교법은 통계 CI를 규정하지 않으므로 "근거 밴드"로 해석. 보수적으로 90/95%로 넓힐 수 있음.
- **A3/B4 confidence 고정**: 손상 0.65·구매 0.7은 민감도 분산 미반영. 손상은 high-tier로 검토강제, 구매는 med — 게이팅 영향 제한적. 운영 시 민감도 스프레드로 산출 가능.
- **B5 IFRS16 세금 타이밍**: DCF는 현금 리스료 세후를 쓰는데 IFRS16 손익은 감가+이자. 리스기간 누적으로 수렴하나 연도별 타이밍 차 존재(현금주의 DCF로 일관).

## 흐름(seam) 재확인 — 이상 없음
- 엔진→`project_fcst_lines`→`submit`(게이트·투영·SOX 증적)→승인(SoD)→outbox→sink: 연결 확인.
- 손상→`revised_depreciation_after_impairment`→투영: 자산별 수정장부/잔여수명 정상.
- SCD2 `ingest_snapshot`(valid_to close→open, sha 멱등), `detect_contract_change`(부속합의 supersede·재스케줄), eval 게이트(baseline/비용 회귀): 이번 검토 범위에서 구조적 결함 없음.

---

# REVIEW 2차 — 컴포넌트 간 결선(seam) 점검

큐/라우터·참조데이터·계약개정·SOX·eval·SLO의 *배선*을 추적: 생성만 되고 소비 안 되는 신호, 트리거 없는 분기, 항상 통과하는 eval을 찾아 연결했다(테스트 28개 PASS).

| # | 결선(seam) | 문제 | 심각도 | 처리 |
|---|------------|------|--------|------|
| S1 | 계약개정 → 하류 재산출 | `rebuild_request`가 **생성만 되고 소비 안 됨**(개정 후 옛 투영 그대로) | **MAJOR** | **수정**: `process_rebuild_requests`→영향 라인 결정 stale 무효화+`propose_reforecast` Task, drain에 배선 |
| S2 | 미충족요청 → 독촉 | `overdue_escalation` 워커·플레이북은 있으나 **트리거 없음** | minor | **수정**: `scan_overdue_requests`+라우트 규칙(`scheduler`)+내부 trust(보안 미차단) |
| S3 | eval 그라운딩 | `eval_grounding`이 **하드코딩 항상통과**(검증기 미사용) | minor | **수정**: `verify_claim`을 라벨셋(정상/환각)에 적용 |
| S4 | 참조데이터 신선도 | `ref_freshness`가 **데모에서만**(게이팅/모니터링 미연결) | minor | **수정**: `compute_slos`에 freshness SLO로 연결 |
| S5 | 계약 재스케줄 IBR | 개정 재스케줄이 **IBR 리터럴 0.052** 사용(매트릭스 무시) | minor | **수정**: `get_ibr` 조회(폴백 0.052) |

## S1 (MAJOR) — rebuild 미소비
- **문제**: `detect_contract_change`가 개정 시 `rebuild_request(pending)`를 등록하지만 이를 처리하는 코드가 없었다. 결과로 개정된 계약의 옛 버전에 기반한 `fcst_line_projection`·결정이 무효화되지 않고 잔존 — 예측이 옛 스케줄을 계속 반영.
- **근거**: §6.6 retraction 전파. 계보·무효화는 W3C PROV(Invalidation), bitemporal(Snodgrass) 모델. 개정=새 버전이므로 옛 버전 파생물은 재산출 대상.
- **수정**: `process_rebuild_requests`가 pending rebuild를 소비 — 영향 fcst_line의 적용/검토 결정을 `stale`로 무효화하고 `propose_reforecast` Task(사람 승인)를 방출, rebuild를 `processed`로. `drain` 종료 시 호출. 테스트 test_rebuild_invalidates_and_reforecasts(결정 1건 stale·Task 1건).
- **주의(설계)**: 투영 행 단위 자동 재계산이 아니라 *무효화 + 재예측 Task로 사람·워커가 새 계약으로 결정 재실행*하는 방식(스키마가 투영↔계약버전 링크를 안 가지므로 과대주장 회피). 운영 정밀화 시 투영에 contract_version FK 추가가 직접 경로.

## 기타 결선 — 이상 없음(재확인)
- 엔진→투영→`submit`(게이트·SOX 증적)→승인(SoD)→`process_outbox`(sink, control_evidence 승인 플립→icfr effective): 연결 확인.
- SCD2 read(`get_ibr`/`regional_params`)는 `valid_to IS NULL`로 현행만 조회. `drain`이 `ops_run` 기록→`compute_slos` worker_success/cost 반영. 감쇠(`apply_confidence_decay`)→stale+재확인 요청. 모두 정상.
- 잔여 minor(동일 스냅샷 재적재 시 0-duration 행, confidence 고정값)은 REVIEW 1차 표에 기재 — 운영 정밀화 항목.

---

# REVIEW 3차 — 식별된 약점 보완(결선 없이 남았던 항목 전부)

이전 검토에서 *문서화만* 하거나 *의도 경계*로 남겼던 항목을 전부 구현·연결했다(테스트 28+시나리오 23 PASS).
| 항목 | 이전 상태 | 보완 | 근거/검증 |
|------|-----------|------|-----------|
| 고정 confidence(손상0.65·구매0.7) | 문서화 | `confidence_from_stability`로 **민감도 섭동 안정성** 산출(구매 0.767·손상 0.9) | DCF 신뢰도=결정 안정성 |
| RICS 신뢰구간 80% 휴리스틱 | 문서화 | `ci_level` 파라미터(0.80/0.90/0.95)+결과 명시("밴드, 통계보장 아님") | RICS 미규정 명시 |
| SCD2 동일 스냅샷 재적재 0-duration 행 | 문서화 | `ingest_snapshot` **sha 멱등**(동일 내용 재적재→행 무변경) | 검증: 재적재 rows=0·행수 불변 |
| stale 결정 ↔ 재예측 Task 미연결 | 미연결 | rebuild reforecast·decay data_request Task를 **결정 analysis_id에 연결**(계보 추적) | SC08·SC09 |
| Playbook proposed→active 전환 없음 | 미구현 | `activate_playbook`(proposed→active)+route가 active 카드 참조 | SC23 |
| IFRS16 현금주의 세금 타이밍 | 문서화 | 현금주의 DCF는 기간 누적 수렴, **재무 결정은 NAL(등가대출)** 가 정확 관점으로 병기 — 추가 보완 불요 | Ezzell-Miles |

남은 의도 경계는 stale 결정의 applied 부활 금지(append-only supersede)뿐이며, 이는 회계·계보 표준상 올바른 동작이다.

# CARD_FLOWS — 카드 수명주기 상태머신 + 시나리오 커버리지

3종 카드의 생성·전이·소멸과 카드 조합 의사결정 흐름을 코드에서 추출. 시나리오는 누락 없이 열거하고
하니스(tests/test_scenarios.py)로 하나씩 실행·검증한다(append-only/bitemporal: 하드삭제 없음, '소멸'=종결상태).

## 상태머신
### Decision 카드 (decision_analysis.status) — 인식론적
- 생성: `submit`→ 게이트 통과면 `applied`, 아니면 `review` / `bootstrap_from_history`→ `provisional`
- 게이트(gate_decision): grounded ∧ conf≥0.6 ∧ materiality≠material ∧ tier≠high (4조건 AND)
- 전이: `review`→`applied`(연계 Task 실행 시 process_outbox) · `provisional`→`applied`(bulk_confirm) ·
  `applied|review|provisional`→`stale`(decay 임계하회) · `applied|review`→`stale`(rebuild 개정)
- 종결: `applied`(활성) / `stale`(재확인 필요 — 부활 아님, 재실행이 새 결정 생성)

### Task 카드 (task_card.status) — 행위적(항상 사람 승인)
- 생성(전부 `pending_approval`): `submit`(결정마다 1개: propose_renegotiation/propose_capex_or_lease/confirm_impairment) ·
  worker(send_reminder/review_note) · decay(propose_data_request) · rebuild(propose_reforecast) ·
  **notify_accounting**(회계 이벤트 + 통지 토글 ON일 때만; 기본 OFF=포캐스트 반영뿐)
- 전이: `pending_approval`→`approved`(approve_task, SoD) → outbox → `approved`→`done`(process_outbox, sink) ·
  `pending_approval`→`rejected`(reject_task, SoD; 종결, 부작용 없음) · SoD위반/비-pending→예외(전이 없음)
- 멱등: process_outbox 2회 호출=1회 효과(outbox confirmed, sent_log UNIQUE)

### Playbook 카드 (route_work_item + YAML) — 메타
- 매칭: correlated→inbound_reply_to_request · sharepoint /contracts/→contract_ingest ·
  scheduler overdue://→overdue_escalation · 미매칭→None→propose_playbook(work_item `awaiting_playbook`)

### work_item.status: pending → {done(워커처리) | review(외부 unsolicited 보안) | awaiting_playbook(미매칭)}
### 보조 전이: request_register sent→fulfilled · outbox pending→confirmed · rebuild_request pending→processed
###            control_evidence pending_approval→approved · ICFR no-evidence→pending-approval→effective

## 시나리오 커버리지 매트릭스 (누락 없음)
| ID | 커버 대상(상태머신 요소) |
|----|--------------------------|
| SC01 | Decision 생성·게이트 PASS → applied (+행동 Task는 pending) |
| SC02 | 게이트 차단: materiality=material → review |
| SC03 | 게이트 차단: grounded=False → review |
| SC04 | 게이트 차단: tier=high(손상) → review(강제) |
| SC05 | 게이트 차단: conf<0.6 → review |
| SC06 | 전이 review→applied (연계 Task 실행) |
| SC07 | 전이 provisional→applied (bootstrap→bulk_confirm) |
| SC08 | 전이 →stale (신뢰 감쇠) + propose_data_request Task |
| SC09 | 전이 →stale (계약 개정 rebuild) + propose_reforecast Task |
| SC10 | Task pending→approved→done + sink(sent_log) |
| SC11 | SoD 위반(승인자=요청자) → 차단, pending 유지 |
| SC12 | 비-pending 승인 시도 → 예외 |
| SC13 | 멱등: process_outbox 2회=1회 효과 |
| SC14 | 라우팅 correlated → inbound_reply → 결정 생성, 요청 fulfilled |
| SC15 | 라우팅 sharepoint /contracts/ → contract_ingest → 신규 계약 |
| SC16 | 라우팅 scheduler overdue → overdue_escalation → reminder Task |
| SC17 | 라우팅 미매칭 → propose_playbook(awaiting_playbook) |
| SC18 | 보안: 외부 unsolicited가 플레이북 매칭돼도 → review_only(자동작업 차단) |
| SC19 | 조합 전체: inbound→Decision→Task→승인→done + ICFR pending→effective |
| SC20 | 조합 전체: 손상(high)→review→Task 승인→process_outbox→applied + ICFR effective |
| SC21 | 워커 실패 결함격리(배치 미중단) + retry 누적 → dead-letter |
| SC22 | 미매칭 → awaiting_playbook + proposed Playbook 카드 영속화(자기확장) |
| SC23 | Playbook proposed→active 전환 후 동일 트리거가 active 카드로 라우팅(완결) |

## 회계 이벤트 + 회계팀 통지 정책 (기본 OFF, 이벤트별 토글)
의사결정/계약이벤트는 통상 회계처리와 연결된다. **기본 동작은 포캐스트 반영**(수정 감가·리스 charge·손상손익이 fcst_line_projection에 반영). **회계팀 통지는 이벤트 유형별 기본 OFF** — `set_accounting_notify('<event>', True)` 또는 env `FPNA_NOTIFY_<EVENT>=1`로 하나씩 켠다. ON이면 `notify_accounting` Task(사람 승인→통지 발송) 생성.

| 회계 이벤트 | 발생 의사결정/이벤트 | 기준 | 기본 |
|-------------|----------------------|------|------|
| lease_recognition | buy_vs_lease=리스 선택 | IFRS 16 최초인식(ROU·리스부채) | 포캐스트 반영(통지 OFF) |
| lease_remeasurement | lease_favorability 재협상 · 계약 개정 | IFRS 16 ¶40-46 | 포캐스트 반영(통지 OFF) |
| asset_acquisition | buy_vs_lease=구매 선택 | IAS 16 취득·감가 | 포캐스트 반영(통지 OFF) |
| impairment_loss | impairment | IAS 36 손상·수정 감가 | 포캐스트 반영(통지 OFF) |

검증: test_invariants(기본 OFF·토글 ON·독립 토글) + 손상 Task는 `confirm_impairment`(중립, 포캐스트 확인)이고 GL 기록 경로 없음.

## 설계 경계 (의도 — 시나리오 대상 아님)
- stale 결정의 '부활': 재확인/재예측 Task는 stale 결정에 **연결(analysis_id)** 되어 계보는 추적되나, 승인 시 새 결정을 생성(supersede)하며 stale 행을 applied로 되돌리지 않음(의도 — bitemporal append-only).
- Playbook active 전환의 **트리거 작성**: proposed→active는 `activate_playbook`로 전환되고 route가 참조(SC23). active 카드에 매칭된 신규 트리거는 worker 일반 처리(전용 분기 작성은 사람 단계).

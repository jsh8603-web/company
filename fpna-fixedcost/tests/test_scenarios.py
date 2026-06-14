"""test_scenarios.py — 카드 수명주기·조합 의사결정 시나리오 (커버리지 매트릭스: CARD_FLOWS.md).
각 시나리오는 신선한 in-memory DB에서 파이프라인을 돌리고 카드 상태/전이를 단언한다.
실행: python tests/test_scenarios.py  (또는 setup_check가 호출)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fpna_fixedcost import _core as S


# ---- 헬퍼 ----
def newdb():
    con = S.init_db(); S.init_controls(con); return con

def mkres(domain, grounded=True, conf=0.8, mat="below", value=100.0, rec="권고 X"):
    return S.AnalysisResult(domain=domain, recommended_value=value, recommendation=rec,
                            confidence=conf, materiality_band=mat, grounded=grounded, model_version="t/1")

def mkinp(sourced=True):
    prov = S.Provenance("u://x", S.Authority.SIGNED_CONTRACT, "2026-01-01") if sourced else None
    return [S.Input("x", 1.0, "KRW", prov)]

def one(con, q, *p): return con.execute(q, p).fetchone()

LEASE_REPLY = {"kind": "lease_comps",
    "subject": {"location": "판교", "size_sqm": 8000, "term_months": 60, "grade": 4, "cost_basis": "net", "contract_rent_per_sqm": 21000},
    "comps": [{"comp_id": "K1", "headline_rent_per_sqm": 19500, "rent_free_months": 3, "term_months": 60, "months_ago": 3, "size_sqm": 7500, "grade": 4, "cost_basis": "net", "same_location": True, "txn_type": "letting", "uri": "sp://k1", "auth": "INVOICE_PO", "asof": "2026-06-15"},
              {"comp_id": "K2", "headline_rent_per_sqm": 18800, "rent_free_months": 4, "term_months": 60, "months_ago": 8, "size_sqm": 9000, "grade": 4, "cost_basis": "net", "same_location": True, "txn_type": "letting", "uri": "sp://k2", "auth": "INVOICE_PO", "asof": "2026-06-15"},
              {"comp_id": "K3", "headline_rent_per_sqm": 20100, "rent_free_months": 2, "term_months": 48, "months_ago": 2, "size_sqm": 6800, "grade": 4, "cost_basis": "net", "same_location": True, "txn_type": "letting", "uri": "sp://k3", "auth": "INVOICE_PO", "asof": "2026-06-15"}],
    "materiality": 50_000_000}

CONTRACT = {"counterparty_name": "한빛물류(주)", "biz_no": "211-87-00001", "asset_or_property": "이천DC-동A",
            "contract_no": "L-IC-010", "monthly_amount": 90_000_000, "term_months": 60, "escalation": 0.03,
            "start_date": "2026-01-01", "end_date": "2030-12-31", "source_doc": "sp://contracts/L-IC-010.pdf",
            "fcst_line": "DC_lease_icheon"}


# ---- Decision 생성 × 게이트 ----
def SC01_gate_pass_applied(con):
    """covers: Decision 생성·게이트 PASS → applied; 행동 Task는 pending."""
    r = S.submit(con, "q", mkres("buy_vs_lease", grounded=True, conf=0.8, mat="below"), mkinp())
    assert r["status"] == "applied" and r["auto_applied"] is True
    t = one(con, "SELECT status FROM task_card WHERE analysis_id=?", r["analysis_id"])
    assert t[0] == "pending_approval"   # 인식론적 자동반영 ≠ 행동 자동실행
    return "applied + Task pending"

def SC02_material_review(con):
    """covers: 게이트 차단 materiality=material → review."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    assert r["status"] == "review" and r["auto_applied"] is False
    return "review(material)"

def SC03_ungrounded_review(con):
    """covers: 게이트 차단 grounded=False → review."""
    r = S.submit(con, "q", mkres("buy_vs_lease", grounded=False), mkinp())
    assert r["status"] == "review" and r["grounded"] is False
    return "review(ungrounded)"

def SC04_high_tier_review(con):
    """covers: 게이트 차단 tier=high(손상) → review(강제)."""
    r = S.submit(con, "q", mkres("impairment", grounded=True, conf=0.9, mat="below"), mkinp())
    assert r["status"] == "review" and "high" in r["task"]
    return "review(high-tier 강제)"

def SC05_lowconf_review(con):
    """covers: 게이트 차단 conf<0.6 → review."""
    r = S.submit(con, "q", mkres("buy_vs_lease", conf=0.5), mkinp())
    assert r["status"] == "review"
    return "review(conf<0.6)"


# ---- Decision 전이 ----
def SC06_review_to_applied(con):
    """covers: 전이 review→applied (연계 Task 실행)."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    S.approve_task(con, tid, approver="controller")
    S.process_outbox(con)
    assert one(con, "SELECT status FROM decision_analysis WHERE id=?", r["analysis_id"])[0] == "applied"
    return "review→applied"

def SC07_provisional_to_applied(con):
    """covers: 전이 provisional→applied (bootstrap→bulk_confirm)."""
    S.bootstrap_from_history(con, [{"name": "이천DC 임차", "value": 1.08e9, "domain": "lease_favorability",
                                    "fcst_line": "DC_lease_icheon", "doc": "sp://c.pdf"}], {})
    assert one(con, "SELECT COUNT(*) FROM decision_analysis WHERE status='provisional'")[0] == 1
    S.bulk_confirm_provisional(con, approver="controller")
    assert one(con, "SELECT COUNT(*) FROM decision_analysis WHERE status='provisional'")[0] == 0
    assert one(con, "SELECT COUNT(*) FROM decision_analysis WHERE status='applied'")[0] == 1
    return "provisional→applied"

def SC08_decay_to_stale(con):
    """covers: 전이 →stale(신뢰 감쇠) + propose_data_request Task."""
    r = S.submit(con, "q", mkres("lease_favorability", mat="below"), mkinp())
    con.execute("UPDATE decision_analysis SET created_at='2024-01-01', evidence_kind='market_estimate', status='applied' WHERE id=?", (r["analysis_id"],))
    con.commit()
    out = S.apply_confidence_decay(con, asof="2026-06-14")
    assert any(o["analysis_id"] == r["analysis_id"] for o in out)
    assert one(con, "SELECT status FROM decision_analysis WHERE id=?", r["analysis_id"])[0] == "stale"
    assert one(con, "SELECT COUNT(*) FROM task_card WHERE task_type='propose_data_request'")[0] == 1
    return "applied→stale + data_request"

def SC09_rebuild_to_stale(con):
    """covers: 전이 →stale(계약 개정 rebuild) + propose_reforecast Task."""
    r = S.submit(con, "q", mkres("lease_favorability"), mkinp(), fcst_line="DC_lease_icheon")
    con.execute("INSERT INTO rebuild_request(trigger,affected,status,created_at) VALUES('amendment:x','DC_lease_icheon','pending','2026-06-14')")
    con.commit()
    S.process_rebuild_requests(con)
    assert one(con, "SELECT status FROM decision_analysis WHERE id=?", r["analysis_id"])[0] == "stale"
    assert one(con, "SELECT COUNT(*) FROM task_card WHERE task_type='propose_reforecast'")[0] == 1
    return "applied/review→stale + reforecast"


# ---- Task 수명주기 ----
def SC10_task_done_with_sink(con):
    """covers: Task pending→approved→done + sink(sent_log)."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    S.approve_task(con, tid, approver="controller")
    assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "approved"
    S.process_outbox(con)
    assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "done"
    assert one(con, "SELECT COUNT(*) FROM sent_log")[0] == 1
    return "pending→approved→done + sent_log"

def SC11_sod_violation(con):
    """covers: SoD 위반(승인자=요청자) → 차단, pending 유지."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    try:
        S.approve_task(con, tid, approver="fpna-analyst")   # == requester
        raise AssertionError("SoD 위반이 차단되지 않음")
    except S.SoDViolation:
        pass
    assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "pending_approval"
    return "SoD 차단 + pending 유지"

def SC12_approve_wrong_state(con):
    """covers: 비-pending 승인 시도 → 예외."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    S.approve_task(con, tid, approver="controller")
    try:
        S.approve_task(con, tid, approver="cfo")   # 이미 approved
        raise AssertionError("비-pending 승인이 막히지 않음")
    except ValueError:
        pass
    return "비-pending 승인 차단"

def SC13_exactly_once(con):
    """covers: 멱등 process_outbox 2회=1회 효과."""
    r = S.submit(con, "q", mkres("buy_vs_lease", mat="material"), mkinp())
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    S.approve_task(con, tid, approver="controller")
    n1 = len(S.process_outbox(con)); n2 = len(S.process_outbox(con))
    assert n1 == 1 and n2 == 0 and one(con, "SELECT COUNT(*) FROM sent_log")[0] == 1
    return "exactly-once (1차1·2차0)"


# ---- 라우팅 / 보안 ----
def SC14_route_correlated(con):
    """covers: 라우팅 correlated→inbound_reply→결정 생성, 요청 fulfilled."""
    tok = S.open_request(con, "REQ-1", "HQ_lease_pangyo", "facilities", "2026-06-20")
    S.enqueue_work_item(con, "outlook", "msg://r1", "id-1", correlation_token=tok, payload=LEASE_REPLY)
    S.drain(con)
    assert one(con, "SELECT COUNT(*) FROM decision_analysis WHERE domain='lease_favorability'")[0] >= 1
    assert one(con, "SELECT status FROM request_register WHERE request_id='REQ-1'")[0] == "fulfilled"
    return "correlated→결정+fulfilled"

def SC15_route_contract(con):
    """covers: 라우팅 sharepoint /contracts/→contract_ingest→신규 계약."""
    S.enqueue_work_item(con, "sharepoint", "sp://contracts/L-IC-010.pdf", "doc-1",
                        correlation_token=None, payload={"contract": CONTRACT})
    # 외부 unsolicited지만 SC18에서 보안 검증 — 여기선 내부 신뢰 가정 위해 trust 보정
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='doc-1'"); con.commit()
    S.drain(con)
    assert one(con, "SELECT COUNT(*) FROM contract_master WHERE status='active'")[0] == 1
    return "contract_ingest→신규 계약"

def SC16_route_overdue(con):
    """covers: 라우팅 scheduler overdue→overdue_escalation→reminder Task."""
    S.open_request(con, "REQ-OVD", "L", "o", "2026-01-31")   # 과거 기한
    res = S.drain(con, now="2026-06-14")
    assert any(r.get("routed") == "overdue_escalation" for r in res)
    assert one(con, "SELECT COUNT(*) FROM task_card WHERE task_type='send_reminder'")[0] == 1
    return "overdue→reminder Task"

def SC17_route_unmatched(con):
    """covers: 라우팅 미매칭→propose_playbook(awaiting_playbook)."""
    S.enqueue_work_item(con, "outlook", "msg://misc", "id-x", correlation_token=None, payload={"kind": "unknown"})
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='id-x'"); con.commit()  # 보안과 분리해 라우팅만 검증
    S.drain(con)
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='id-x'")[0] == "awaiting_playbook"
    return "미매칭→awaiting_playbook"

def SC18_security_unsolicited_review_only(con):
    """covers: 보안 — 외부 unsolicited가 플레이북 매칭돼도 review_only(자동작업 차단)."""
    # 상관키 없는 sharepoint /contracts/ → 라우팅은 contract_ingest이나 trust=unsolicited
    S.enqueue_work_item(con, "sharepoint", "sp://contracts/evil.pdf", "doc-evil",
                        correlation_token=None, payload={"contract": CONTRACT})
    S.drain(con)
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='doc-evil'")[0] == "review"
    assert one(con, "SELECT COUNT(*) FROM contract_master")[0] == 0   # 자동 계약생성 안 됨
    return "unsolicited→review_only(작업 차단)"


# ---- 조합 전체 파이프라인 ----
def SC19_full_inbound_pipeline(con):
    """covers: 조합 — inbound→Decision→Task→승인→done + ICFR pending→effective."""
    tok = S.open_request(con, "REQ-9", "HQ_lease_pangyo", "facilities", "2026-06-20")
    S.enqueue_work_item(con, "outlook", "msg://r9", "id-9", correlation_token=tok, payload=LEASE_REPLY)
    S.drain(con)
    aid = one(con, "SELECT id FROM decision_analysis WHERE domain='lease_favorability' ORDER BY id DESC")[0]
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", aid)[0]
    icfr_before = {c: s for c, _, _, _, _, s in S.icfr_summary(con)}
    S.approve_task(con, tid, approver="controller")
    S.process_outbox(con)
    assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "done"
    icfr_after = {c: s for c, _, _, _, _, s in S.icfr_summary(con)}
    lease_controls = [c for c in icfr_after if c in icfr_before]
    assert any(icfr_after[c] == "effective" for c in lease_controls)   # 승인 후 통제 유효
    return "inbound→…→done + ICFR effective"

def SC20_full_impairment_pipeline(con):
    """covers: 조합 — 손상(high)→review→Task 승인→process_outbox→applied + ICFR effective."""
    cgu = S.CGU("cgu", [S.CGUAsset("M1", 6.2e9, life_years=8, elapsed_years=3, residual=2e8)],
                pretax_cashflows_y1_n=[1.2e9, 1.15e9, 1.1e9, 1.05e9, 1.0e9], pretax_rate=0.13,
                terminal_growth=0.0, use_terminal=True, fair_value=4.15e9, costs_of_disposal=0.0)
    res, inp = S.test_impairment(cgu, abs_materiality=2e8)
    r = S.submit(con, "손상", res, inp, projections=S.project_fcst_lines("impairment", cgu=cgu, alloc=res._alloc), fcst_line="DC_machines")
    assert r["status"] == "review"   # high-tier 강제 검토
    tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
    S.approve_task(con, tid, approver="controller")
    S.process_outbox(con)
    assert one(con, "SELECT status FROM decision_analysis WHERE id=?", r["analysis_id"])[0] == "applied"
    assert any(s == "effective" for _, _, _, _, _, s in S.icfr_summary(con))
    return "손상 high→review→승인→applied + ICFR"


def SC21_worker_failure_deadletter(con):
    """covers: 워커 실패 결함격리(배치 미중단) + retry 누적→dead-letter."""
    S.enqueue_work_item(con, "sharepoint", "sp://contracts/bad.pdf", "bad-1", correlation_token=None, payload={"contract": {"bad": True}})
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='bad-1'"); con.commit()  # 라우팅되나 내부서 예외
    tok = S.open_request(con, "REQ-OK", "HQ_lease_pangyo", "f", "2026-06-20")
    S.enqueue_work_item(con, "outlook", "msg://ok", "ok-1", correlation_token=tok, payload=LEASE_REPLY)
    S.drain(con)   # 1회: bad 실패(attempts=1) — 그러나 정상 inbound은 처리됨(결함격리)
    assert one(con, "SELECT COUNT(*) FROM decision_analysis WHERE domain='lease_favorability'")[0] >= 1
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='bad-1'")[0] == "pending"
    S.drain(con); S.drain(con)   # 누적 3회 → dead-letter
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='bad-1'")[0] == "dead"
    assert one(con, "SELECT COUNT(*) FROM ops_run WHERE status='failed'")[0] >= 1
    return "결함격리 + 3회→dead-letter"

def SC22_propose_playbook_card(con):
    """covers: 미매칭 → awaiting_playbook + proposed Playbook 카드 영속화(자기확장)."""
    S.enqueue_work_item(con, "slack", "slack://random", "rnd-1", correlation_token=None, payload={"kind": "x"})
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='rnd-1'"); con.commit()
    S.drain(con)
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='rnd-1'")[0] == "awaiting_playbook"
    assert one(con, "SELECT COUNT(*) FROM playbook_card WHERE status='proposed'")[0] >= 1
    return "미매칭→proposed Playbook 카드"


def SC23_playbook_activate_then_route(con):
    """covers: Playbook proposed→active 전환 후, 동일 트리거가 active 카드로 라우팅(자기확장 완결)."""
    S.enqueue_work_item(con, "slack", "slack://expenses", "e-1", correlation_token=None, payload={"kind": "x"})
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='e-1'"); con.commit()
    S.drain(con)   # 미매칭 → proposed 카드 + awaiting_playbook
    pbid = one(con, "SELECT playbook_id FROM playbook_card WHERE status='proposed'")[0]
    S.activate_playbook(con, pbid, approver="controller")          # 사람 작성·활성화
    S.enqueue_work_item(con, "slack", "slack://expenses", "e-2", correlation_token=None, payload={"kind": "x"})
    con.execute("UPDATE work_item SET trust='correlated' WHERE dedup_key='e-2'"); con.commit()
    S.drain(con)   # 동일 트리거 → 이제 active 카드로 라우팅(처리됨)
    assert one(con, "SELECT status FROM work_item WHERE dedup_key='e-2'")[0] == "done"
    return "proposed→active→라우팅 완결"


SCENARIOS = [v for k, v in sorted(globals().items()) if k.startswith("SC")]


def run_all():
    passed, failed = 0, []
    print("=" * 78)
    print("카드 수명주기·조합 의사결정 시나리오 (커버리지: CARD_FLOWS.md)")
    print("=" * 78)
    for fn in SCENARIOS:
        name = fn.__name__
        con = newdb()
        try:
            detail = fn(con)
            print(f"  PASS  {name:32s} → {detail}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name:32s} → {type(e).__name__}: {e}")
            failed.append(name)
    print("-" * 78)
    print(f"{passed} passed, {len(failed)} failed" + (f"  실패: {failed}" if failed else ""))
    return not failed


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)

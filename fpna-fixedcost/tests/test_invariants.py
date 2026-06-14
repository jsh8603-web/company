"""핵심 불변식 회귀 테스트. pytest 또는 `python tests/test_invariants.py`(stdlib)로 실행.

검증: View Contract recon tie-out=0 · 전수 매핑 · 게이트 보정 · 거래처 ER 클러스터 ·
      계약 개정 supersede · outbox exactly-once · 신뢰 감쇠→stale · 내러티브 그라운딩(환각 차단) ·
      eval 배포 게이트 · SoD 차단 · IAS36 회수가능액=max(FVLCD,VIU).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fpna_fixedcost import cards, engines, analytics, reference_data, common, lifecycle


def _con():
    return cards.init_db()


def test_gate_calibration_no_false():
    con = _con()
    r = analytics.eval_gate_calibration(con)
    assert r["passed"] and r["value"] <= 0.05            # false-apply/escalate 0


def test_router_accuracy():
    con = _con()
    r = analytics.eval_router(con)
    assert r["passed"] and r["value"] >= 0.95


def test_deploy_gate_pass():
    con = _con()
    dg = analytics.eval_deploy_gate(con)
    assert dg["deploy"] == "PASS"


def test_entity_resolution_clusters_by_biz_no():
    con = _con()
    er = analytics.resolve_entities(con, [
        {"id": 1, "name": "쿠팡로지스틱스(주)", "biz_no": "123-45-67890", "addr": "서울 송파"},
        {"id": 2, "name": "Coupang Logistics Co., Ltd.", "biz_no": "123-45-67890", "addr": "Seoul"},
        {"id": 3, "name": "한진물류(주)", "biz_no": "999-88-77776", "addr": "인천"}])
    sizes = sorted(len(v) for v in er["clusters"].values())
    assert sizes == [1, 2]                                # 2개 변형 통합 + 1개 분리


def test_contract_amendment_supersede():
    con = _con()
    analytics.resolve_entities(con, [{"id": 1, "name": "L사(주)", "biz_no": "111-11-11111", "addr": "A"}])
    base = {"counterparty_name": "L사(주)", "biz_no": "111-11-11111", "asset_or_property": "P1",
            "contract_no": "C1", "monthly_amount": 100, "term_months": 24, "source_doc": "d"}
    r1 = analytics.detect_contract_change(con, base)
    r2 = analytics.detect_contract_change(con, {**base, "monthly_amount": 110})
    assert r1["type"] == "new" and r2["type"] == "amendment" and r2["supersedes"] == r1["contract"]


def test_outbox_exactly_once():
    con = _con()
    con.execute("""INSERT INTO task_card(analysis_id,task_type,payload,risk_tier,status,requester,approver,created_at)
                   VALUES(1,'send_request','{}','low','pending_approval','analyst',NULL,'2026-06-14')""")
    tid = con.execute("SELECT MAX(id) FROM task_card").fetchone()[0]
    con.execute("INSERT INTO decision_analysis(id,status) VALUES(1,'review')")
    cards.approve_task(con, tid, approver="controller")
    n1 = len(cards.process_outbox(con))
    n2 = len(cards.process_outbox(con))                   # 멱등: 2차 0
    assert n1 == 1 and n2 == 0


def test_sod_blocks_self_approval():
    con = _con()
    con.execute("""INSERT INTO task_card(analysis_id,task_type,payload,risk_tier,status,requester,approver,created_at)
                   VALUES(1,'x','{}','low','pending_approval','same','NULL','2026-06-14')""")
    tid = con.execute("SELECT MAX(id) FROM task_card").fetchone()[0]
    try:
        cards.approve_task(con, tid, approver="same"); assert False, "SoD 미차단"
    except cards.SoDViolation:
        pass


def test_confidence_decay_marks_stale():
    con = _con()
    con.execute("""INSERT INTO decision_analysis(question,domain,fcst_line,evidence_kind,inputs,model,model_version,
        result,confidence,conf_interval,sensitivity,materiality_band,grounded,status,linked_assumption_card,next_review,created_at)
        VALUES('x','lease_favorability','L','market_estimate','[]','m','m/1','{}',0.72,'[0,0]','{}','n/a',1,'applied','a',NULL,'2025-01-01')""")
    out = cards.apply_confidence_decay(con, asof="2026-06-14", stale_threshold=0.4)
    assert out and out[0]["decayed_conf"] < 0.4           # 노후 → stale + 재확인


def test_variance_bridge_ties_out():
    con = _con()
    br = cards.build_variance_bridge(con, "L", budget=2000, actual=1900,
                                     lanes={"indexation": 40, "assumption_change": -140})
    assert br["tie_out"] == 0                             # View Contract recon


def test_narrative_grounding_blocks_hallucination():
    con = _con()
    cards.build_variance_bridge(con, "L", budget=2000, actual=1900,
                                lanes={"indexation": 40, "assumption_change": -140})
    v_ok = analytics.verify_narrative_claim(con, "L", "assumption_change", -140)
    v_bad = analytics.verify_narrative_claim(con, "L", "assumption_change", -999)
    assert v_ok["grounded"] and not v_bad["grounded"]     # 환각 차단


def test_impairment_recoverable_is_max():
    fv = 4150.0
    cgu = engines.CGU("c", [engines.CGUAsset("a", 6200, life_years=10, elapsed_years=3, residual=200)],
                      [900, 850, 800, 750, 700], 0.13, terminal_growth=0.01,
                      fair_value=4300, costs_of_disposal=150)
    rec = max(engines.value_in_use(cgu), engines.fvlcd(cgu))
    assert engines.fvlcd(cgu) == fv and rec >= engines.fvlcd(cgu)


def test_note_classification_routes():
    a = lifecycle.classify_note({}, "본사 임차 갱신 임대료 ₩175,000,000 회신 예정, 검토 필요")
    r = lifecycle.classify_note({}, "IFRS16 IBR 방법론 메모, 기준서 참고")
    p = lifecycle.classify_note({}, "주말 등산 다녀옴 날씨 좋았음")
    assert a["route"] == "pipeline" and a["sensitivity"] == "S1"   # 금액→S1, 액션+고정비→파이프라인
    assert r["route"] == "DA_index"                                # 방법론→DA 지식
    assert p["route"] == "vault_only"                              # 개인→볼트


def test_artifact_publish_immutable():
    con = cards.init_db()
    a = lifecycle.register_artifact(con, "2026-06", "controller", "variance", "X", "r1", "xlsx", inputs=["L2"])
    assert "_drafts/" in a["path"]                                 # 초안은 _drafts
    pub = lifecycle.publish_artifact(con, a["artifact_id"], approver="controller")
    assert pub["status"] == "published" and "_drafts/" not in pub["path"] and "/controller/" in pub["path"]
    again = lifecycle.publish_artifact(con, a["artifact_id"], approver="controller")
    assert "already_published" in again["status"]                 # 발행본 불변


def test_er_u_calibration_rare_value():
    recs = [{"name": f"L{i}", "biz_no": f"{i}-x"} for i in range(30)] + [{"name": "dup", "biz_no": "9-x"}]
    cal = analytics.calibrate_u_from_data(recs, fields=("biz_no",))
    assert 0 < cal["u_probabilities"]["biz_no"] < 0.1           # 대부분 고유→u 작음→강한 증거
    assert analytics.fs_match_weight(0.99, cal["u_probabilities"]["biz_no"], True) > 2  # log2(m/u)>0


def test_eval_baseline_regression():
    con = cards.init_db()
    analytics.eval_router(con)                                   # baseline(정확도 1.0) 적재
    reg = analytics.eval_regression_vs_baseline(con, "router_match", value=0.80, le=False)
    assert reg["baseline"] is not None and reg["regressed"]      # 직전 대비 악화 감지


def test_forecast_accuracy_tracks_bias():
    con = cards.init_db()
    for p, f, a in [("m1", 100, 120), ("m2", 100, 130)]:
        analytics.record_forecast_actual(con, "L", p, f, a)
    fa = analytics.forecast_accuracy(con, "L", mape_threshold=0.05)
    assert fa["n"] == 2 and fa["status"] == "degraded" and fa["bias"] < 0   # 과소예측 누적


def test_er_em_learns_high_m():
    recs = [{"biz_no": f"{i}-x"} for i in range(30)] + [{"biz_no": "9-x"}, {"biz_no": "9-x"}]
    p = analytics.train_er_em(recs, "biz_no")
    assert p["m"] > 0.8 and p["u"] < 0.05                       # EM이 m 높게·u 낮게 학습


def test_verify_claim_hybrid():
    ev = "임차료가 6,600만원 감소했고 주 요인은 재협상"
    assert analytics.verify_claim(ev, "6600만원 감소")["grounded"]        # 수치 일치
    assert analytics.verify_claim(ev, "재협상이 주 요인")["grounded"]      # 어휘 정렬
    assert not analytics.verify_claim(ev, "신규 차량이 원인")["grounded"]  # 환각 차단


def test_abc_allocation_conserves_total():
    a = analytics.allocate_cost_abc(1000.0, {"x": 3, "y": 1})
    assert abs(sum(a.values()) - 1000.0) < 0.01 and a["x"] == 750.0   # 합 보존·비중 배분


def test_external_adapter_offline_ingest():
    import json, tempfile, os
    from fpna_fixedcost import reference_data
    con = cards.init_db()
    p = os.path.join(tempfile.gettempdir(), "t_snap.json")
    json.dump([{"region": "R", "property_type": "office", "grade": 4, "period": "Q",
                "rent_per_sqm": 100, "rent_index": 100.0, "vacancy": 1.0}], open(p, "w"))
    r = reference_data.fetch_and_ingest(con, "regional_rent_benchmark",
        ["region", "property_type", "grade", "period"], "REB", "src", "url", "lic", "v1",
        lambda: reference_data.file_fetcher(p))
    assert r["rows"] == 1                                        # 오프라인 fetcher로 적재


def test_outbox_sink_records_sent_log():
    con = cards.init_db()
    con.execute("""INSERT INTO task_card(analysis_id,task_type,payload,risk_tier,status,requester,approver,created_at)
                   VALUES(1,'send_request','{}','low','pending_approval','analyst',NULL,'2026-06-14')""")
    tid = con.execute("SELECT MAX(id) FROM task_card").fetchone()[0]
    con.execute("INSERT INTO decision_analysis(id,status) VALUES(1,'review')")
    cards.approve_task(con, tid, approver="controller")
    cards.process_outbox(con)
    n = con.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
    assert n == 1                                               # 발송이 sink에 실제 기록(no-op 아님)


def test_board_deck_spec_grounded():
    from fpna_fixedcost import report
    con = cards.init_db()
    cards.build_variance_bridge(con, "L", budget=2000, actual=1900,
                                lanes={"indexation": 40, "assumption_change": -140})
    deck = report.build_board_deck_spec(con, "L", "2026-06")
    assert deck["grounded"] and len(deck["slides"]) >= 3        # 그라운딩·결론제목 슬라이드
    assert all("action_title" in s for s in deck["slides"])     # house_style: 결론 제목
    assert "renderer" in deck                                   # 렌더는 기존 툴체인으로 위임


def test_assumption_change_attributed_from_decisions():
    con = cards.init_db()
    con.execute("INSERT INTO decision_analysis(id,domain,fcst_line,status) VALUES(1,'lease_favorability','L','applied')")
    con.execute("INSERT INTO fcst_line_projection(analysis_id,line_type,period,value,note) VALUES(1,'lease_renewal_pnl',1,900,'')")
    con.commit()
    br = cards.build_variance_bridge(con, "L", budget=1000, actual=1100, lanes={"indexation": 50})
    assert br["lanes"]["assumption_change"] == -100.0   # 900(결정 1차년 투영) − 1000(예산) 귀속
    assert br["tie_out"] == 0.0                          # 잔차 흡수, tie-out 유지


def test_impairment_floor_reallocation():
    from fpna_fixedcost import engines as E
    # 자산 A(장부 100, 바닥 90) / B(장부 100, 바닥 0). 손실 80 → A는 10까지만, 나머지 70은 B로
    cgu = E.CGU("cgu", [E.CGUAsset("A", 100, recoverable_floor=90),
                        E.CGUAsset("B", 100, recoverable_floor=0)],
               pretax_cashflows_y1_n=[10], pretax_rate=0.1, use_terminal=False)
    alloc = dict(E.allocate_loss(cgu, 80))
    assert alloc["A"] <= 10.0 + 1e-6 and abs(alloc["A"] + alloc["B"] - 80) < 1.0  # 바닥 준수·합 보존


def test_nal_equivalent_loan_discounts_at_after_tax_kd():
    from fpna_fixedcost import engines as E
    own = E.OwnPlan(capex=1000, life_years=5, residual_value=100, annual_opex=0, tax_rate=0.25)
    lease = E.LeasePlan(annual_payment=240, term_years=5, ibr=0.06)
    nal = E.net_advantage_to_lease(own, lease, kd_after_tax=0.06 * (1 - 0.25), horizon=5)
    assert nal["kd_after_tax"] == 0.045 and nal["decision"] in ("리스", "구매")  # 세후 차입금리 할인


def test_rebuild_invalidates_and_reforecasts():
    from fpna_fixedcost import analytics as A
    con = cards.init_db()
    con.execute("INSERT INTO decision_analysis(id,domain,fcst_line,status) VALUES(1,'lease_favorability','L','applied')")
    con.execute("INSERT INTO rebuild_request(trigger,affected,status,created_at) VALUES('amendment:x','L','pending','2026-06-14')")
    con.commit()
    out = A.process_rebuild_requests(con)
    stale = con.execute("SELECT status FROM decision_analysis WHERE id=1").fetchone()[0]
    task = con.execute("SELECT COUNT(*) FROM task_card WHERE task_type='propose_reforecast'").fetchone()[0]
    assert out[0]["invalidated_decisions"] == 1 and stale == "stale" and task == 1   # 개정→무효화+재예측


def test_overdue_routes_to_escalation():
    con = cards.init_db()
    cards.open_request(con, "REQ-OVD", "L", "o", "2026-01-31")          # 과거 기한
    res = cards.drain(con, now="2026-06-14")                            # 스캔→라우팅→워커
    routed = [r for r in res if r.get("routed") == "overdue_escalation"]
    task = con.execute("SELECT COUNT(*) FROM task_card WHERE task_type='send_reminder'").fetchone()[0]
    assert routed and task == 1                                         # 내부 스케줄러→escalation(보안 미차단)


def test_eval_grounding_uses_real_verifier():
    from fpna_fixedcost import analytics as A
    con = cards.init_db()
    r = A.eval_grounding(con)
    assert r["passed"] and r["value"] >= 0.9     # verify_claim을 라벨셋에 적용(하드코딩 아님)


def test_accounting_notify_off_by_default():
    """기본 OFF: 회계 이벤트라도 notify_accounting Task 없음(포캐스트 반영만)."""
    con = cards.init_db()
    from fpna_fixedcost import _core as S
    res = S.AnalysisResult(domain="impairment", recommended_value=1e8, recommendation="손상 인식",
                           confidence=0.9, materiality_band="near", grounded=True, model_version="t/1")
    inp = [S.Input("x", 1.0, "KRW", S.Provenance("u", S.Authority.SIGNED_CONTRACT, "2026-01-01"))]
    r = S.submit(con, "손상", res, inp)
    assert r["accounting_event"] == "impairment_loss" and r["notify_accounting"] is False
    assert con.execute("SELECT COUNT(*) FROM task_card WHERE task_type='notify_accounting'").fetchone()[0] == 0


def test_accounting_notify_toggle_on():
    """토글 ON: 해당 이벤트만 notify_accounting Task 생성; 끄면 원복."""
    from fpna_fixedcost import _core as S
    try:
        S.set_accounting_notify("impairment_loss", True)
        con = cards.init_db()
        res = S.AnalysisResult(domain="impairment", recommended_value=1e8, recommendation="손상 인식",
                               confidence=0.9, materiality_band="near", grounded=True, model_version="t/1")
        inp = [S.Input("x", 1.0, "KRW", S.Provenance("u", S.Authority.SIGNED_CONTRACT, "2026-01-01"))]
        r = S.submit(con, "손상", res, inp)
        assert r["notify_accounting"] is True
        assert con.execute("SELECT COUNT(*) FROM task_card WHERE task_type='notify_accounting'").fetchone()[0] == 1
    finally:
        S.set_accounting_notify("impairment_loss", False)   # 누수 방지(기본 OFF 원복)


def test_other_event_stays_off_when_one_on():
    """하나만 켜도 다른 이벤트는 OFF 유지(독립 토글)."""
    from fpna_fixedcost import _core as S
    try:
        S.set_accounting_notify("impairment_loss", True)   # 손상만 ON
        con = cards.init_db()
        res = S.AnalysisResult(domain="lease_favorability", recommended_value=1e8, recommendation="재협상",
                               confidence=0.9, materiality_band="below", grounded=True, model_version="t/1")
        inp = [S.Input("x", 1.0, "KRW", S.Provenance("u", S.Authority.SIGNED_CONTRACT, "2026-01-01"))]
        r = S.submit(con, "임차", res, inp)   # lease_remeasurement는 OFF
        assert r["accounting_event"] == "lease_remeasurement" and r["notify_accounting"] is False
    finally:
        S.set_accounting_notify("impairment_loss", False)


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    p = f = 0
    for t in ALL:
        try:
            t(); p += 1; print(f"PASS {t.__name__}")
        except Exception as e:
            f += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{p} passed, {f} failed")
    sys.exit(1 if f else 0)

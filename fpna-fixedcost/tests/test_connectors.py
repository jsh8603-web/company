"""test_connectors.py — 외부 경계 어댑터(파일 랜딩존) 오프라인 검증.
랜딩존에 이벤트 파일을 떨어뜨리면 실제 카드 함수가 발화하는지 확인(승인/거부/회신/계약/노트/1주기)."""
import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fpna_fixedcost import _core as S
from fpna_fixedcost import connectors as C


def _tmp():
    d = tempfile.mkdtemp(prefix="fpna_inbox_"); return d

def _drop(d, name, ev):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(ev, f, ensure_ascii=False)

def one(con, q, *p): return con.execute(q, p).fetchone()

def mkres(domain, mat="material"):
    return S.AnalysisResult(domain=domain, recommended_value=100.0, recommendation="권고",
                            confidence=0.8, materiality_band=mat, grounded=True, model_version="t/1")
def mkinp():
    return [S.Input("x", 1.0, "KRW", S.Provenance("u", S.Authority.SIGNED_CONTRACT, "2026-01-01"))]


def test_approval_event_fires_approve():
    """E1: approval(approve) 이벤트 → approve_task 발화 → Task approved, processed/ 이동."""
    con = S.init_db(); d = _tmp()
    try:
        r = S.submit(con, "q", mkres("buy_vs_lease"), mkinp())
        tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
        _drop(d, "a1.json", {"type": "approval", "event_id": "a1", "task_id": tid, "approver": "controller", "decision": "approve"})
        out = C.poll_inbox(con, d)
        assert out[0]["type"] == "approval"
        assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "approved"
        assert os.path.exists(os.path.join(d, "processed", "a1.json"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_reject_event_sets_rejected():
    """E1: approval(reject) → reject_task → Task rejected."""
    con = S.init_db(); d = _tmp()
    try:
        r = S.submit(con, "q", mkres("buy_vs_lease"), mkinp())
        tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
        _drop(d, "r1.json", {"type": "approval", "event_id": "r1", "task_id": tid, "approver": "controller", "decision": "reject", "reason": "근거 부족"})
        C.poll_inbox(con, d)
        assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "rejected"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_sod_violation_routes_to_rejected_folder():
    """E1: 승인자=요청자 → SoD 차단, rejected/ 폴더로 격리, Task는 pending 유지."""
    con = S.init_db(); d = _tmp()
    try:
        r = S.submit(con, "q", mkres("buy_vs_lease"), mkinp())
        tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
        _drop(d, "s1.json", {"type": "approval", "event_id": "s1", "task_id": tid, "approver": "fpna-analyst", "decision": "approve"})
        out = C.poll_inbox(con, d)
        assert "SoD" in out[0]["error"]
        assert os.path.exists(os.path.join(d, "rejected", "s1.json"))
        assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "pending_approval"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_inbound_reply_event_enqueues():
    """E2: inbound_reply 이벤트 → open_request + correlated work_item 적재."""
    con = S.init_db(); d = _tmp()
    try:
        _drop(d, "i1.json", {"type": "inbound_reply", "event_id": "i1", "request_id": "REQ-1",
                             "open_request": True, "fcst_line": "HQ_lease_pangyo",
                             "payload": {"kind": "lease_comps", "subject": {}, "comps": []}})
        C.poll_inbox(con, d)
        assert one(con, "SELECT trust FROM work_item WHERE dedup_key='i1'")[0] == "correlated"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_contract_event_trusted_vs_untrusted():
    """E3: contract(trusted) → internal 처리 / 미신뢰 → unsolicited(검토)."""
    con = S.init_db(); d = _tmp()
    try:
        _drop(d, "c1.json", {"type": "contract", "event_id": "c1", "raw_ref": "sp://contracts/ok.pdf",
                             "trusted": True, "payload": {"contract": {}}})
        _drop(d, "c2.json", {"type": "contract", "event_id": "c2", "raw_ref": "sp://contracts/evil.pdf",
                             "trusted": False, "payload": {"contract": {}}})
        C.poll_inbox(con, d)
        assert one(con, "SELECT trust FROM work_item WHERE dedup_key='c1'")[0] == "internal"
        assert one(con, "SELECT trust FROM work_item WHERE dedup_key='c2'")[0] == "unsolicited"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_cycle_smoke():
    """E10: 1주기(poll→drain→outbox→decay)가 이벤트를 끝까지 처리하고 sink까지 도달."""
    con = S.init_db(); d = _tmp()
    try:
        os.environ["FPNA_OUTBOX"] = os.path.join(d, "outbox")
        r = S.submit(con, "q", mkres("buy_vs_lease"), mkinp())
        tid = one(con, "SELECT id FROM task_card WHERE analysis_id=?", r["analysis_id"])[0]
        _drop(d, "a1.json", {"type": "approval", "event_id": "a1", "task_id": tid, "approver": "controller", "decision": "approve"})
        summary = C.run_cycle(con, inbox_dir=d, sender="file")
        assert summary["polled"] >= 1 and summary["sent"] >= 1
        assert one(con, "SELECT status FROM task_card WHERE id=?", tid)[0] == "done"   # 승인→실행→done
        # file_sender가 outbox 폴더에 발송요청 기록
        assert any(fn.endswith(".json") for fn in os.listdir(os.path.join(d, "outbox")))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_outlook_sender_dep_gated():
    """E7: win32com 미설치 환경에서 outlook_com_sender 호출 → 의존성 에러(깨지지 않고 명확)."""
    con = S.init_db()
    import importlib.util
    if importlib.util.find_spec("win32com") is not None:
        return  # 호스트에 COM 있으면 스킵(샌드박스엔 없음)
    try:
        C.outlook_com_sender(con, 1, "task:1", "send_reminder")
        raise AssertionError("의존성 없는데 에러가 안 남")
    except RuntimeError as e:
        assert "win32com" in str(e)


def test_odbc_read_only_guard():
    """E6: 쓰기성 쿼리 차단(단방향) + DSN 미지정 차단 — 드라이버 없이도 가드는 동작(오프라인)."""
    try:
        C.odbc_actuals_fetcher("DELETE FROM gl_actuals")
        raise AssertionError("쓰기 쿼리가 막히지 않음")
    except ValueError as e:
        assert "읽기 전용" in str(e)
    try:
        C.odbc_actuals_fetcher("SELECT 1", conn_str="")   # DSN 없음
        raise AssertionError("DSN 없는데 통과")
    except ValueError as e:
        assert "DSN" in str(e) or "연결" in str(e)


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def run_all():
    p, f = 0, []
    for fn in ALL:
        try:
            fn(); print(f"PASS {fn.__name__}"); p += 1
        except Exception as e:
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}"); f.append(fn.__name__)
    print(f"\n{p} passed, {len(f)} failed")
    return not f


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)

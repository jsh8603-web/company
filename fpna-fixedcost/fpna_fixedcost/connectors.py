"""connectors.py — 외부 경계 어댑터 (폐쇄망 구현체).

설계: 모든 인바운드는 **SharePoint 동기 폴더(파일 랜딩존)** 의 JSON 이벤트를 폴링해 카드만 방출한다
(외부 입력=데이터, 지시 아님 §6.2). 인바운드 HTTP 엔드포인트가 필요 없어 사내 방화벽/프록시 제약에 부합하고,
기존 poll/drain 모델과 동일하다. 운영 전환 시 전송 계층만 Teams/SharePoint/Outlook/ERP로 교체한다.

이벤트 계약(랜딩존 *.json):
- approval     : {"type":"approval","event_id":"..","task_id":N,"approver":"..","decision":"approve|reject","reason":".."}
- inbound_reply: {"type":"inbound_reply","event_id":"..","request_id":"REQ-..","open_request":bool,"fcst_line":"..","payload":{..}}
- contract     : {"type":"contract","event_id":"..","raw_ref":"sp://contracts/..","trusted":bool,"payload":{"contract":{..}}}
- note         : {"type":"note","event_id":"..","note_id":"..","confirmed":bool,"frontmatter":{..},"body":".."}
"""
import os, json, glob, shutil
from ._core import (approve_task, reject_task, enqueue_work_item, open_request, route_note,
                    drain, process_outbox, apply_confidence_decay, SENDERS, SoDViolation)

DEFAULT_INBOX = os.environ.get("FPNA_INBOX", "/tmp/fpna/inbox")
DEFAULT_OUTBOX = os.environ.get("FPNA_OUTBOX", "/tmp/fpna/outbox")


def _move(path, sub):
    dest = os.path.join(os.path.dirname(path), sub)
    os.makedirs(dest, exist_ok=True)
    shutil.move(path, os.path.join(dest, os.path.basename(path)))


def _dispatch(con, ev, path, now):
    t = ev.get("type")
    if t == "approval":
        if ev.get("decision", "approve") == "approve":
            return approve_task(con, ev["task_id"], approver=ev["approver"], now=now)
        return reject_task(con, ev["task_id"], approver=ev["approver"], reason=ev.get("reason", ""), now=now)
    if t == "inbound_reply":
        if ev.get("open_request"):
            open_request(con, ev["request_id"], ev.get("fcst_line", ""), ev.get("owner", "fixedcost-fpna"), ev.get("due", now), now=now)
        return enqueue_work_item(con, "outlook", ev.get("raw_ref", path), ev["event_id"],
                                 correlation_token=f"[{ev['request_id']}]", payload=ev["payload"], now=now)
    if t == "contract":
        # 신뢰 라이브러리(trusted)면 internal로 자동처리, 아니면 기본 unsolicited→검토(보안)
        return enqueue_work_item(con, "sharepoint", ev.get("raw_ref", "sp://contracts/x.pdf"), ev["event_id"],
                                 payload=ev["payload"], now=now, trust="internal" if ev.get("trusted") else None)
    if t == "note":
        return route_note(con, ev["note_id"], ev.get("frontmatter", {}), ev.get("body", ""),
                          now=now, confirmed=ev.get("confirmed", False))
    return {"skipped": t}


def poll_inbox(con, inbox_dir=DEFAULT_INBOX, now="2026-06-14"):
    """랜딩존(*.json) 폴링 → 타입별 디스패치 → processed/(또는 rejected/error)로 이동. 결함격리."""
    os.makedirs(inbox_dir, exist_ok=True)
    out = []
    for path in sorted(glob.glob(os.path.join(inbox_dir, "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                ev = json.load(f)
            r = _dispatch(con, ev, path, now)
            out.append({"event": name, "type": ev.get("type"), "result": r})
            _move(path, "processed")
        except SoDViolation as e:
            out.append({"event": name, "error": f"SoD: {e}"}); _move(path, "rejected")
        except Exception as e:
            out.append({"event": name, "error": str(e)[:120]}); _move(path, "error")
    return out


def file_sender(con, task_id, idem, side_effect, now="2026-06-14"):
    """운영 기본 sender: 발송요청 JSON을 outbox 폴더에 기록(Power Automate/Outlook이 픽업). 멱등(파일명=idem)."""
    outbox = os.environ.get("FPNA_OUTBOX", DEFAULT_OUTBOX)   # 런타임 구성(호출 시점)
    os.makedirs(outbox, exist_ok=True)
    p = os.path.join(outbox, f"{idem.replace(':', '_')}.json")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"task_id": task_id, "idempotency_key": idem, "side_effect": side_effect, "at": now},
                      f, ensure_ascii=False)
    return f"file::{idem}"


SENDERS["file"] = file_sender   # 운영: 'outlook_com'(Outlook COM 통지)을 같은 시그니처로 등록. GL 기록 경로 없음(단방향)


# ── E7/E2 Outlook COM (사내 제약=COM) · E6 ERP ODBC 읽기 ─────────────────────
# 의존성은 호출 시점 lazy-import(미설치 시 깔끔한 에러). 코어 stdlib 불변식 유지.
import importlib

def _require(mod, hint):
    try:
        return importlib.import_module(mod)
    except Exception as e:
        raise RuntimeError(f"의존성 '{mod}' 필요({hint}). deps_check.py로 확인 후 설치/화이트리스트.") from e


def outlook_com_sender(con, task_id, idem, side_effect, now="2026-06-14"):
    """E7: 승인된 Task를 Outlook COM으로 발송(멱등은 outbox가 보장). 환경변수 FPNA_OUTLOOK_DRAFT_ONLY=1이면
    발송 대신 Drafts 저장(사람 최종 확인). 발송 대상/제목/본문은 Task payload에서."""
    win32 = _require("win32com.client", "Outlook COM 발송 E7")
    row = con.execute("SELECT payload FROM task_card WHERE id=?", (task_id,)).fetchone()
    payload = json.loads(row[0]) if row and row[0] else {}
    mail = win32.Dispatch("Outlook.Application").CreateItem(0)   # 0=olMailItem
    mail.To = payload.get("to", os.environ.get("FPNA_DEFAULT_TO", ""))
    mail.Subject = payload.get("subject", f"[FP&A 고정비] {side_effect} (Task #{task_id})")
    mail.Body = payload.get("body", json.dumps(payload, ensure_ascii=False, indent=2))
    if os.environ.get("FPNA_OUTLOOK_DRAFT_ONLY", "0") == "1":
        mail.Save(); return f"outlook_draft::{idem}"
    mail.Send(); return f"outlook_sent::{idem}"


SENDERS["outlook_com"] = outlook_com_sender   # 호스트에 Outlook 있을 때 process_outbox(sender='outlook_com')


def poll_outlook_replies(con, inbox_dir=DEFAULT_INBOX, now="2026-06-14", folder=6):
    """E2: Outlook COM(MAPI) 받은편지함에서 미회신 요청 토큰([REQ-..]) 메일을 스캔 → inbound_reply 이벤트를
    랜딩존에 기록(이후 poll_inbox가 소비). 구조화 회신은 첨부 JSON 권장; 본문 파싱은 메일 양식 파서로."""
    win32 = _require("win32com.client", "Outlook COM 회신 수신 E2")
    ns = win32.Dispatch("Outlook.Application").GetNamespace("MAPI")
    items = ns.GetDefaultFolder(folder).Items   # 6=olFolderInbox
    open_tokens = [r[0] for r in con.execute("SELECT correlation_token FROM request_register WHERE status='sent'")]
    os.makedirs(inbox_dir, exist_ok=True); written = []
    for m in items:
        subj = getattr(m, "Subject", "") or ""
        tok = next((t for t in open_tokens if t and t.strip("[]") in subj), None)
        if not tok:
            continue
        eid = f"mail-{(getattr(m, 'EntryID', 'x') or 'x')[:16]}"
        ev = {"type": "inbound_reply", "event_id": eid, "request_id": tok.strip("[]"),
              "payload": {"kind": "lease_comps_raw", "subject_text": subj, "body": getattr(m, "Body", "")}}
        p = os.path.join(inbox_dir, f"{eid}.json")
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(ev, f, ensure_ascii=False)
            written.append(eid)
    return written


def odbc_actuals_fetcher(query, params=(), dsn=None, conn_str=None):
    """E6: 결산/실적 READ 전용 ODBC. SELECT/WITH만 허용(시스템은 GL에 절대 쓰지 않음 — 단방향 불변식).
    순수파이썬 pypyodbc 우선(드라이버 매니저만 필요), 없으면 pyodbc. 반환=행 dict 리스트(→ ingest_snapshot/variance)."""
    q = query.strip().lower()
    if not (q.startswith("select") or q.startswith("with")):
        raise ValueError("E6 읽기 전용: SELECT/WITH만 허용(시스템은 GL 직기록 안 함).")
    cs = conn_str or (f"DSN={dsn}" if dsn else os.environ.get("FPNA_ERP_ODBC", ""))
    if not cs:
        raise ValueError("ODBC DSN/연결문자열 필요(FPNA_ERP_ODBC 또는 dsn=).")
    mod = None
    for cand in ("pypyodbc", "pyodbc"):
        try:
            mod = importlib.import_module(cand); break
        except Exception:
            continue
    if mod is None:
        raise RuntimeError("ODBC 모듈 필요(pypyodbc 순수파이썬 권장 또는 pyodbc). deps_check.py 확인.")
    dbcon = mod.connect(cs)
    try:
        cur = dbcon.cursor(); cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        dbcon.close()


def run_cycle(con, inbox_dir=DEFAULT_INBOX, now="2026-06-14", sender="file", decay=True):
    """OS 스케줄러 진입점(1주기): 인박스 폴링 → 드레인(overdue 스캔·rebuild 소비 포함) → outbox 실행 → 감쇠 스윕.
    Windows Task Scheduler/cron이 `python -m fpna_fixedcost.run_cycle`로 주기 호출."""
    polled = poll_inbox(con, inbox_dir, now)
    drained = drain(con, now)
    sent = process_outbox(con, now, sender=sender)
    decayed = apply_confidence_decay(con, asof=now) if decay else []
    return {"polled": len(polled), "drained": len(drained), "sent": len(sent), "decayed": len(decayed),
            "detail": {"polled": polled, "sent": sent}}

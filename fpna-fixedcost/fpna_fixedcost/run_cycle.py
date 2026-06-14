"""OS 스케줄러 진입점. Windows Task Scheduler/cron이 주기적으로 실행:
    set FPNA_DB=\\\\sharepoint-sync\\fpna\\state.db  &  set FPNA_INBOX=...  &  set FPNA_OUTBOX=...
    python -m fpna_fixedcost.run_cycle
파일 DB(FPNA_DB)를 열어 1주기(poll→drain→outbox→decay)를 돌리고 요약을 stdout에 남긴다."""
import os, json, sqlite3
from ._core import init_db
from .connectors import run_cycle, DEFAULT_INBOX

def main():
    db = os.environ.get("FPNA_DB", "/tmp/fpna/state.db")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = init_db(db)                      # 영속 파일 DB(스키마 멱등 생성)
    summary = run_cycle(con, inbox_dir=os.environ.get("FPNA_INBOX", DEFAULT_INBOX))
    con.close()
    print(json.dumps({"cycle": summary}, ensure_ascii=False))

if __name__ == "__main__":
    main()

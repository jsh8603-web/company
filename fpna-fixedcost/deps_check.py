"""deps_check.py — 로컬 호스트에서 커넥터별 '바로 구현 가능' 여부 점검(stdlib only).
실행: python deps_check.py
코어는 stdlib+sqlite3, 보고서는 openpyxl, Outlook=win32com(COM), ERP/결산 ODBC=pypyodbc(순수파이썬) 또는 pyodbc."""
import importlib, sys, platform


def have(mod):
    try:
        importlib.import_module(mod); return True
    except Exception:
        return False


def main():
    py_ok = sys.version_info[:2] >= (3, 10)
    caps = {
        "openpyxl (보고서 빌드)": have("openpyxl"),
        "win32com.client / pywin32 (Outlook COM: E2,E7)": have("win32com.client"),
        "pypyodbc (ODBC 순수파이썬: E6 권장)": have("pypyodbc"),
        "pyodbc (ODBC 컴파일: E6 대안)": have("pyodbc"),
    }
    print(f"Python {platform.python_version()}  (>=3.10: {'OK' if py_ok else 'NO'})  | OS: {platform.system()} {platform.release()}")
    print("의존성:")
    for k, v in caps.items():
        print(f"  [{'OK  ' if v else '없음 '}] {k}")

    odbc_ok = caps["pypyodbc (ODBC 순수파이썬: E6 권장)"] or caps["pyodbc (ODBC 컴파일: E6 대안)"]
    com_ok = caps["win32com.client / pywin32 (Outlook COM: E2,E7)"]
    readiness = {
        "파일 랜딩존(poll_inbox·file_sender·run_cycle) E1–E4,E10,E12": py_ok,         # stdlib only
        "Teams 승인 E1 (Power Automate, 노코드)": True,                                # 로컬 파이썬 의존성 없음
        "보고서 빌드 (openpyxl)": caps["openpyxl (보고서 빌드)"],
        "Outlook 발송/회신 E2,E7 (COM)": com_ok,
        "ERP/결산 ODBC 읽기 E6": odbc_ok,
        "GL 분개 E8 (제안 아티팩트만, GL 직기록 없음)": py_ok,                          # 산출물=파일, 전기는 사람
    }
    print("\n커넥터 즉시 구현 가능 여부:")
    for k, v in readiness.items():
        print(f"  [{'가능    ' if v else '의존성 필요'}] {k}")

    # ODBC 드라이버 열거(가능 시)
    if caps["pyodbc (ODBC 컴파일: E6 대안)"]:
        try:
            import pyodbc
            drv = pyodbc.drivers()
            print("\nODBC 드라이버:", ", ".join(drv) if drv else "(없음 — DSN/드라이버 설치 필요)")
        except Exception as e:
            print("\nODBC 드라이버 열거 실패:", e)
    elif odbc_ok:
        print("\nODBC: pypyodbc 사용 가능 — 시스템 DSN/드라이버 매니저 필요(ODBC 데이터원본 관리자에서 DSN 확인).")
    else:
        print("\nODBC: 미설치 — DSN 있으면 pypyodbc(순수파이썬, 단일 .py 벤더링) 권장.")

    print("\n요약: 위 '가능' 항목은 추가 작업 없이 바로 구현 착수 가능. '의존성 필요'는 해당 모듈 화이트리스트/설치 후 착수.")


if __name__ == "__main__":
    main()

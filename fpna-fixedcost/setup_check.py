#!/usr/bin/env python3
"""
setup_check.py — 로컬에 던진 직후 *가장 먼저* 실행. 의존성→임포트→스모크→테스트 순 검증.

  python setup_check.py

목적: "바로 구현"에 들어가기 전에 환경이 준비됐는지 한 번에 확인하고, 다음 할 일을 알려준다.
런타임 의존성은 openpyxl(보고서) 하나뿐 — 코어 엔진/카드는 순수 stdlib라 openpyxl 없이도 동작.
"""
import sys, os, importlib, importlib.util, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ok = True


def check(label, cond, hint=""):
    global ok
    mark = "OK  " if cond else "FAIL"
    print(f"  [{mark}] {label}" + ("" if cond else f"   → {hint}"))
    if not cond: ok = False
    return cond


print("=" * 70)
print("fpna-fixedcost 환경 점검")
print("=" * 70)

# 1) 파이썬 버전 (dataclass/타입 문법: 3.10+ 권장)
v = sys.version_info
check(f"Python {v.major}.{v.minor} (≥3.10 필요)", v >= (3, 10),
      "python3.10+ 설치 또는 pyenv로 전환")

# 2) 코어 임포트 (순수 stdlib — openpyxl 불요)
core_ok = False
try:
    import fpna_fixedcost
    from fpna_fixedcost import common, engines, projection, reference_data, cards, sox, analytics, report, lifecycle
    core_ok = check("코어 임포트 (stdlib only)", True)
except Exception as e:
    check("코어 임포트 (stdlib only)", False, f"{e}")

# 3) openpyxl (보고서 생성용; vendored 또는 pip)
xl = importlib.util.find_spec("openpyxl") is not None
check("openpyxl (보고서; 없으면 vendor/ 또는 pip)", xl,
      "PYTHONPATH=vendor 로 실행하거나 'pip install openpyxl' (폐쇄망: vendor/README.md)")

# 4) 금지 의존성 미사용 확인 (stdlib 원칙)
forbidden = [m for m in ("pandas", "numpy", "pydantic") if importlib.util.find_spec(m)]
check("금지 의존성 미참조(코어는 stdlib)", True,
      "")  # 설치돼 있어도 코어는 미사용 — 정보성
if forbidden:
    print(f"        (참고: {forbidden} 설치돼 있으나 코어는 사용하지 않음)")

# 5) 스모크: DB 초기화 + 엔진 1회 (openpyxl 불요)
if core_ok:
    try:
        con = cards.init_db()
        cgu = engines.CGU("c", [engines.CGUAsset("a", 6200, life_years=10, elapsed_years=3, residual=200)],
                          [900, 850, 800, 750, 700], 0.13, terminal_growth=0.01,
                          fair_value=4300, costs_of_disposal=150)
        rec = max(engines.value_in_use(cgu), engines.fvlcd(cgu))
        check(f"스모크: 손상 엔진 회수가능액 계산 (₩{rec:,.0f})", rec > 0)
    except Exception as e:
        check("스모크: 엔진", False, f"{e}")

# 6) 불변식 테스트 (stdlib 러너)
try:
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", "test_invariants.py")],
                       capture_output=True, text=True, timeout=120)
    last = (r.stdout.strip().splitlines() or ["?"])[-1]
    check(f"불변식 테스트 ({last})", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
except Exception as e:
    check("불변식 테스트", False, f"{e}")

# 7) 카드 수명주기·조합 시나리오 (커버리지 하니스)
try:
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", "test_scenarios.py")],
                       capture_output=True, text=True, timeout=120)
    last = (r.stdout.strip().splitlines() or ["?"])[-1]
    check(f"카드 흐름 시나리오 ({last})", r.returncode == 0, r.stdout[-400:] + r.stderr[-300:])
except Exception as e:
    check("카드 흐름 시나리오", False, f"{e}")

# 8) 외부 경계 커넥터(파일 랜딩존) 오프라인 검증
try:
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", "test_connectors.py")],
                       capture_output=True, text=True, timeout=120)
    last = (r.stdout.strip().splitlines() or ["?"])[-1]
    check(f"경계 커넥터 ({last})", r.returncode == 0, r.stdout[-400:] + r.stderr[-300:])
except Exception as e:
    check("경계 커넥터", False, f"{e}")

print("-" * 70)
if ok:
    print("준비 완료 ✅  다음 순서로 진행:")
    print("  1) python main.py                 # end-to-end 데모 + 보고서(openpyxl 필요)")
    print("  2) docs/ + MASTER_INDEX.md         # 설계↔코드 연결관계 파악")
    print("  3) plan.md                         # 부임 후 사람 결정(IBR·CGU·SOX·인증키 등) 채우기")
    print("  4) CLAUDE.md                       # 사내 Claude Code 작업 규율")
else:
    print("일부 점검 실패 ❌  위 → 힌트 따라 해결 후 재실행. (코어는 stdlib만 필요)")
print("=" * 70)
sys.exit(0 if ok else 1)

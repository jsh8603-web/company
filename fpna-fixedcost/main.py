"""fpna-fixedcost 진입점.

  python main.py            # end-to-end 데모(엔진→큐→승인→증적→보고서) 실행
회사 폐쇄망: vendored openpyxl(vendor/) 외 의존 없음. 산출 보고서 fixed_cost_report.xlsx.
"""
from fpna_fixedcost._core import main

if __name__ == "__main__":
    main()

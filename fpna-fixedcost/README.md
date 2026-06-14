# fpna-fixedcost

물류 고정비 FP&A를 위한 **계약 중심 의사결정 + 자동화 파이프라인**. 순수 stdlib + vendored openpyxl로 회사 폐쇄망 드롭인.

계약 결정(건물 임차 유불리·트럭 구매 vs 리스·기계 손상)을 *불확실성 하의 분석+권고*로 카드화하고, 투영(상각·리스 스케줄)으로 fcst에 흘리며, 트리거/큐(요청·회신·dedup·보안)→승인(SoD)→outbox(exactly-once)→ICFR 증적→Variance Bridge→View Contract 보고서까지 한 흐름으로 닫는다.

## 빠른 시작
```bash
PYTHONPATH=vendor python main.py        # 데모 + fixed_cost_report.xlsx(5시트) 생성
python tests/test_invariants.py         # 11개 불변식 회귀
```

## 구조
```
fpna-fixedcost/
  fpna_fixedcost/
    _core.py          # 검증된 구현(단일 모듈; 폐쇄망 vendored 단순성)
    common engines projection reference_data cards sox analytics report   # 도메인 임포트 표면
  main.py             # 진입점
  tests/              # 핵심 불변식(stdlib/pytest)
  playbooks/          # 시드 4종(자기확장 포함)
  vendor/             # openpyxl 벤더링 안내
  docs/               # 설계 SSOT·R3·R4·자산 v1/v2·데이터 획득 스펙
  CLAUDE.md           # 회사 Claude Code 컨텍스트(불변식·모듈맵·규율)
  MASTER_INDEX.md     # 공백→구현 추적, 표준·데이터 출처, 전체 인덱스
```

## 근거 표준 (코드에 박힘)
IFRS 16(리스·IBR) · IAS 16(상각·구성요소) · IAS 36(손상·CGU·VIU) · RICS 비교법 ·
COSO/PCAOB AS 2201(ICFR) · ISA 320(중요성) · W3C PROV · SemVer · Fellegi-Sunter(ER).

## 한국 데이터 출처
한국부동산원 상업용부동산 임대동향조사(REB, 지역 임대지표) · 국토교통부 실거래가(RTMS) ·
한국은행 ECOS(금리·환율) · 통계청 KOSIS(CPI). 폐쇄망: 외부 수집→SharePoint 착지→reference_data.

## 핵심 원칙
- 숫자(→fcst)와 행동 권고(→Task 승인) 분리. 계산은 엔진, 판단(CGU·IBR·비교조정)은 사람.
- 무출처/허위출처 자동반영 금지(grounding). high-tier(손상) 검토 강제. SoD·outbox·감사 계보.
- 모델/플레이북 변경은 eval 배포 게이트 통과 필수.

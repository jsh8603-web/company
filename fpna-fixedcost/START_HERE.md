# START HERE — 로컬 투하 후 0→1

이 패키지는 **계약 중심 고정비 FP&A 의사결정 + 자동화 파이프라인 + 콘텐츠 라이프사이클**의 전체(설계 문서 + 검증된 구현 + 배포 스캐폴딩)다. 회사 폐쇄망 드롭인.

## 30초 시작
```bash
python setup_check.py     # ① 의존성·임포트·스모크·테스트 한 번에 점검 (가장 먼저)
python main.py            # ② end-to-end 데모 0~15 + fixed_cost_report.xlsx(5시트) 생성
python tests/test_invariants.py   # ③ 핵심 불변식 회귀
```
런타임 의존성은 **openpyxl 하나**(보고서용). 코어 엔진/카드/라이프사이클은 **순수 stdlib**라 openpyxl 없이도 동작(보고서만 생략). 폐쇄망 벤더링: `vendor/README.md`, 실행은 `PYTHONPATH=vendor python main.py`.

## 무엇이 어디에 (연결관계는 MASTER_INDEX.md)
- `fpna_fixedcost/_core.py` — **검증된 구현 단일 코어**(1,700+줄). 모든 로직이 여기.
- `fpna_fixedcost/{common,engines,projection,reference_data,cards,sox,analytics,report,lifecycle}.py` — 도메인별 **임포트 표면**(코어 재노출). 깨끗한 import 경로. 단일 코어+facade는 폐쇄망 벤더링용 설계(STATUS.md 불변식).
- `docs/00~08` — 설계 SSOT·R3·R4·자산 v1/v2·데이터 획득·콘텐츠 라이프사이클·**외부 검토**.
- `MASTER_INDEX.md` — **공백→구현 추적 + 모듈 의존 DAG + 문서↔코드 매핑 + 데이터 흐름**. ← 연결관계는 여기서.
- `playbooks/` — 시드 4종(자기확장 포함).
- `CLAUDE.md` — 사내 Claude Code 상시 컨텍스트(불변식·규율).
- `STATUS.md` — **구현 상태(전부 구현·검증) + 흐름 보완 + 근거(논문/repo) + 설계 불변식**.
- `VERIFY_PLAN.md` — **애매 항목 방향 확정 + 근거 + 검증 + 구현 계획**(렌더·발송·수집·검증·ER 스케일).
- `plan.md` — **로컬 작업 = 의존성 확인 + 구현(슬롯 B·설정 주입 C)**. 결정/검토 항목 없음.

## 구현 순서
1. `setup_check.py` 통과 → 환경 OK.
2. `MASTER_INDEX.md`로 설계↔코드 연결 파악(필요한 스펙은 `docs/`).
3. `plan.md`대로 구현: 설정 주입(C1~C9, 위치·플레이스홀더 명시) + 코드 슬롯(B1~B7).
4. 순서: C9(키·프록시)·C1·C3 주입 → B3(외부 어댑터) 연결 → 엔진이 실데이터로 동작 → B1·B2(워커·발송) → B4(PPT/PDF).
5. 구현 상태는 STATUS.md(전부 구현, 22 테스트). 남은 건 운영값 주입·외부계 연결(plan.md).

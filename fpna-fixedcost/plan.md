# plan.md — 로컬 작업 (의존성 확인 + 구현)

기능은 전부 구현·검증됨(STATUS.md, 22 테스트). 기본값·오프라인 경로로 *지금 동작*한다.
로컬에서 할 일은 둘뿐: **① 의존성 확인 → ② 구현(운영 연결: 실계·실값 꽂기)**. 결정/검토 항목 없음.

## ① 의존성 확인
```
python setup_check.py     # Python≥3.10·코어 stdlib·openpyxl·스모크·테스트 22개
```
openpyxl 없으면 `vendor/README.md`로 벤더링(`PYTHONPATH=vendor python main.py`) 또는 `pip install openpyxl`.

## ② 구현 — 운영 연결 (인터페이스 동일, 기본값 위에 실계/실값 꽂기)
| # | 작업 | 어떻게 | 현재 동작 |
|---|------|--------|-----------|
| 1 | 외부 통지 | `SENDERS["outlook_com"]=...`(log_sender와 동일 시그니처) → `process_outbox(sender="outlook_com")`. sender=통지 채널(메일/Teams), GL 기록 없음 | log_sender→sent_log 기록(멱등) |
| 2 | 외부 데이터 | `api_fetcher`에 OpenAPI 키(env `GODATA_API_KEY` 등)·승인 프록시 → file_fetcher 대신 | file_fetcher 오프라인 적재 |
| 3 | IBR/CGU 실값 | `seed_full_ibr_matrix` 행을 treasury 값으로·CGU 입력을 감사 합의로 교체 | KRW 6행 기본값·데모 CGU |
| 4 | SOX 범위 | `CONTROL_MATRIX`·`DOMAIN_TASK`(risk_tier)를 감사 합의로 조정 | 6통제·손상=high 시드 |
| 5 | house_style | `HOUSE_STYLE`에 전임 CEO 보고 톤 코퍼스 반영 | action_title·구조 기본값 |
| 6 | 보존/PII | `RETENTION_POLICY`·`PII_POLICY`를 법무 정책으로 | 7y/S1 off-device 기본값 |
| 7 | 렌더 연결 | 덱/문서 스펙(`build_board_deck_spec`/`build_report_spec`)을 BIGS deck_system·academic-slide·PDF 툴체인에 전달 | 스펙 생성(grounded·house_style) |
| 8 | ERP/WMS 입력 | GL export·고정자산대장·가동률을 fetcher로 적재(2와 동일) | 모의 스냅샷 |

## 순서
의존성 확인 → 2(데이터 키·프록시)·3(IBR/CGU) → 엔진이 실데이터로 동작 → 1(발송)·4(SOX) → 7(렌더). 5·6·8은 병행.

## 외부 경계 엔드포인트 (구현안 — INTEGRATION.md 전수조사)
경계는 함수 인터페이스가 아니라 **파일 랜딩존 커넥터**로 구현: 인바운드는 SharePoint 동기 폴더의 JSON 이벤트를 `poll_inbox`가 폴링, 아웃바운드는 `file_sender`, 스케줄러는 `run_cycle`(`python -m fpna_fixedcost.run_cycle`). 엔드포인트 E1–E12(승인/회신/계약/노트/참조데이터/GL실적 읽기/메일통지/렌더/스케줄러/시크릿/영속 — GL 쓰기 없음)를 매니페스트로 열거하고, E1(승인)은 Teams Adaptive Card + Power Automate 양방향 플로우로 상세화. 승인 시점=Task pending_approval→approved(SoD)→outbox→실행(이전 부작용 없음). 검증: tests/test_connectors.py 6 PASS(랜딩존 파일 드롭→실제 카드 발화).

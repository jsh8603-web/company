# INTEGRATION.md — 외부 경계 엔드포인트 전수조사 + 구현안

시스템은 stdlib 엔진이고, 외부와 닿는 지점은 모두 **함수 인터페이스 + 기본 어댑터**로 존재한다.
이 문서는 (1) 경계 엔드포인트를 누락 없이 열거하고, (2) 폐쇄망 구현체(파일 랜딩존)와 운영 전환(Teams/SharePoint/Outlook/ERP)을 명시한다.

## 설계 원칙 — 파일 랜딩존 + 단일 폴링 주기
인바운드 HTTP 엔드포인트를 노출하지 않는다(사내 방화벽/프록시 제약). 대신 **SharePoint 동기 폴더**에
JSON 이벤트가 떨어지고, OS 스케줄러가 `run_cycle`을 주기 호출해 poll→drain→outbox→decay를 한 바퀴 돈다.
이는 기존 poll/drain 모델과 동일하며, 외부 입력은 카드만 생성(지시 아님 §6.2). 운영 전환 시 **전송 계층만** 교체.

```
[Teams/SharePoint/Outlook/ERP]  --(Power Automate가 JSON 기록)-->  [SharePoint 동기 폴더(inbox)]
                                                                          |
                          Windows Task Scheduler ──> python -m fpna_fixedcost.run_cycle
                                                                          |
                        poll_inbox → (approve_task/enqueue/route_note) → drain → process_outbox(file_sender)
                                                                          |
                                                          [outbox 폴더] --(Power Automate/COM)--> [Outlook 통지]
```

## 엔드포인트 매니페스트 (E1–E12)
| # | 엔드포인트 | 방향 | 트리거/표면 | 이전 상태 | 구현체(이번) | 운영 전환 |
|---|-----------|------|-------------|-----------|-------------|-----------|
| E1 | 승인 인입 | IN | 승인자 클릭 | `approve_task`/`reject_task` 함수만 | poll_inbox `approval` 이벤트 → approve/reject(SoD) | Teams Adaptive Card + Power Automate |
| E2 | 회신 인입 | IN | 자료요청 회신 | `enqueue_work_item` 함수만 | poll_inbox `inbound_reply` → correlated work_item | Outlook 규칙 → Power Automate → 폴더 |
| E3 | 계약 투입 | IN | 신규/개정 계약 | `enqueue_work_item` 함수만 | poll_inbox `contract`(trusted=internal/미신뢰=검토) | SharePoint 라이브러리 → Power Automate |
| E4 | 노트 캡처 | IN | Obsidian/VaultVoice | `route_note` 함수만 | poll_inbox `note`(confirmed→pipeline) | 노트 export → 폴더 |
| E5 | 참조데이터 풀 | IN | REB/ECOS/KOSIS OpenAPI | `api_fetcher`(오프라인) | `fetch_and_ingest` + env 키 | 스케줄 풀 → SharePoint 착지 → ingest_snapshot |
| E6 | GL/ERP 실적 | IN | 결산 실적 | `file_fetcher` | poll/fetch(파일) → variance/bootstrap | ERP export → 폴더 |
| E7 | 메일 발송 | OUT | 승인→outbox | `SENDERS['log']`(no-op) | **`file_sender`**(발송요청 JSON 기록) | `outlook_com`(COM) 또는 file→Power Automate |
| E9 | 덱/보고서 렌더 | OUT | 보드 spec | `build_*_spec`(spec만) | spec → 폴더 | BIGS deck_system/academic-slide/PDF 렌더 |
| E10 | 스케줄러 | TRIGGER | 주기 실행 | `drain` 함수만 | **`run_cycle` + `python -m fpna_fixedcost.run_cycle`** | Windows Task Scheduler/cron |
| E11 | 시크릿 | CONFIG | API 키 | env 읽기 산재 | env(`FPNA_*`, `GODATA_API_KEY`) | 사내 키 볼트/자격증명 관리자 |
| E12 | 영속/백업 | STATE | DB 위치 | `:memory:`/파일 | `FPNA_DB` 파일 경로(스키마 멱등) | SharePoint 동기 경로 + 일 백업 |

검증: tests/test_connectors.py가 E1–E4·E10을 오프라인(랜딩존 파일 드롭)으로 발화 확인(6 PASS).

## E1 상세 — Teams 승인 구현
### 승인 시점(코드 확정)
Task 카드 `pending_approval` → `approved`(approve_task, SoD: 승인자≠요청자) → 트랜잭셔널 outbox → `process_outbox`가 비로소 부작용 실행.
**승인 이전 외부 효과 없음.** 게이트 통과 결정은 숫자만 자동 반영되고 행동 Task는 승인 대기; 미통과·고위험(손상)은 숫자도 승인 시 반영.

### 승인 라우팅(SoD + 중요도)
| 결정 유형 | 승인자 | 근거 |
|-----------|--------|------|
| 일상(materiality below/near, tier med/low) | FP&A 리드 | 일반 통제 |
| material 또는 high-tier(손상·CGU·구매/리스 대형) | Controller/CFO | SOX 핵심통제·상향집계 편향 |
요청자는 보통 `fixedcost-fpna`(또는 worker/system); 승인자는 이와 달라야 함(C-SOD-01).

### Teams Adaptive Card(승인자에게 게시할 카드)
```json
{
  "type": "AdaptiveCard", "version": "1.5",
  "body": [
    {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": "고정비 의사결정 승인 요청"},
    {"type": "FactSet", "facts": [
      {"title": "질문", "value": "${question}"},
      {"title": "권고", "value": "${recommendation}"},
      {"title": "신뢰도", "value": "${confidence}"},
      {"title": "중요도", "value": "${materiality_band}"},
      {"title": "근거", "value": "${grounded}"},
      {"title": "민감도", "value": "${sensitivity}"},
      {"title": "Task", "value": "#${task_id} (${task_type}, ${risk_tier})"}
    ]},
    {"type": "TextBlock", "wrap": true, "isSubtle": true, "text": "승인 시 통지가 발송됩니다. 거부 시 검토 큐로 회송."}
  ],
  "actions": [
    {"type": "Action.Submit", "title": "승인", "style": "positive",
     "data": {"type": "approval", "task_id": "${task_id}", "decision": "approve"}},
    {"type": "Action.Submit", "title": "거부", "style": "destructive",
     "data": {"type": "approval", "task_id": "${task_id}", "decision": "reject"}}
  ]
}
```

### Power Automate 플로우(노코드, 양방향)
**아웃바운드(카드 게시):** 트리거 = SharePoint 폴더 `outbox/approval-requests/`에 새 파일(시스템이 pending Task를 카드 데이터로 기록) → "Post adaptive card and wait for a response"(Teams, 채널/대상=승인 라우팅 표) → 카드는 위 JSON.
**인바운드(클릭 결과):** 승인자 클릭 → Power Automate가 응답 캡처 → `approver`=클릭한 사용자(UPN), `event_id`=GUID 부여 → JSON을 inbox 랜딩존에 기록:
```json
{"type":"approval","event_id":"<guid>","task_id":<id>,"approver":"<UPN>","decision":"approve"}
```
→ 다음 `run_cycle`의 `poll_inbox`가 소비 → `approve_task`(SoD 재검증) → outbox → 발송. **승인자 신원은 클릭 사용자에서 오므로 시스템이 위조 불가**, SoD는 코드에서 한 번 더 강제.

### 멱등·보안
- `event_id`로 중복 클릭 방어(이미 approved Task는 approve_task가 비-pending 예외 → error/로 격리).
- 부작용은 `idempotency_key`(outbox)로 정확히 1회(process_outbox).
- SoD 위반 이벤트는 `rejected/` 폴더로 격리, Task는 pending 유지(재라우팅).

## 운영 체크리스트(전환 순서)
1. SharePoint 동기 폴더 3개(inbox/outbox/processed) + `FPNA_DB`/`FPNA_INBOX`/`FPNA_OUTBOX` 설정.
2. Windows Task Scheduler: `python -m fpna_fixedcost.run_cycle` 5–15분 주기.
3. E1 Power Automate 2개 플로우(카드 게시 / 응답 수집) — 위 계약.
4. E7 sender 교체: `SENDERS['outlook_com']`(Outlook COM) 등록 또는 file_sender + Power Automate. (시스템은 GL에 쓰지 않음)
5. E5 키(`GODATA_API_KEY` 등) 사내 볼트 주입; E2/E3/E6 Outlook/SharePoint/ERP → 폴더 플로우.
6. E9 spec 폴더를 BIGS/academic-slide 렌더 잡이 감시.

---

# 보완 — ERP/ODBC/COM 구체화 + 의존성 + 작업 순서

## ERP 두 경로 분리 (중요)
- **E6 결산/실적 읽기 = READ 전용.** variance bridge·bootstrap 입력. `odbc_actuals_fetcher`(SELECT/WITH만, 가드 강제). **ODBC DSN이 있으면 파일 export를 ODBC로 대체**(라이브, 수작업 export 제거). 시스템은 GL에 **절대 쓰지 않음**(단방향 불변식).
- **GL 쓰기 경로 없음.** FP&A는 GL에 전기하지 않는다. 손상 등 회계처리가 필요한 사안은 `escalate_impairment_to_accounting` Task로 **회계/컨트롤러팀에 통지(메일/Teams)** 하고, 포캐스트에는 수정 감가/손상손익이 내부 투영으로 반영될 뿐이다. GL 접점은 E6(읽기)뿐.

## ODBC (E6) 구현 스펙
- 모듈: **`pypyodbc`(순수파이썬, 단일 .py — openpyxl처럼 `vendor/`에 드롭인)** 우선 / 없으면 `pyodbc`(컴파일 wheel). 둘 다 시스템 ODBC 드라이버 매니저 필요(DSN 존재 시 충족).
- 호출: `odbc_actuals_fetcher("SELECT period,line,amount FROM v_closing WHERE ...", dsn="ERP_RO")` 또는 `conn_str=`/`FPNA_ERP_ODBC` env. 반환=행 dict 리스트 → `ingest_snapshot`/variance에 투입.
- 가드: SELECT/WITH 외 차단(ValueError), DSN 미지정 차단. 읽기 전용 계정 권장.

## Outlook COM (E7 발송 / E2 회신) 구현 스펙 (사내 제약=COM)
- 모듈: **`win32com.client`(pywin32)** — 사내 윈도우 호스트에 보통 설치/화이트리스트됨(deps_check로 확인).
- E7 `outlook_com_sender`(SENDERS에 등록): 승인된 Task를 `Outlook.Application.CreateItem(0)`로 생성→`Send()`. `FPNA_OUTLOOK_DRAFT_ONLY=1`이면 `Save()`(Drafts, 사람 최종 확인). 멱등은 outbox `idempotency_key`.
- E2 `poll_outlook_replies`: MAPI 받은편지함 스캔→미회신 요청 토큰([REQ-..]) 매칭→`inbound_reply` 이벤트를 랜딩존에 기록→다음 `run_cycle`의 `poll_inbox`가 소비. 구조화 회신은 **첨부 JSON 권장**(본문 파서 대신).
- 전환: `process_outbox(con, sender="outlook_com")` 또는 SENDERS 기본을 교체.

## 의존성 매트릭스 (로컬에서 `python deps_check.py`로 즉시 확인)
| 커넥터 | 필요 의존성 | 성격 | 바로 구현? |
|--------|-------------|------|-----------|
| 파일 랜딩존 poll_inbox·file_sender·run_cycle (E1–E4,E10,E12) | 없음(stdlib+sqlite3) | — | **가능** |
| Teams 승인 (E1) | 없음(Power Automate 노코드) | 외부 | **가능**(폴더 계약만 준수) |
| 보고서 빌드 | openpyxl | 벤더링됨 | **가능** |
| 덱 렌더 (E9) | 기존 BIGS/academic-slide | 보유 | **가능**(spec→폴더 핸드오프) |
| Outlook 발송/회신 (E2,E7) | pywin32(win32com) | 사내 보통 설치 | 의존성 확인 후 |
| ERP/결산 ODBC (E6) | pypyodbc(순수, 벤더링) 또는 pyodbc + DSN | 설치/DSN 필요 | DSN·모듈 확인 후 |
| 참조데이터 OpenAPI (E5) | 없음(stdlib urllib) + API 키 | 키/프록시 | 키 확인 후 |

핵심: **코어·파일 랜딩존·Teams·보고서·E5는 추가 의존성 0**(stdlib). COM/ODBC만 호스트 모듈이 필요하고, 미설치 시 커넥터가 명확한 에러를 던지도록 게이트(코어 동작엔 영향 없음).

## 작업 순서 + 병렬화
**Phase 0 — 백본(선행, 이미 구현·검증).** 폴더 3개(inbox/outbox/processed) + `FPNA_DB`/`FPNA_INBOX`/`FPNA_OUTBOX` + Windows Task Scheduler가 `python -m fpna_fixedcost.run_cycle`를 5–15분 주기 실행. `deps_check.py`로 호스트 점검, `setup_check.py`로 회귀 확인. 모든 트랙이 이 파일 계약(이벤트 JSON)·SENDERS·fetcher 인터페이스로만 통신하므로, Phase 0 이후 아래는 **상호 독립 = 완전 병렬**.

| 트랙(병렬) | 작업 | 의존 | 산출 연결점 |
|-----------|------|------|-------------|
| **A. Teams 승인(E1)** | Power Automate 2개 플로우(카드 게시/응답 수집) | 폴더 계약만 | inbox `approval` 이벤트 |
| **B. Outlook COM(E2,E7)** | `outlook_com_sender` 등록 + `poll_outlook_replies` | pywin32 | SENDERS / inbox `inbound_reply` |
| **C. ERP 읽기(E6)** | `odbc_actuals_fetcher` 배선(또는 파일 export) | pypyodbc/DSN | variance/bootstrap |
| **D. 참조데이터(E5)** | `fetch_and_ingest` 키·스케줄 | API 키 | ingest_snapshot |
| **E. 렌더(E9)** | spec→BIGS/academic-slide 감시 잡 | 보유 툴 | build_*_spec 출력 |

- **A/B/C/D/E는 서로 막지 않음**(공유 전제는 Phase 0뿐). 담당이 다르면 동시 진행 가능(예: A=Power Automate 담당, B/C=파이썬 담당, E=덱 담당).
- 순서 의존은 둘뿐: E10 스케줄러(=run_cycle, 이미 구현)가 A–D의 *소비자*라 먼저 떠 있어야 하고, E11 시크릿이 C/D 착수 전 필요. E12(DB 경로)는 전 트랙 공통 선행이라 Phase 0에 포함.
- 권장 1차 스코프: **Phase 0 + A(Teams 승인)**만으로 사람-인-더-루프 승인 루프가 끝까지 돈다(나머지는 입력 소스 확장).

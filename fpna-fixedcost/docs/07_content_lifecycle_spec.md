# 통합 콘텐츠 라이프사이클 — capture → classify → process → produce → organize → retain

> 노트(Obsidian)·메일/Teams·계약을 한 입력 흐름으로 받아, 카드 파이프라인으로 처리하고, 타입별 산출물(Excel/PPT/PDF/메모)로 생산해, 버전·보존이 통제된 저장 체계에 정리하는 단일 라이프사이클.
> 기존 시스템에 접합: 자산 레이어 L0~L3 + 빌드 매니페스트(asset v1) · 데이터 계약/DQ(v2) · 카드 파이프라인(SSOT §4) · 생산 스킬(pptx/xlsx/pdf/academic-slide).
> 누락 보완: **PPT 보고 덱 · PDF 정식 보고서 · 보고 톤/양식 통일(house_style) · 회의록 구조화**.

===== LIFECYCLE START =====

## 0. 한 장 요약

```
[CAPTURE]                 [CLASSIFY/ROUTE]        [PROCESS]            [PRODUCE]                 [ORGANIZE]            [DISTRIBUTE]   [RETAIN]
Obsidian 노트(VaultVoice) → note_router ──┐                                                                                          
메일/Teams(오케스트레이터) → 큐(work_item) ─┼─→ 카드 파이프라인 → L2 ledger → 산출물 빌더(스킬+house_style) → 출력 택소노미 → 승인 발송 → 보존/아카이브
계약(SharePoint)          → contract_ingest┘     (Decision/Task)    (+grounded narrative)   (Excel/PPT/PDF/메모)   (SharePoint+manifest) (Task/outbox)  (deprecate-not-delete)
```

세 입력 → 한 파이프라인 → 타입 산출물 → 통제된 저장. Obsidian=사고/노트(개인), SharePoint=공식 산출물·ledger 원천(시스템 진실) — 분리.

## 1. CAPTURE (입력 3채널)
- **Obsidian 노트**: VaultVoice(음성/텍스트/이미지) → Google Drive 동기 → 볼트 `00_Inbox/`. 빠른 포착, 개인.
- **메일/Teams**: 오케스트레이터(구현 완료) — 외부·동료. 상관키 회신/알림.
- **계약/SharePoint**: 정식 문서 → contract_ingest(구현 완료).

## 2. Obsidian 노트 분류 (단일 인박스 → 3갈래 라우팅)

### 2A. frontmatter 스키마 (포착 시 부여; VaultVoice가 일부 자동)
```yaml
---
type: action | data | meeting | reference | personal   # 분류 키
topic: [고정비-부동산]            # 도메인 태그(Areas와 정합)
fcst_line: HQ_lease_pangyo        # 파이프라인행이면 대상 라인
action: "임대인 신규 임대료 회신 예정 → 자료요청"   # 행동 의도(있으면)
sensitivity: S0 | S1              # S1=기밀(계약·금액)
source: voice | text | image
captured_at: 2026-06-14T09:00
status: inbox                     # inbox → routed → filed
pipeline: false                   # true면 work_item 후보(사람 확인)
---
```

### 2B. 볼트 구조 (PARA + 도메인)
```
00_Inbox/          포착(미분류)
10_Projects/       기한 있는 산출물(예: 2026-Q2_BoardPack, 본사임차_재협상)
20_Areas/          지속 영역: 고정비-차량 / 고정비-부동산 / 고정비-유틸리티 / 고정비-설비
30_Resources/      레퍼런스·방법론(IFRS16·RICS 메모 등; DA 지식 연결)
40_Archive/        종료
50_Meetings/       회의록(YYYY-MM-DD_주제) — 구조화 추출 대상
90_Daily/          데일리 노트
```

### 2C. 라우팅 규칙 (note_router → 3갈래)
| type | 행선지 | 처리 |
|------|--------|------|
| action / data (+ fcst_line) | **파이프라인** | 사람 확인 → work_item(source=note, trust=correlated) |
| meeting | 50_Meetings + 구조화 추출 | claim 추출 → assumption-card 델타(§1B) |
| reference | 30_Resources + **DA 지식**(300+ YAML/BGE-m3) | 인덱싱(검색용) |
| personal | 볼트 보관 | 파이프라인 미투입 |

규율: 파이프라인행은 **항상 사람 확인**(음성 메모가 자동 행동 유발 금지). S1 노트는 볼트 내 권한·동기 제외 검토.

### 2D. note_router (기존 cards.enqueue_work_item 재사용)
```python
def route_note(con, note_frontmatter, body, now):
    fm = note_frontmatter
    if fm["type"] in ("action", "data") and fm.get("pipeline") and fm.get("fcst_line"):
        # 반환 스키마(데이터 계약) 검증 후 work_item — 노트는 사용자 작성이라 trust=correlated
        payload = {"kind": "note", "fcst_line": fm["fcst_line"], "action": fm.get("action"), "body": body}
        return cards.enqueue_work_item(con, "note", f"obsidian://{fm['captured_at']}",
                                       dedup_key=f"note:{fm['captured_at']}",
                                       correlation_token=None, payload=payload, now=now)
    if fm["type"] == "meeting":
        return {"route": "meeting_extract", "target": "50_Meetings"}
    if fm["type"] == "reference":
        return {"route": "DA_index", "target": "30_Resources"}
    return {"route": "vault_only"}
# 파이프라인행은 검토 큐 경유 후 drain()이 워커 디스패치.
```

## 3. PROCESS (카드 파이프라인 — 구현 완료)
work_item → router(결정론+폴백) → worker → Decision/Decision-Analysis + Task. 게이트(그라운딩·무출처금지·중요성·high-tier)·승인(SoD)·outbox(exactly-once)·ICFR 증적·신뢰감쇠. (SSOT §4, fpna_fixedcost)

## 4. PRODUCE — 타입별 산출물 (누락 보완 포함)

| 산출물 | 트리거 | 생산 스킬/엔진 | 입력 | 비고 |
|--------|--------|----------------|------|------|
| **Excel** (fcst·variance·백업) | 마감/온디맨드 | openpyxl report(구현) | L2 ledger·variance | 5시트·recon tie-out=0 |
| **PPT 보고 덱** ⚠신규 | CEO 보고 주기 | **pptx / academic-slide-coauthoring 스킬**(BIGS deck_system) | variance bridge·**grounded narrative**·evidence health | action title + 핵심 차트 + 출처 각주 |
| **PDF 정식 보고서** ⚠신규 | 서명·아카이브용 | **pdf 스킬** | 확정 보고·계약 요약 | 불변 발행본 |
| **메모/메일** | 자료요청·독촉·공유 | Task 카드 → outbox(구현) | 결정·요청 | 승인 발송 |
| 회의록(구조화) ⚠신규 | 회의 후 | 추출(§1B) | 50_Meetings 노트 | 결정사항/액션/예산영향 3갈래 |

### 4A. house_style — 보고 톤/양식 통일 ⚠신규 (첫 대화 요청)
- **action title 규약**: 슬라이드·섹션 제목이 결론 문장("고정비 3%↑, 본사 임차 갱신·신규 차량 가동 주도").
- **표준 템플릿**: 메시지 타이틀 + 핵심 exhibit(차트/표) + 출처 각주(매니페스트 링크). Excel·PPT·PDF 공통.
- **톤 코퍼스**: 전임/현직 최근 3~6개월 CEO 보고를 코퍼스화 → 톤 참조(스타일만 차용, 수치는 ledger).
- **그라운딩 필수**: 모든 서술은 variance/카드로 cite-back 검증(§7.14) — 환각 코멘터리 차단.
- house_style은 버전드 정의(시맨틱 레이어, §5) — 변경 시 SemVer + 승인.

### 4B. 생산 규율
- 모든 산출물은 L2(ledger)에서 빌드 + **빌드 매니페스트**(입력 source_version·ledger_txn_time·model_version) 동반 → 재현·감사.
- 내러티브는 grounded만 포함. 발송은 Task→승인→outbox.

## 5. ORGANIZE — 산출물 폴더 정리 (핵심 요청)

### 5A. 출력 택소노미 (SharePoint = 시스템 진실)
```
/fpna-fixedcost/reports/
  <YYYY>/<YYYY-MM>/                         # 기간(회계)
    _drafts/                                # 초안(미승인) — 승인 시 승격
    CEO/      boardpack__<title>__<run_id>.pptx + .manifest.json
    controller/ variance__<scope>__<run_id>.xlsx + .manifest.json
    internal/ fcst__<line>__<run_id>.xlsx
    archive_pdf/ <signed>__<run_id>.pdf
```
- **대상(audience)**: CEO / controller / internal — 톤·상세도 분기.
- **유형(type)**: boardpack / variance / fcst / memo.

### 5B. 명명 규약 (정렬·추적 가능)
`<period>_<scope>_<type>_v<n>__<run_id>.<ext>`
예: `2026-06_HQlease_variance_v2__r0617.xlsx`. run_id=빌드 매니페스트 키.

### 5C. 버전·발행
- **발행본 불변**(board pack은 재현 가능해야): 수정=새 run_id, 이전본 보존(자산 v1 L3 규약).
- **초안 → 승인 → 발행**: `_drafts/`에서 작업, 승인 게이트(§6.8) 통과 시 audience 폴더로 승격.
- 매니페스트로 "이 board pack은 어느 ledger 시점·어느 REB/ECOS 버전" 추적.

### 5D. 경계 (혼동 금지)
- **Obsidian 볼트** = 사고·노트·초안 작업(개인 지식, 비공식).
- **SharePoint reports/** = 공식 산출물(시스템 진실, 감사 대상).
- **SharePoint raw/** = ledger 원천(계약·메일 첨부, L0).
- 작업은 로컬 `/work/<run_id>/`, 발행만 SharePoint. 볼트에 공식 산출물 두지 않음.

## 6. RETAIN / ARCHIVE
- 보존 정책(데이터 계약 SLA): board pack·서명 보고 = 장기(SOX/기록물), 초안 = 단기. legal hold 시 파기 차단.
- **하드삭제 없음**: 노트는 40_Archive, 보고서는 콜드 스토리지로 이관하되 **매니페스트 보존**(재현). 결정·계약은 deprecate/retract(이력).
- S1(기밀) 산출물 권한·보존 메타 필수.

## 7. 누락 산출물 체크리스트 (말씀하신 것 → 포함 여부)
| 산출물 | 출처(대화) | 라이프사이클 위치 |
|--------|-----------|-------------------|
| Excel 보고서 | 1턴 | §4 (구현) |
| **PPT 보고 덱** | 1턴(CEO 보고) | §4 ⚠신규 — pptx/academic-slide |
| **PDF 정식 보고** | 1턴(엑셀·pdf) | §4 ⚠신규 — pdf 스킬 |
| **보고 톤/양식 통일** | 1턴 | §4A house_style ⚠신규 |
| 회의록 | 1턴(미팅 多) | §4 + 50_Meetings ⚠신규 |
| 메일/Teams 발신 | 1턴 | §3/§4 (구현, 오케스트레이터) |
| 노트 분류→파이프라인 | 본 요청 | §2 ⚠신규 |
| 예산 반영 추적 | 1턴 | 카드/ledger(구현) |

## 8. 통합 지점 · 사람 결정
- 접합: note_router→cards.enqueue_work_item · 산출물 빌더→pptx/xlsx/pdf 스킬 + report.build_report · 매니페스트→자산 v1 · 톤/house_style→시맨틱 레이어(v2) · grounded narrative→§7.14.
- **사람 결정**: ① 볼트 폴더 체계 확정(PARA vs 도메인) ② 노트 type 자동 태깅 범위(VaultVoice) ③ house_style 톤 코퍼스(전임 보고 확보·승인) ④ 출력 택소노미·명명·보존 기간(controller/IT) ⑤ CEO/controller/internal 대상별 양식 ⑥ S1 노트 동기·권한 정책.

===== LIFECYCLE END =====

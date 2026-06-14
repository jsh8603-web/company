# VERIFY_PLAN — 애매 항목: 방향 확정 · 근거 · 검증 · 구현 계획

반복 논의를 끝내기 위해, 코어 밖이거나 표준에 맡긴 항목마다 **방향을 확정**하고 *근거*(우수 repo/논문), *검증 방법*, *구현 단계*를 못박는다. 코어 기능은 전부 구현·검증됨(STATUS.md, 23 테스트). 아래는 운영 경계의 확정 계획이다.

## 1. 보고 산출물 렌더 (PPT/PDF)
- **방향(확정)**: 이 시스템은 **콘텐츠 스펙**(결론 제목·exhibit·근거 각주·그라운딩)만 생성하고, 렌더는 보유 중인 **BIGS deck_system(~70 레이아웃, McKinsey식)·academic-slide 스킬**이 수행한다. PPT 엔진을 코어에 넣지 않는다(pptxgenjs/python-pptx는 stdlib+openpyxl 제약 밖, 또한 렌더러를 이미 보유). 코어가 안 하는 게 맞다 — 결합만 한다.
- **근거**: 액션 타이틀·exhibit 중심 보고는 Minto(Pyramid Principle)·McKinsey 표준; 콘텐츠/렌더 분리는 관심사 분리(파이프라인-뷰) 원칙.
- **검증**: ① 스펙 스키마 검증(슬라이드마다 action_title·source·grounded 필수) ② `build_board_deck_spec`의 grounded=True 게이트(verify_claim) ③ 렌더 스모크: 스펙→deck_system 1회 생성 후 pptx 스킬의 서브에이전트 비주얼 QA(오버플로·겹침·근거 각주 충돌) ④ 모든 수치 각주가 L2 ledger 출처와 일치.
- **구현**: (a) `build_board_deck_spec` 출력 → deck_system 레이아웃명 매핑 어댑터(stat_bridge→워터폴 레이아웃, evidence_status→표 레이아웃) (b) HOUSE_STYLE를 deck_system 테마 토큰에 바인딩 (c) PDF는 동일 스펙을 문서 템플릿에 (d) 산출물은 `register_artifact`(초안)→`publish_artifact`(불변) 경유.

## 2. 외부 통지 (Outlook 메일 / Teams) — GL 기록 없음
- **방향(확정)**: `SENDERS` 레지스트리에 운영 sender 등록(`outlook_com`), `process_outbox(sender=...)`로 교체. 기본 `log_sender`는 sent_log에 실제 기록(멱등)하며 운영 sender도 동일 시그니처. sender는 통지 채널만(메일/Teams).
- **근거**: transactional outbox 패턴(microservices.io) — 상태변경과 발송을 분리, 멱등키로 정확히 1회. **시스템은 GL에 쓰지 않는다(단방향)**: 회계처리 필요 사안은 회계팀에 통지/이관할 뿐 원장 기록 경로가 없다.
- **검증**: ① exactly-once: 2회 호출 시 sent_log 1행(UNIQUE idem) ② 재시작 복구(pending만 재실행) ③ 발송 후 sent_log↔outbox 정합 대사 ④ SoD: requester≠approver 강제(테스트 존재) ⑤ 드라이런 환경 우선.
- **구현**: (a) `SENDERS["outlook_com"]`=win32com(Outlook COM) 발송, 첨부=published artifact 경로 (b) 손상 등은 `escalate_impairment_to_accounting` 통지(회계팀 이관) (c) 실패 시 outbox status='error'+재시도 (d) 운영 전 드라이런 sender로 sent_log만 적재해 검수.

## 3. 외부 데이터 수집 (OpenAPI 키/프록시)
- **방향(확정)**: `api_fetcher`(env 키·승인 프록시)로 REB/ECOS/KOSIS 풀 → 날짜 스냅샷 → SharePoint 착지 → `file_fetcher`가 읽어 `ingest_snapshot`(SCD2). 폐쇄망은 file_fetcher가 기본, 인터넷 구간만 api_fetcher.
- **근거**: 한국부동산원 상업용부동산 임대동향조사(data.go.kr)·한국은행 ECOS(ecos.bok.or.kr/api)·통계청 KOSIS — 공식 출처. bitemporal SCD2 = 감사 가능한 참조 데이터 표준.
- **검증**: ① 스냅샷 sha256 멱등(중복 미적재) ② 스키마 검증(필수 컬럼·타입) ③ 신선도 SLA: `ref_freshness`가 임계 초과 시 stale 게이트 ④ 적재 후 `get_ibr`/`regional_params` 조회가 최신 valid_to IS NULL 행 반환.
- **구현**: (a) 키는 비밀관리(env/Key Vault), 코드 미보관 (b) 승인 프록시 경유 호출, 실패 시 직전 스냅샷 유지 (c) 스케줄러가 주기 풀→착지 (d) 라이선스(KOGL) 메타 기록.

## 4. 클레임 검증 강화 (NLI/LLM 판정)
- **방향(확정)**: 현재 `verify_claim`=수치 정확매칭(재무 강함)+어휘 정렬(재현 프록시). 운영은 동일 인터페이스 뒤에 **NLI entailment 또는 LLM-판정**을 꽂는다(비수치 주장 정밀화). 인터페이스 불변.
- **근거**: Chain-of-Verification(arXiv 2309.11495)·RARR(arXiv 2210.08726, "Researching and Revising")·인용 기반 평가(ALCE). 수치 도메인은 정확매칭이 entailment보다 강함 — 그래서 1차는 수치, 2차로 어휘/NLI.
- **검증**: 라벨 세트(정상/환각 클레임)로 precision/recall·FPR 측정, eval 게이트에 회귀로 연결. 환각(근거 없는 주장)은 차단되어야 함(현재 데모/테스트로 0% 통과 확인).
- **구현**: (a) `verify_claim(evidence, claim)` 시그니처 유지 (b) NLI 모델/LLM 판정 어댑터 추가(사내 Claude) (c) 라벨 세트 구축→임계 보정 (d) eval_grounding 스위트에 편입.

## 5. 거래처 ER — 조건부 독립 & 스케일 TF
- **방향(확정)**: Fellegi-Sunter 채택(Splink 표준). m=EM 학습, u=직접추정, **값별 TF 보정**(희소 사업자번호 강증거)을 스케일에서 적용하되 **고유 식별자는 기저 미만 약화 방지(min 경계)**. 경계 점수는 검토 큐.
- **근거**: Splink term-frequency 가이드; **Xu, Li & Grannis (2021), J Appl Stat 49(11):2789** — 학습데이터 없이 값 빈도로 가중치 보정(희소값=강증거). 조건부 독립은 FS의 명시 가정(Splink fellegi_sunter 문서). 사업자번호가 지배 식별자라 이름·주소 상관의 영향이 작음.
- **검증**: 라벨 매치 세트로 pairwise precision/recall, 검토 밴드 폭 보정. u_value는 **표본이 아니라 전체 데이터**에서 산정(소표본 과대평가 방지) — 현재 n≥30 게이트 + min 경계로 강한 식별자 약화 방지(테스트로 스케일 군집 정확 병합 확인).
- **구현**: (a) u_value를 전체 거래처 마스터에서 집계 (b) blocking으로 후보쌍 축소(확장성) (c) 주기적 EM 재적합 (d) 검토 큐 UI는 사람 판정→피드백 적재(능동학습).

## 설계 불변식 (재확인 — 바꾸지 않음)
단일 코어+facade(폐쇄망 벤더링), 단방향 GL 미기록, FS 조건부 독립(표준), 수치 cite-back 우선. STATUS.md 참조.

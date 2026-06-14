# 08. 외부 검토 — 유사 구현·논문 대조 (방향 점검 + 개선)

별점 높은 repo·표준·논문과 우리 설계를 대조했다. **결론: 큰 방향 오류 없음 — 분야가 베스트프랙티스로 합의한 패턴과 독립적으로 일치.** 세 곳에서 정밀화했다.

## 1. 검증된 설계 (분야 합의와 일치 → 변경 없음)
| 우리 설계 | 대조 대상 | 판정 |
|-----------|-----------|------|
| 3카드 HITL(Decision 게이트·Task 항상 승인) | FP&A-agent 분야(Board/Workday/Cube/ChatFin): "HITL이 신뢰의 토대; AI는 분석, 사람이 결정·거버넌스" | 일치. 금융은 human-in-the-loop이 정답(human-on-the-loop 아님) |
| grounding·cite-back Verifier(환각 차단) | Chain-of-Verification(arXiv 2309.11495); claim-centric attribution faithfulness(ACL findings) | 일치. 우리 *수치 cite-back*은 entailment보다 강함(숫자는 ledger와 일치/불일치 이분) |
| 거래처 ER = Fellegi-Sunter(log2(m/u)·가산·임계 2개·검토밴드) | Splink(moj-analytical-services), FS 1969 | 정확히 동일 모델 |
| transactional outbox(idempotency_key·exactly-once) | microservices.io 표준 | 텍스트북 일치 |
| eval 배포 게이트(골든·결정론 assertion·임계·회귀 차단) | promptfoo/DeepEval "CI metric gate" | 일치. "결정론 assertion이 저비용으로 회귀 다수 포착" |
| 중요성 게이트·변화만 검토·variance 드라이버 귀속 | Workday/Cube 자동 variance | 일치 |
| 계산 vs 판단 분리(엔진 계산·CGU/IBR 사람) | 분야: "AI는 전략·트레이드오프·정치맥락 못함, 사람이 스토리·결정" | 일치 |
| append-only·bitemporal·PROV·매니페스트 | event-sourcing(Fowler)·블랙박스 해소 | 일치 |

분야 경고(Gartner: 2027까지 agentic AI 40% 실패 — 비용 폭주·불명확 가치·약한 리스크 통제). 우리는 SoD·ICFR·관측·grounding으로 "Trust is Architecture"를 이미 반영.

## 2. 개선 1 — ER: u를 데이터에서 추정 (Splink식 direct estimation)
- **발견**: 우리 ER은 정확히 FS지만 m·u 가중치를 *하드코딩*. Splink는 **u를 데이터에서 직접추정**(비매칭 우세 가정, 값 빈도)하고 m은 EM. 하드코딩은 cold-start엔 robust하나 스케일에선 부정확.
- **반영**(§28A): `calibrate_u_from_data`(값 빈도→u), `fs_match_weight`(log2(m/u)), `fs_prior_weight`(λ 사전). 데모: 사업자번호 대부분 고유한 vendor 43건에서 u≈0.027 → 일치 5.2 bits(하드코딩 13 bits의 과신 교정), λ=0.01 사전 −6.6 bits.
- **운영**: cold-start=프라이어, 스케일(n≥30)=u 직접추정 + **m EM 학습 자동 적용**(train_er_em). 컬럼 조건부 독립은 FS 표준 모델의 전제(설계 불변식, STATUS.md).

## 3. 개선 2 — eval: 정적 임계 + baseline 회귀 + 비용 회귀
- **발견**: 분야는 "직전 run 대비 회귀 비교"와 "비용 회귀(토큰 30%↑도 CI에서 차단)"를 강조(promptfoo/DeepEval, Gartner 비용 통제). 우리는 정적 임계만.
- **반영**(§28B): `eval_regression_vs_baseline`(직전 동일 suite 대비 악화 감지 — 점진 퇴행 포착), `eval_cost_regression`(ops_run 누적 비용 vs 예산), `eval_deploy_gate`에 비용 차원 추가. 데모: router 0.80 vs base 1.0→regressed, 비용 $0.04 vs $0.01→regressed.
- 비고: 서술 품질은 LLM-as-judge(llm-rubric) + 플래그 5~10% 사람 샘플 권장(우리는 결정론 우선 — 수치 도메인엔 충분).

## 4. 개선 3 — 예측 정확도/편향 추적 (분야가 지목하는 핵심 열화)
- **발견**: FP&A-agent 분야가 명시적으로 경고하는 열화 신호 = **"시간 경과에 따른 예측 정확도 저하"**·exception rate 상승. 우리는 신뢰 감쇠·SLO는 있으나 *과거 예측 vs 실현 백테스트*가 없었음.
- **반영**(§28C): `forecast_actual` 테이블 + `record_forecast_actual` + `forecast_accuracy`(MAPE·bias, 임계 초과 시 degraded). 데모: HQ 임차 과소예측 누적 → bias 음수로 포착. → SLO/eval에 연결해 추세 감시(real-time 알림 + trend 분석 2층 중 trend 층).

## 5. 해소 상태 (STATUS.md — 전부 구현)
검토에서 나온 정밀화·확장은 모두 구현됐다(STATUS.md). 관련분:
- ER: u 직접추정 + **m을 EM 학습**(Splink) + λ 사전, n≥30에서 자동 적용. 컬럼 조건부 독립은 FS 표준 모델의 전제이며 사업자번호 지배라 영향 작음(설계 불변식).
- 서술 검증: **수치+어휘 하이브리드**(CoVe식). 수치는 ledger 일치, 비수치는 어휘 정렬.
- ABC 일반 배부·외부 어댑터·발송 sink·IBR/운영 기본값·보고 덱/문서 콘텐츠 스펙: 전부 구현.
- 출처 표준: 회계(IFRS/IAS)·평가(RICS/IVS)·통제(COSO/PCAOB)·ER(Splink/FS)·eval(promptfoo/DeepEval)·verify(CoVe). 비-GitHub 표준 + 대표 OSS.

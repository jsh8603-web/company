"""SECTION 20-25 — ER(Fellegi-Sunter)/계약개정/민감도/eval회귀/내러티브(그라운딩)/관측·SLO."""
from ._core import (normalize_name, resolve_entities, resolve_counterparty,
                    detect_contract_change, process_rebuild_requests, lease_sensitivity, buy_vs_lease_sensitivity,
                    eval_router, eval_gate_calibration, eval_grounding, eval_deploy_gate,
                    narrate_variance, verify_narrative_claim, compute_slos)
# SECTION 28 — 외부 검토 반영 개선
from ._core import (calibrate_u_from_data, fs_match_weight, fs_prior_weight,
                    eval_regression_vs_baseline, eval_cost_regression,
                    record_forecast_actual, forecast_accuracy)
# SECTION 29 — ER EM학습 · 하이브리드 클레임 검증 · ABC 배부
from ._core import train_er_em, verify_claim, allocate_cost_abc

"""SECTION 1 — 공통 토대 (dataclass·NPV/DCF·가중통계·게이트·중요성)."""
from ._core import (Authority, Provenance, Input, AnalysisResult, npv, pv_future,
                    terminal_value_pv, weighted_mean_se, grounded_check,
                    cap_confidence_by_provenance, materiality_band, gate_decision)

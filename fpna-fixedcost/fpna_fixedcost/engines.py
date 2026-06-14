"""SECTION 2-4 — 계약 결정 엔진: 임차 비교(RICS)·buy-vs-lease(IFRS16)·손상(IAS36)."""
from ._core import (Subject, Comp, CompAdjustParams, estimate_market_rent,
                    OwnPlan, LeasePlan, analyze_buy_vs_lease, lease_liability, net_advantage_to_lease,
                    CGU, CGUAsset, test_impairment, value_in_use, fvlcd, allocate_loss)

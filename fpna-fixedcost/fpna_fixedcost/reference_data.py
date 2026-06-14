"""SECTION 16 — Reference Data(외부지표→reference_data SCD2) + 엔진 리팩터 조회."""
from ._core import (ingest_snapshot, seed_reb_snapshot, seed_ecos_ibr,
                    regional_params, get_ibr, ref_freshness)
# SECTION 29 — 외부 어댑터 + 완전 IBR 기본값
from ._core import file_fetcher, api_fetcher, fetch_and_ingest, seed_full_ibr_matrix

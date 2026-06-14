"""fpna_fixedcost — 계약 중심 고정비 의사결정 시스템.

구현은 검증된 단일 코어(_core.py)에 있고, 아래 도메인 모듈이 임포트 표면을 제공한다
(폐쇄망 vendored 드롭인 단순성을 위해 코어는 단일 파일 유지; 필요 시 물리 분리 가능).
"""
from . import common, engines, projection, reference_data, cards, sox, analytics, report, lifecycle, config, connectors  # noqa

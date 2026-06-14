"""SECTION 26-27 — 콘텐츠 라이프사이클: 노트 분류·라우팅 / 산출물 폴더링·매니페스트.

노트(단일 인박스)→3갈래(파이프라인/DA지식/볼트), 산출물 출력 택소노미·버전·발행(불변).
"""
from ._core import (classify_note, route_note, DOMAIN_KEYWORDS,
                    output_path, build_manifest, register_artifact, publish_artifact)

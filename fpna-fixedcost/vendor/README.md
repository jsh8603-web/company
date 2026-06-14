# vendor/ — 런타임 의존성 벤더링 (폐쇄망)

회사 정책: GitHub pull·py 실행 가능, 그 외 설치/네트워크 폐쇄. 런타임 의존성은
**openpyxl + et_xmlfile 하나**(순수 파이썬, C확장 없음, MIT)뿐이며 소스로 동봉한다.

## 벤더링 절차 (인터넷 구간에서 1회)
```
pip download openpyxl et_xmlfile -d ./_wheels --no-binary :all:
# 또는 소스 트리 복사:
#   site-packages/openpyxl  → vendor/openpyxl
#   site-packages/et_xmlfile → vendor/et_xmlfile
```
그런 뒤 vendor/를 repo에 커밋(또는 승인 경로로 이관). 실행 시:
```
PYTHONPATH=vendor python main.py
```
또는 sitecustomize로 vendor/를 sys.path에 추가. pandas/numpy/pydantic/dbt/GE/jsonschema는
사용하지 않는다(표 변환·검증·재무계산은 stdlib + dataclass로 직접 구현).

## 외부 데이터(REB/ECOS/RTMS/KOSIS)
폐쇄망에서 직접 호출 금지. 인터넷/승인 프록시 구간 어댑터가 날짜 스냅샷을 SharePoint에
착지 → 파이프라인이 reference_data(SCD2)로 적재(docs/06_data_acquisition_spec.md).

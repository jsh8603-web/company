# 데이터 수집·소싱 레이어 — 누락 보완 (SSOT 데이터 획득 스펙)

> 문제: 엔진(임차 비교·buy-vs-lease·손상)이 입력을 데모 리터럴(market_trend_pm·IBR·등급조정·잔존·현금흐름)로 받았다. *실제 어디서 어떻게 수집·유지하는지*와 *폐쇄망에서 어떻게 들여오는지*가 누락됐다. 이 문서가 그 획득 레이어를 채운다.
> 원칙: 외부 출처 직접 호출 금지(폐쇄망). 수집은 분리 구간에서 → 승인 경로(SharePoint) 착지 → 파이프라인이 reference_data(SCD2)로 적재. 엔진은 리터럴 대신 reference_data 조회.

===== SPEC START =====

## 1. 데이터 요소 인벤토리 (consumer → element → source → method → cadence → owner)

### 1A. 임차 비교 엔진 (RE comparable) — "지역 지표" 핵심
| element | source(실제) | 수집 방법 | 주기 | owner |
|---------|-------------|-----------|------|-------|
| 지역별 임대료·임대가격지수·공실률·전환률 | **한국부동산원 상업용부동산 임대동향조사**(국가통계 408001호) — data.go.kr OpenAPI/파일, R-ONE(reb.or.kr/r-one) | OpenAPI 풀 또는 파일 다운로드 → CSV 스냅샷 | 분기(익월 말목) | fixedcost-fpna |
| 실거래 비교(임대/매매) | **국토교통부 실거래가 공개시스템(RTMS)** rtms.molit.go.kr — data.go.kr OpenAPI | OpenAPI 풀 → 거래 레코드 | 월 | fixedcost-fpna |
| 임대료 시계열 추세(=market_trend_pm) | REB 임대가격지수에서 *유도* | 지수 전기대비 변화율 계산 | 분기 | fixedcost-fpna |
| 물가연동(인덱싱) | **통계청 KOSIS CPI**(소비자물가) — kosis.kr OpenAPI | OpenAPI 풀 | 월 | controller |
| 자사 임차 포트폴리오(비교 기준) | **내부 계약 마스터**(L0/SharePoint) | 추출 적재(§5B) | 상시 | fixedcost-fpna |

> 주의: REB(지표)와 RTMS(실거래)는 집계·공개 기준이 상이 → 같은 셀에 혼합 금지. 비교법 증거 위계에서 RTMS 실거래 > REB 지수 > 호가.

### 1B. Buy-vs-Lease 엔진 (트럭)
| element | source | 수집 방법 | 주기 | owner |
|---------|--------|-----------|------|-------|
| IBR(증분차입이자율) | **내부 실제 차입금리** + **ECOS 회사채(AA-,3년)·국고채** 벤치마크 | 내부 treasury 입력 + ECOS OpenAPI | 분기/변경시 | treasury |
| 허들레이트/WACC | **내부 재무/treasury**(자본비용 정책) | treasury 승인 입력 | 연/반기 | treasury |
| 잔존가치(중고 상용차) | **내부 처분이력** + 중고상용차 시세(딜러/경매 지수) | 내부 disposal 집계 + 외부 시세 다운로드 | 반기 | fixedcost-fpna |
| TCO opex(정비·연료·보험) | **fleet 관리시스템·telematics·GL opex** | 내부 시스템 export | 월 | fleet ops |
| 리스 견적 | **리스사**(요청-회신 파이프라인 §4) | inbound_reply 워커 | 건별 | fixedcost-fpna |
| 법인세율(유효/법정) | **세무/회계** | 정책 입력 | 연/세법개정시 | tax |

### 1C. 손상 엔진 (IAS 36)
| element | source | 수집 방법 | 주기 | owner |
|---------|--------|-----------|------|-------|
| VIU 세전 현금흐름 | **사업계획/fcst 모델**(CGU별 운영 투영) | 내부 fcst 연계 | 분기/연 | fixedcost-fpna |
| 세전 할인율 | WACC에서 세전 환산(treasury) | 유도 계산 | 분기 | treasury |
| FVLCD(공정가치−처분비) | **외부 감정평가** + 중고 설비 시장 | 감정평가서 인입(L0) + 시장 비교 | 지표 발생시/연 | controller |
| 손상 지표(트리거) | **WMS 가동률·throughput·telematics**(내부) + 시장·기술 신호 | 운영 KPI export → §7.12 이상탐지 | 월/상시 | fixedcost-fpna |
| 장부금액 | **고정자산대장/ERP** | ERP export | 월 | controller |

### 1D. 횡단 (전 엔진 공통)
| element | source | 수집 방법 | 주기 | owner |
|---------|--------|-----------|------|-------|
| GL 실적(actuals SoT) | **ERP**(§6.5 경계) | ERP 정기 export(파일/API) → 대사 | 월/마감 | controller |
| 고정자산대장 | **ERP 고정자산모듈** | export | 월 | controller |
| 계약 원문 | **SharePoint** | §5B 추출 | 상시 | fixedcost-fpna |
| FX(원/달러 등) | **ECOS** 환율 | OpenAPI 풀 | 일/말일 | treasury |
| 금리 커브 | **ECOS** 시장금리(기준·국고채·회사채AA-) | OpenAPI 풀 | 일/월 | treasury |
| 마스터데이터(CoA·CC·vendor·property) | **ERP/내부** | export + SCD2(§7.4) | 변경시 | controller |

## 2. 폐쇄망 수집 아키텍처 (직접 호출 금지)

```
[인터넷/승인 프록시 구간]                 [승인 경로]              [폐쇄망 파이프라인]
 acquisition adapters  ──dated snapshot──▶  SharePoint     ──ingest──▶  reference_data(SCD2)
  · REB (data.go.kr OpenAPI/file)            /refdata/<set>/             + ref_snapshot(출처·수집일·버전·해시)
  · ECOS (OpenAPI 인증키)                     <YYYYQn|YYYYMM>/            + DQ freshness 검증(§5)
  · RTMS (data.go.kr OpenAPI)                 <sha256>.csv               + 엔진이 조회
  · KOSIS (OpenAPI)
```
- **분리 원칙**: 폐쇄망 파이프라인은 외부를 직접 호출하지 않는다. 어댑터는 인터넷 구간(또는 승인 프록시)에서 실행, **날짜 스냅샷 파일**로 SharePoint에 착지. 파이프라인은 파일만 읽는다(=재현·감사 가능, 외부 변동에 무관).
- **자동화 수준**: ECOS/data.go.kr는 OpenAPI라 어댑터 자동화 가능(인증키). 자동 프록시 불가 시 분기 1회 수동 다운로드도 허용(REB는 분기라 수동도 현실적).
- **라이선스**: ECOS=출처명시 시 상업 무료, REB=국가통계 출처명시, RTMS=공공. 스냅샷 메타에 출처·라이선스 기록.

## 3. reference_data 스키마 + 벤치마크 어댑터 (구현)

```python
# --- 스냅샷 메타(재현·감사) ---
CREATE TABLE ref_snapshot(
  ref_set TEXT, snapshot_date TEXT, source TEXT, source_url TEXT, license TEXT,
  version TEXT, sha256 TEXT, ingested_at TEXT, PRIMARY KEY(ref_set, version));

# --- 지역 임대료 벤치마크(REB; SCD2는 §7.4 reference_data 재사용) ---
CREATE TABLE regional_rent_benchmark(
  region TEXT, property_type TEXT, grade INTEGER, period TEXT,   -- 2026Q1
  rent_per_sqm REAL, rent_index REAL, vacancy REAL,
  source_version TEXT, valid_from TEXT, valid_to TEXT);          -- valid_to NULL=현행

# --- IBR 매트릭스(내부 차입 + ECOS 벤치마크) ---
CREATE TABLE ibr_matrix(
  currency TEXT, term_band TEXT, security TEXT, ibr REAL,         -- KRW/3-5y/secured
  benchmark TEXT, spread REAL, source_version TEXT, valid_from TEXT, valid_to TEXT);
```

**SCD2 적재 어댑터(멱등·이력보존)**:
```python
def ingest_reference_snapshot(con, table, ref_set, rows, keys, source, url, license, version, sha256, now):
    con.execute("INSERT OR IGNORE INTO ref_snapshot VALUES(?,?,?,?,?,?,?,?)",
                (ref_set, now, source, url, license, version, sha256, now))
    for r in rows:                              # SCD2: 동일 키 현행 행 close 후 신규 open
        where = " AND ".join(f"{k}=?" for k in keys)
        con.execute(f"UPDATE {table} SET valid_to=? WHERE {where} AND valid_to IS NULL",
                    (now, *[r[k] for k in keys]))
        cols = ",".join(r) + ",source_version,valid_from,valid_to"
        con.execute(f"INSERT INTO {table}({cols}) VALUES({','.join('?'*(len(r)+3))})",
                    (*r.values(), version, now, None))
    con.commit()
```

**엔진 리팩터(리터럴 → reference_data 조회)**: `re_comparable`의 파라미터를 지표에서 가져온다.
```python
def regional_params(con, region, grade, asof):
    """REB 지표에서 시장 수준·추세를 조회(literal market_trend_pm 대체)."""
    cur = con.execute("""SELECT rent_per_sqm, rent_index, period FROM regional_rent_benchmark
        WHERE region=? AND grade=? AND period<=? AND valid_to IS NULL
        ORDER BY period DESC LIMIT 2""", (region, grade, asof)).fetchall()
    if not cur: return None
    rent = cur[0][0]
    trend_pm = ((cur[0][1]/cur[1][1]) ** (1/3) - 1) if len(cur) == 2 and cur[1][1] else 0.0  # 분기지수→월추세
    return {"market_rent_anchor": rent, "market_trend_pm": trend_pm, "period": cur[0][2]}
# estimate_market_rent(...)에 CompAdjustParams(market_trend_pm=regional_params(...)['market_trend_pm']) 주입.
# 비교 후보(comps)도 RTMS 실거래 + 자사 포트폴리오 + 회신에서 구성(증거 위계 가중).
```
`buy_vs_lease`의 IBR/할인율도 동일하게 `ibr_matrix`·할인율 정책 테이블에서 조회(literal 0.055/0.09 대체).

## 4. 수집 주기 · 신선도(데이터 계약 SLA) · 버전/정정

| ref_set | freshness SLA | 정정 처리 |
|---------|---------------|-----------|
| REB 임대지표 | 분기 + 35일(공표 익월) | 지수 정정 시 새 version → 영향 임차결정 재분석(§7.7)·restatement(§6.4) |
| ECOS 금리/FX | 일 1 / 말일 | 확정치 갱신 시 version |
| RTMS 실거래 | 월 | 지연 신고분 누적 → 재스냅샷 |
| KOSIS CPI | 월 | 잠정→확정 version |
- 각 ref_set은 **데이터 계약(§5-A)** 보유: freshness 임계·소유·DQ규칙. 임계 초과 시 stale 플래그 → 해당 결정 evidence health 강등 + 재수집 알림.
- 매니페스트(§1)에 사용 source_version 기록 → board pack 재현 시 동일 지표 버전으로.

## 5. 내부 데이터 수집 (ERP/WMS/telematics/계약)

- **GL/ERP(§6.5)**: 정기 export(마감 후 파일 또는 승인 API) → L0 적재 → L2 대사(`gl_recon`). 방식·주기·인터페이스를 IT와 확정. 시스템→GL 쓰기 없음(단방향).
- **고정자산대장**: ERP 고정자산모듈 export → 상각 roll-forward(§7.1)·장부금액 입력.
- **WMS 가동률·telematics**: 손상 지표(§1C)·TCO(§1B) 소스. export 주기·지표 정의 확정 → §7.12 이상탐지 입력.
- **계약 추출(§5B)**: SharePoint 계약 PDF → **사내 Claude 구조화 추출**(반환 스키마 강제) → 계약·자산 마스터. 필드: 임대료·면적·등급·인상률·해지·보증금·할인율. 추출 충실성은 Verifier(§6.1).

## 6. 데이터 품질 · 거버넌스

- DQ(§5): 외부 지표는 completeness(지역 누락)·freshness·범위검사; 내부는 grain·tie-out.
- 민감도: 외부 공개지표=S0, 내부 계약·차입금리·처분이력=S1(권한·보존).
- 모든 ref 적재·엔진 조회는 계보(§12)로 추적 — fcst 숫자에서 "어느 분기 REB 지표·어느 ECOS 버전"까지.

## 7. 우선순위 · 구현 순서 · 사람 결정

구현 순서: ① ref_snapshot·reference_data·regional_rent_benchmark·ibr_matrix 스키마 → ② 어댑터(ECOS·data.go.kr OpenAPI 우선; REB 분기 수동 폴백) → ③ 엔진 리팩터(regional_params·ibr 조회) → ④ 데이터 계약·DQ·freshness → ⑤ 내부(ERP/WMS) 인터페이스.

**사람 결정 필수**: ① ECOS·data.go.kr **OpenAPI 인증키 발급** 및 외부 수집 구간/프록시 승인(IT 보안) ② IBR 매트릭스 구성(treasury — 벤치마크·스프레드) ③ 할인율/허들 정책 ④ 감정평가사 FVLCD 계약·주기 ⑤ telematics/WMS 지표 연동 범위 ⑥ GL/ERP export 인터페이스·주기 ⑦ 외부 지표 민감도/라이선스 표기.

## 8. 출처 (비-GitHub, 공공·전문기관)

- 한국부동산원 상업용부동산 임대동향조사 — reb.or.kr/r-one, data.go.kr(분기 지역별 임대료·지수·공실률, OpenAPI/파일). 국가통계 408001호.
- 국토교통부 실거래가(RTMS) — rtms.molit.go.kr, data.go.kr OpenAPI.
- 한국은행 ECOS — ecos.bok.or.kr/api (시장금리·국고채·회사채AA-·환율; 인증키; 출처명시 무료).
- 통계청 KOSIS — kosis.kr (CPI; OpenAPI).
- (재사용) RICS 비교법·IFRS16 IBR·IAS36 — 엔진 방법론(R4 스펙).

===== SPEC END =====

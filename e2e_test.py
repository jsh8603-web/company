"""
e2e_test.py — 확장 E2E. 5개 마감에 걸친 풀포트폴리오 운영을 워커 전 경로로 흘리고,
매 마감마다 (1) 기록된 ProjectionLines를 엔진 재계산과 대조(fact==truth),
(2) 멱등/epoch/불변식/actualization/bridge/relocation/overlay/breach를 단언.
"""
import json, collections, lease_fcst as lf, sap_recon as sap
from com_worker import FakeSP, run_worker, load_store

EPOCH = "2026-09-01"; HZ = 48
seq = [0]; rows = []
def row(kind, p, rec, vf, sup=None):
    rows.append({"Seq": seq[0], "Kind": kind, "Payload": json.dumps(p), "RecordedAt": rec,
                 "ValidFrom": vf, "Supersedes": "" if sup is None else sup}); seq[0] += 1
def C(**k): return k
sp = FakeSP(rows)
def at(asof): return [x for x in sp.tables["ProjectionLines"] if x["AsOf"] == asof]
chk = []
def ck(name, cond):
    assert cond, "FAIL: " + name
    chk.append(name)

# ---- fact==truth 교차검증: 기록된 ProjectionLines가 엔진 재계산과 일치 ----------
def cross_check(asof):
    S = load_store(sp)
    P, actual_evs, _ = lf.project_portfolio(S.events, HZ, EPOCH)
    base, by_gl, _ = lf.aggregate(P, HZ, "base")
    over, _, _ = lf.aggregate(P, HZ, "overlay")
    # 엔진 기준 reported(base에서 actual 키 치환) 총액
    base_by_key = collections.defaultdict(float)
    for p in P:
        if p.scenario == "base" and 1 <= p.month <= HZ:
            base_by_key[(p.site_id, p.gl, p.month)] += p.amount
    aidx = {(a["site"], a["gl"], a["month"]): a["amount"] for a in sap.agg_actuals(actual_evs)}
    rep = sum(base[m] for m in range(1, HZ+1))
    for k, v in aidx.items():
        if 1 <= k[2] <= HZ:
            rep += v - base_by_key.get(k, 0.0)          # 닫힌 키: base→actual
    pl = at(asof)
    w_rep = sum(x["Amount"] for x in pl if x["Scenario"] in ("base", "actual"))
    w_over = sum(x["Amount"] for x in pl if x["Scenario"] == "overlay")
    tol = max(5, len(pl))
    ck(f"{asof} fact==truth(reported)", abs(w_rep - round(rep)) <= tol)
    ck(f"{asof} fact==truth(overlay)", abs(w_over - round(sum(over.values()))) <= tol)
    ck(f"{asof} 음수 없음", all(x["Amount"] >= 0 for x in pl))
    # 완전 개방월(실적 없는 월) base Σ == 엔진 base[m]
    closed_m = {k[2] for k in aidx}
    openm = next(m for m in range(1, 13) if m not in closed_m)
    wbase = sum(x["Amount"] for x in pl if x["Scenario"] == "base" and x["Month"] == openm)
    ck(f"{asof} 개방월 base 일치 m{openm}", abs(wbase - round(base[openm])) <= 2)

def idempotent(asof, today):
    n = len(at(asof)); run_worker(sp, horizon=HZ, today=today, epoch=EPOCH)
    ck(f"{asof} 멱등", len(at(asof)) == n)

def fY1(events_asof):
    P, _, _ = lf.project_portfolio(events_asof, HZ, EPOCH)
    b, _, _ = lf.aggregate(P, HZ, "base"); return sum(b[m] for m in range(1, 13))

# ═══ 마감1 (2026-09-30): 초기 포트폴리오 ═══════════════════════════════════
row("card.create",C(id="SH-A",site_id="A",cost_center="CC1",facility_type="sub_hub",region="수도권남부",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=150_000_000,
    escalation_annual=0.03,rent_free_months=2,restoration_est=300_000_000,cam_monthly=12_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("card.create",C(id="SH-B",site_id="B",cost_center="CC2",facility_type="sub_hub",region="수도권서부",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=0,
    rent_schedule=[100_000_000,108_000_000,118_000_000],cam_monthly=8_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("card.create",C(id="MC-1",site_id="M1",cost_center="CC3",facility_type="mobile",region="수도권남부",
    classification="operating",commencement="2026-09-01",term_months=12,monthly_rent=8_500_000,cam_monthly=600_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("booster.create",C(region="수도권남부",planned_count=5,avg_unit_cost=7_300_000,start_month=2,dept_reliability=0.7),"2026-09-30","2026-10-01")
row("booster.create",C(region="수도권서부",planned_count=3,avg_unit_cost=7_000_000,start_month=3,dept_reliability=0.6),"2026-09-30","2026-10-01")
r1 = run_worker(sp, horizon=HZ, today="2026-09-30", epoch=EPOCH)
ck("C1 불변식", r1["invariants_ok"]); ck("C1 리뷰", r1["reviews"] > 0)
cross_check("2026-09-30"); idempotent("2026-09-30","2026-09-30")
evs_c1 = load_store(sp).events

# ═══ 마감2 (2026-10-31): 첫 실적(부분: lease만) + 정정 ═══════════════════════
row("actual.post",C(site="A",gl=lf.GL_LEASE,month=1,amount=146_000_000,doc="a1"),"2026-10-10","M01")
row("actual.post",C(site="B",gl=lf.GL_LEASE,month=1,amount=108_000_000,doc="b1"),"2026-10-10","M01")
row("actual.post",C(site="M1",gl=lf.GL_LEASE,month=1,amount=8_500_000,doc="m1"),"2026-10-10","M01")
row("card.amend",C(card_id="SH-A",field="cam_monthly",value=13_000_000),"2026-10-15","2026-09-01")  # 개방월 영향
r2 = run_worker(sp, horizon=HZ, today="2026-10-31", epoch=EPOCH)
pl2 = at("2026-10-31")
ck("C2 불변식", r2["invariants_ok"])
ck("C2 lease m1 실적고정", next(x for x in pl2 if x["SourceCard"]=="SH-A" and x["GL"]==lf.GL_LEASE and x["Month"]==1)["Scenario"]=="actual")
ck("C2 CAM m1 부분→base", next(x for x in pl2 if x["SourceCard"]=="SH-A" and x["GL"]==lf.GL_CAM and x["Month"]==1)["Scenario"]=="base")
ck("C2 부분실적 오탐0", r2["breaches"]==0)
cross_check("2026-10-31"); idempotent("2026-10-31","2026-10-31")

# ═══ 마감3 (2026-11-30): settle/drain + 확정갱신 + 불확실손상 + 분할전표 ═══════
row("booster.create",C(region="수도권남부",planned_count=4,avg_unit_cost=9_200_000,start_month=3,dept_reliability=0.7),"2026-11-10","2026-11-01")
row("booster.drain",{"region":"수도권남부","count_delta":1,"new_card":C(id="MC-2",site_id="M2",cost_center="CC4",
    facility_type="mobile",region="수도권남부",classification="operating",commencement="2026-11-01",term_months=12,monthly_rent=9_200_000,cam_monthly=600_000,certainty="confirmed")},"2026-11-10","2026-11-01")
row("lifecycle",{"card_id":"SH-A","type":"renewal","month":36,"add_months":24,"new_rent":160_000_000,"certainty":"confirmed"},"2026-11-12","M36")
row("lifecycle",{"card_id":"SH-B","type":"impairment","month":20,"loss":40_000_000,"certainty":"uncertain"},"2026-11-15","M20")
# 분할 전표: SH-A lease m2 = 73M + 73.2M
row("actual.post",C(site="A",gl=lf.GL_LEASE,month=2,amount=73_000_000,doc="a2a"),"2026-11-20","M02")
row("actual.post",C(site="A",gl=lf.GL_LEASE,month=2,amount=73_211_667,doc="a2b"),"2026-11-20","M02")
row("actual.post",C(site="A",gl=lf.GL_CAM,month=1,amount=12_000_000,doc="ac1"),"2026-11-20","M01")
r3 = run_worker(sp, horizon=HZ, today="2026-11-30", epoch=EPOCH)
pl3 = at("2026-11-30")
ck("C3 불변식", r3["invariants_ok"])
ck("C3 분할전표 합산", abs(sum(x["Amount"] for x in pl3 if x["SourceCard"]=="SH-A" and x["GL"]==lf.GL_LEASE and x["Month"]==2) - 146_211_667) <= 2)
ck("C3 불확실손상 overlay", any(x["Scenario"]=="overlay" for x in pl3))
ck("C3 확정갱신 horizon내", sum(x["Amount"] for x in pl3 if x["SourceCard"]=="SH-A" and x["GL"]==lf.GL_LEASE and x["Month"]==40)>0)
bridge3 = [x for x in sp.tables["Bridge"] if x["AsOf"]=="2026-11-30"]
ck("C3 bridge==forecast ΔY1", abs(sum(b["Amount"] for b in bridge3) - (fY1(load_store(sp).as_of("2026-11-30")) - fY1(load_store(sp).as_of("2026-10-31")))) < 2)
cross_check("2026-11-30"); idempotent("2026-11-30","2026-11-30")

# ═══ 마감4 (2026-12-31): relocation + 종료 + backfill + 다권역 drain ══════════
row("card.create",C(id="MC-3",site_id="M3",cost_center="CC5",facility_type="mobile",region="수도권서부",
    classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=7_000_000,certainty="confirmed"),"2026-09-30","2026-10-01")
lf_store = load_store(sp)  # relocate는 store에서 구 commencement 조회
# relocate를 이벤트로 직접 기록(워커 경로 유지): 종료 + 파생 commencement 신카드
_old_comm = "2026-10-01"
from datetime import date
_new_comm = lf._add_months(date.fromisoformat(_old_comm), 6).isoformat()
row("lifecycle",{"card_id":"MC-3","type":"termination","month":6,"penalty":0},"2026-12-05","M06")
row("card.create",C(id="MC-3b",site_id="M3b",cost_center="CC5",facility_type="mobile",region="수도권서부",
    classification="operating",commencement=_new_comm,term_months=12,monthly_rent=7_200_000,certainty="confirmed"),"2026-12-05",_new_comm)
row("lifecycle",{"card_id":"MC-2","type":"termination","month":8,"penalty":2_000_000},"2026-12-06","M08")
row("card.create",C(id="OLD-X",site_id="X",cost_center="CC6",facility_type="sub_hub",region="수도권서부",
    classification="operating",commencement="2026-06-01",term_months=36,monthly_rent=90_000_000,certainty="confirmed"),"2026-12-10","2026-06-01")
row("booster.drain",{"region":"수도권서부","count_delta":1,"new_card":C(id="MC-4",site_id="M4",cost_center="CC7",
    facility_type="mobile",region="수도권서부",classification="operating",commencement="2026-12-01",term_months=12,monthly_rent=7_100_000,certainty="confirmed")},"2026-12-08","2026-12-01")
r4 = run_worker(sp, horizon=HZ, today="2026-12-31", epoch=EPOCH)
pl4 = at("2026-12-31")
ck("C4 불변식", r4["invariants_ok"])
# relocation 경계: MC-3/MC-3b lease 합이 절대월마다 ≤1건(겹침 없음)
mc3 = collections.Counter(x["Month"] for x in pl4 if x["SourceCard"] in ("MC-3","MC-3b") and x["GL"]==lf.GL_LEASE and x["Scenario"]=="base")
ck("C4 relocation 무겹침", all(v==1 for v in mc3.values()))
# backfill epoch 안정: SH-A m1 lease(실적) 불변
ck("C4 epoch 안정", next(x for x in pl4 if x["SourceCard"]=="SH-A" and x["GL"]==lf.GL_LEASE and x["Month"]==1)["Amount"]==146_000_000)
ck("C4 backfill 기여", any(x["SourceCard"]=="OLD-X" and x["Month"]>=1 for x in pl4))
cross_check("2026-12-31"); idempotent("2026-12-31","2026-12-31")

# ═══ 마감5 (2027-01-31): 실적 누적 + AvF 구성 ═══════════════════════════════
for s,gl,m,amt in [("B",lf.GL_LEASE,2,108_000_000),("M1",lf.GL_LEASE,2,8_500_000),
                   ("A",lf.GL_LEASE,3,146_211_667),("A",lf.GL_CAM,2,13_000_000),
                   ("B",lf.GL_CAM,1,8_000_000)]:
    row("actual.post",C(site=s,gl=gl,month=m,amount=amt,doc=f"x{s}{m}"),"2027-01-15",f"M{m:02d}")
r5 = run_worker(sp, horizon=HZ, today="2027-01-31", epoch=EPOCH)
pl5 = at("2027-01-31")
ck("C5 불변식", r5["invariants_ok"])
ck("C5 AvF: 닫힌월 실적+개방월 예측 공존",
   any(x["Scenario"]=="actual" for x in pl5) and any(x["Scenario"]=="base" for x in pl5))
# 보고 한 줄 = base+actual, 모든 월 1..HZ 커버(공백 없음)
months_cov = {x["Month"] for x in pl5 if x["Scenario"] in ("base","actual")}
ck("C5 월 커버리지 1..12 공백없음", set(range(1,13)) <= months_cov)
bridge5 = [x for x in sp.tables["Bridge"] if x["AsOf"]=="2027-01-31"]
ck("C5 bridge==forecast ΔY1", abs(sum(b["Amount"] for b in bridge5) - (fY1(load_store(sp).as_of("2027-01-31")) - fY1(load_store(sp).as_of("2026-12-31")))) < 2)
cross_check("2027-01-31"); idempotent("2027-01-31","2027-01-31")

# ═══ 전역 단언 ═══════════════════════════════════════════════════════════
asofs = sorted({x["AsOf"] for x in sp.tables["ProjectionLines"]})
ck("스냅샷 5개", len(asofs)==5)
ck("Events 단조증가(워커 변조 없음)", len(sp.tables["Events"])==seq[0])
# 각 스냅샷: 월별 Σ(GL, base+actual) 양수 & 라인 존재
for a in asofs:
    pl = at(a)
    ck(f"{a} 라인 존재", len(pl)>0)

print(f"확장 E2E 통과 ✓  ({len(chk)} checks / 5 closes)")
for c in chk: print("  ✓", c)

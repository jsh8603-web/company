"""
integration_test.py — 실가동 흐름 무결성. FakeSP로 다회차 운영을 모사하고
끊김(이중계상/비멱등/축어긋남/epoch이동)이 없음을 단언한다.
"""
import json, lease_fcst as lf, sap_recon as sap
from com_worker import FakeSP, run_worker

EPOCH = "2026-09-01"; HZ = 48
seq = [0]
def row(rows, kind, payload, rec, vf, sup=None):
    rows.append({"Seq": seq[0], "Kind": kind, "Payload": json.dumps(payload),
                 "RecordedAt": rec, "ValidFrom": vf, "Supersedes": "" if sup is None else sup}); seq[0]+=1

def card(**k): return k
rows = []
# 마감1 (2026-09-30): sub-hub(esc 3%) + mobile + booster
row(rows,"card.create",card(id="SH-용인1",site_id="용인1",cost_center="CC-01",facility_type="sub_hub",
    region="수도권남부",classification="operating",commencement="2026-09-01",term_months=36,
    monthly_rent=150_000_000,escalation_annual=0.03,rent_free_months=2,restoration_est=300_000_000,
    cam_monthly=12_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row(rows,"card.create",card(id="MC-평택1",site_id="M평택1",cost_center="CC-02",facility_type="mobile",
    region="수도권남부",classification="operating",commencement="2026-09-01",term_months=12,
    monthly_rent=8_500_000,cam_monthly=600_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row(rows,"booster.create",card(region="수도권남부",planned_count=5,avg_unit_cost=7_300_000,
    start_month=2,dept_reliability=0.7),"2026-09-30","2026-10-01")

sp = FakeSP(rows)
ev_before = len(sp.tables["Events"])
r1 = run_worker(sp, horizon=HZ, today="2026-09-30", epoch=EPOCH)
pl1 = [x for x in sp.tables["ProjectionLines"] if x["AsOf"]=="2026-09-30"]

# [1] 워커는 Events 정본을 변조하지 않는다(읽기전용)
assert len(sp.tables["Events"]) == ev_before, "Events mutated by worker!"
# [2] 불변식 통과
assert r1["invariants_ok"]
# [3] escalation 이중계상 없음: 운영리스 정액이라 SH Lease cost는 월 동일(flat),
#     그리고 Events에 tickler가 amend를 추가하지 않음(=정본 불변, [1]). 추가로 정액 검증:
sh_lease = sorted({(x["Month"],x["Amount"]) for x in pl1
                   if x["SourceCard"]=="SH-용인1" and x["GL"]=="Lease cost"})
assert sh_lease[0][1] == sh_lease[-1][1], "정액 위반(escalation 이중계상 의심)"

# [4] 멱등: 같은 AsOf 재실행 → ProjectionLines 행수 불변
n_before = len([x for x in sp.tables["ProjectionLines"] if x["AsOf"]=="2026-09-30"])
run_worker(sp, horizon=HZ, today="2026-09-30", epoch=EPOCH)
n_after = len([x for x in sp.tables["ProjectionLines"] if x["AsOf"]=="2026-09-30"])
assert n_before == n_after, f"비멱등! {n_before}->{n_after}"

# 마감2 (2026-11-10): 실현단가 반영(booster 갱신)+drain+불확실 손상 + SAP 실적('YYYY-MM')
row(rows,"booster.create",card(region="수도권남부",planned_count=4,avg_unit_cost=9_200_000,
    start_month=3,dept_reliability=0.7),"2026-11-10","2026-11-01")
row(rows,"booster.drain",{"region":"수도권남부","count_delta":1,"new_card":card(id="MC-평택2",
    site_id="M평택2",cost_center="CC-09",facility_type="mobile",region="수도권남부",
    classification="operating",commencement="2026-11-01",term_months=12,monthly_rent=9_200_000,
    cam_monthly=600_000,certainty="confirmed")},"2026-11-10","2026-11-01")
row(rows,"lifecycle",{"card_id":"SH-용인1","type":"impairment","month":20,"loss":50_000_000,
    "certainty":"uncertain"},"2026-11-10","M20")
# SAP 실적: 회계기간 'YYYY-MM' → abs_month 변환되어 투영월과 정렬되는지
S_tmp = lf.EventStore()
sap.ingest_sap([sap.ActualRecord("CC-01","용인1","5120000","2026-09",14_000_000,"D1","2026-11-05")],
               S_tmp, "2026-11-05", epoch=EPOCH)
am = S_tmp.events[0].payload["month"]
assert am == 1, f"달력월 변환 오류: 2026-09 should map to abs month 1, got {am}"
row(rows,"actual.post",{"site":"용인1","gl":lf.GL_CAM,"month":am,"amount":14_000_000,"doc":"D1"},
    "2026-11-10","M01")

r2 = run_worker(sp, horizon=HZ, today="2026-11-10", epoch=EPOCH)
pl2 = [x for x in sp.tables["ProjectionLines"] if x["AsOf"]=="2026-11-10"]

# [5] epoch 고정: SH Lease cost의 Month=1 금액이 두 마감에서 동일(시간축 안정)
def sh_m1(pl): return next(x["Amount"] for x in pl if x["SourceCard"]=="SH-용인1"
                           and x["GL"]=="Lease cost" and x["Month"]==1)
assert sh_m1(pl1)==sh_m1(pl2), "epoch 이동(Month 축 어긋남)!"

# [6] Bridge(결정 델타) == 엔진 forecast Y1 Δ(마감2-마감1), 잔차 0 (actualization과 분리)
from com_worker import load_store
Sall = load_store(sp)
def fY1(asof):
    P,_,_ = lf.project_portfolio(Sall.as_of(asof), HZ, EPOCH)
    base,_,_ = lf.aggregate(P, HZ, "base")
    return sum(base[m] for m in range(1, 13))
bridge = [x for x in sp.tables["Bridge"] if x["AsOf"]=="2026-11-10"]
assert bridge, "Bridge 미기록"
assert abs(sum(b["Amount"] for b in bridge) - (fY1("2026-11-10")-fY1("2026-09-30"))) < 1, "Bridge!=forecast Y1 Δ"

# [7] 대사: SAP 실적이 투영월과 정렬되어 위반이 정확히 잡힘(용인1 CAM 16.7%)
br = [x for x in sp.tables["Breaches"] if x["AsOf"]=="2026-11-10"]
assert any(x["Site"]=="용인1" and x["GL"]=="CAM/occupancy" for x in br), "달력월 정렬 실패로 대사 누락"

# [8] 과거 계약 backfill 후에도 epoch 고정(SH still Month 1)
row(rows,"card.create",card(id="OLD-인천1",site_id="인천1",cost_center="CC-07",facility_type="sub_hub",
    region="수도권서부",classification="operating",commencement="2026-06-01",term_months=36,
    monthly_rent=90_000_000,certainty="confirmed"),"2026-12-10","2026-06-01")
run_worker(sp, horizon=HZ, today="2026-12-10", epoch=EPOCH)
pl3=[x for x in sp.tables["ProjectionLines"] if x["AsOf"]=="2026-12-10"]
assert sh_m1(pl1)==sh_m1(pl3), "backfill이 epoch를 이동시킴!"
# 과거 계약은 epoch 이전분은 잘리고 윈도우 내(Month>=1)만 기여
assert any(x["SourceCard"]=="OLD-인천1" and x["Month"]>=1 for x in pl3)

print("통합검증 통과 ✓")
print(f"  [1] Events 불변(읽기전용)  [2] 불변식 OK  [3] 정액(이중계상 없음)")
print(f"  [4] 재실행 멱등({n_before}행 유지)  [5] epoch 고정(SH m1 {sh_m1(pl1):,})")
print(f"  [6] Bridge=ΔY1 {sum(b['Amount'] for b in bridge):,}  [7] 달력월 정렬 대사 OK")
print(f"  [8] backfill 후 epoch 안정")

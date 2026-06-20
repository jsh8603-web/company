"""
edge_test.py — 의심 케이스 배터리. 각 케이스 독립 시나리오로 끊김/오류를 단언.
A 마감월 정정(고정)  B 다권역 동시 drain  C 부분 실적(오탐 없음)  D supersede 체인
E 확정 갱신(horizon 내 포착)  F rent-free+escalation 정액  G drain 수 보존
H overlay-only 월(무크래시)  I 음수 count 클램프
"""
import json, lease_fcst as lf, sap_recon as sap
from com_worker import FakeSP, run_worker
EPOCH = "2026-09-01"; HZ = 48
def C(**k): return k
def store(evs):
    S = lf.EventStore()
    for e in evs: S.append(*e)
    return S
ok = []

# ── A. 마감월 정정: 실적 있는 월은 정정해도 보고값(=실적) 불변, 미래월만 이동 ──
rows=[]; seq=[0]
def row(kind,p,rec,vf,sup=None):
    rows.append({"Seq":seq[0],"Kind":kind,"Payload":json.dumps(p),"RecordedAt":rec,
                 "ValidFrom":vf,"Supersedes":"" if sup is None else sup}); seq[0]+=1
row("card.create",C(id="SH1",site_id="s1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,
    cam_monthly=10_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("actual.post",C(site="s1",gl=lf.GL_LEASE,month=1,amount=100_000_000,doc="d"),"2026-10-05","M01")
sp=FakeSP(rows); run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)
pl=lambda a:[x for x in sp.tables["ProjectionLines"] if x["AsOf"]==a]
m1_actual=next(x for x in pl("2026-10-31") if x["SourceCard"]=="SH1" and x["GL"]==lf.GL_LEASE and x["Month"]==1)
assert m1_actual["Scenario"]=="actual" and m1_actual["Amount"]==100_000_000, "마감월 실적 고정 실패"
m5_before=next(x for x in pl("2026-10-31") if x["SourceCard"]=="SH1" and x["GL"]==lf.GL_LEASE and x["Month"]==5)["Amount"]
# 정정: 임차료 상향(미래 재산정) — 닫힌 M1은 불변, 열린 M5는 변동
row("card.amend",C(card_id="SH1",field="monthly_rent",value=120_000_000),"2026-11-02","2026-09-01")
run_worker(sp,horizon=HZ,today="2026-11-30",epoch=EPOCH)
m1_after=next(x for x in pl("2026-11-30") if x["SourceCard"]=="SH1" and x["GL"]==lf.GL_LEASE and x["Month"]==1)
m5_after=next(x for x in pl("2026-11-30") if x["SourceCard"]=="SH1" and x["GL"]==lf.GL_LEASE and x["Month"]==5)["Amount"]
assert m1_after["Scenario"]=="actual" and m1_after["Amount"]==100_000_000, "정정이 마감월을 바꿈!"
assert m5_after!=m5_before, "정정이 미래월에 반영 안 됨"
ok.append("A 마감월 정정 고정")

# ── B. 다권역 동시 drain: 권역 독립 차감 ──
S=store([
 ("booster.create",C(region="R1",planned_count=5,avg_unit_cost=8_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01",None),
 ("booster.create",C(region="R2",planned_count=3,avg_unit_cost=7_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01",None),
 ("booster.drain",{"region":"R1","count_delta":1,"new_card":C(id="m1",site_id="m1",cost_center="c",facility_type="mobile",region="R1",classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=8_000_000)},"2026-11-10","2026-10-01",None),
 ("booster.drain",{"region":"R2","count_delta":1,"new_card":C(id="m2",site_id="m2",cost_center="c",facility_type="mobile",region="R2",classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=7_000_000)},"2026-11-10","2026-10-01",None),
])
_,b,_=lf.fold(S.events)
assert b["R1"]["planned_count"]==4 and b["R2"]["planned_count"]==2, f"다권역 drain 오류 {b['R1']['planned_count']},{b['R2']['planned_count']}"
ok.append("B 다권역 drain 독립")

# ── C. 부분 실적월: lease만 실적, CAM 미도래 → CAM 오탐 없음 ──
rows=[];seq=[0]
row("card.create",C(id="SH2",site_id="s2",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,
    cam_monthly=10_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("actual.post",C(site="s2",gl=lf.GL_LEASE,month=1,amount=100_000_000,doc="d"),"2026-10-05","M01")  # lease만
sp=FakeSP(rows); r=run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)
lease_m1=next(x for x in pl("2026-10-31") if x["GL"]==lf.GL_LEASE and x["Month"]==1)
cam_m1=next(x for x in pl("2026-10-31") if x["GL"]==lf.GL_CAM and x["Month"]==1)
assert lease_m1["Scenario"]=="actual" and cam_m1["Scenario"]=="base", "부분 실적 처리 오류"
assert r["breaches"]==0, f"부분 실적 오탐 breach {r['breaches']}"
ok.append("C 부분 실적 오탐 없음")

# ── D. supersede 체인 A←B←C: 최종 C만 반영 ──
S=lf.EventStore()
S.append("card.create",C(id="X",site_id="x",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
a=S.append("card.amend",C(card_id="X",field="monthly_rent",value=110_000_000),"2026-10-01","2026-09-01")
b=S.append("card.amend",C(card_id="X",field="monthly_rent",value=120_000_000),"2026-10-02","2026-09-01",supersedes=a.id)
c=S.append("card.amend",C(card_id="X",field="monthly_rent",value=130_000_000),"2026-10-03","2026-09-01",supersedes=b.id)
cards,_,_=lf.fold(S.events)
assert cards["X"]["monthly_rent"]==130_000_000, f"supersede 체인 오류 {cards['X']['monthly_rent']}"
# as-of: B 시점엔 120 (C 이전)
cards_b,_,_=lf.fold(S.as_of("2026-10-02"))
assert cards_b["X"]["monthly_rent"]==120_000_000, "as-of 체인 중간 재현 오류"
ok.append("D supersede 체인 최종/중간")

# ── E. 확정 갱신: horizon 내 연장분 포착 ──
S=lf.EventStore()
S.append("card.create",C(id="R1",site_id="r1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=24,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
S.append("lifecycle",{"card_id":"R1","type":"renewal","month":24,"add_months":24,"new_rent":110_000_000,"certainty":"confirmed"},"2026-10-01","M24")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
base,_,_=lf.aggregate(P,HZ,"base")
assert base.get(30,0)>0, "확정 갱신 연장분 horizon 내 누락"
ok.append("E 확정 갱신 horizon 내 포착")

# ── F. rent-free + escalation: 정액 = 총지급/기간, 월 flat ──
S=lf.EventStore()
S.append("card.create",C(id="F1",site_id="f1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,
    escalation_annual=0.03,rent_free_months=3,certainty="confirmed"),"2026-09-30","2026-09-01")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
lease=[p.amount for p in P if p.gl==lf.GL_LEASE and p.source_card=="F1" and 1<=p.month<=36]
# 총지급: 무상 3개월 제외, 연 3% 상승 단계
pay=sum(100_000_000*((1.03)**((m-1)//12)) for m in range(1,37) if m>3)
assert abs(sum(lease)-pay)<5 and max(lease)-min(lease)<1, f"rent-free+esc 정액 오류 Δ{max(lease)-min(lease):.0f}"
ok.append("F rent-free+escalation 정액")

# ── G. drain 수 보존: 권역 mobile 유닛 수 = (남은 plan)+(전환 카드) ──
S=store([
 ("booster.create",C(region="G",planned_count=5,avg_unit_cost=8_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01",None),
 ("booster.drain",{"region":"G","count_delta":1,"new_card":C(id="g1",site_id="g1",cost_center="c",facility_type="mobile",region="G",classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=8_000_000)},"2026-11-10","2026-10-01",None),
])
cards,boost,_=lf.fold(S.events)
units=boost["G"]["planned_count"]+sum(1 for d in cards.values() if d.get("region")=="G" and d["facility_type"]=="mobile")
assert units==5, f"drain 수 보존 실패 {units}"
ok.append("G drain 수 보존")

# ── H. overlay-only 월: 불확실 갱신만 있는 월 → 무크래시, overlay 기록 ──
rows=[];seq=[0]
row("card.create",C(id="H1",site_id="h1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=12,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("lifecycle",{"card_id":"H1","type":"renewal","month":12,"add_months":12,"new_rent":100_000_000,"certainty":"uncertain"},"2026-10-01","M12")
sp=FakeSP(rows); run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)
ov=[x for x in pl("2026-10-31") if x["Scenario"]=="overlay" and x["Month"]>12]
assert ov, "overlay-only 월 미기록"
ok.append("H overlay-only 무크래시")

# ── I. 음수 count 클램프: 과다 drain → planned_count 0 (음수 아님), booster 0 기여 ──
S=store([
 ("booster.create",C(region="I",planned_count=2,avg_unit_cost=8_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01",None),
 ("booster.drain",{"region":"I","count_delta":5,"new_card":C(id="i1",site_id="i1",cost_center="c",facility_type="mobile",region="I",classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=8_000_000)},"2026-11-10","2026-10-01",None),
])
cards,boost,_=lf.fold(S.events)
assert boost["I"]["planned_count"]==0, f"음수 클램프 실패 {boost['I']['planned_count']}"
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
bcost=sum(p.amount for p in P if p.source_card.startswith("BOOSTER") and p.gl==lf.GL_LEASE)
assert bcost==0, f"클램프 후 booster 비용 음수/잔존 {bcost}"
ok.append("I 음수 count 클램프")

# ── J. 불규칙 연차 정액(rent_schedule): escalation% 대신 계약서 명시값으로 정액 ──
S=lf.EventStore()
S.append("card.create",C(id="J1",site_id="j1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=0,
    rent_schedule=[100_000_000,105_000_000,115_000_000],certainty="confirmed"),"2026-09-30","2026-09-01")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
lease=[p.amount for p in P if p.gl==lf.GL_LEASE and p.source_card=="J1" and 1<=p.month<=36]
exp=(12*100_000_000+12*105_000_000+12*115_000_000)/36
assert abs(lease[0]-exp)<1 and max(lease)-min(lease)<1, f"불규칙 연차 정액 오류 {lease[0]:.0f} vs {exp:.0f}"
ok.append("J 불규칙 연차 정액")

# ── K. 동일 site_id 복수 카드 + actualization: 실적 1줄(이중계상 없음) ──
rows=[];seq=[0]
for cid in ("K1","K2"):
    row("card.create",C(id=cid,site_id="shared",cost_center="c",facility_type="sub_hub",region="R",
        classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=50_000_000,
        certainty="confirmed"),"2026-09-30","2026-09-01")
row("actual.post",C(site="shared",gl=lf.GL_LEASE,month=1,amount=90_000_000,doc="d"),"2026-10-05","M01")
sp=FakeSP(rows); run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)
plk=pl("2026-10-31")
m1=[x for x in plk if x["GL"]==lf.GL_LEASE and x["Month"]==1]
assert sum(x["Amount"] for x in m1)==90_000_000 and all(x["Scenario"]=="actual" for x in m1), \
    f"동일 site 이중 실적! m1 합 {sum(x['Amount'] for x in m1)}"
m2=[x for x in plk if x["GL"]==lf.GL_LEASE and x["Month"]==2]
assert sum(x["Amount"] for x in m2)==100_000_000 and all(x["Scenario"]=="base" for x in m2), "미래월 합산 오류"
ok.append("K 동일 site 실적 1줄")

# ── L. horizon 경계 직전 갱신: 절단 정확(>horizon 미기록, 경계내 존재, 무크래시) ──
S=lf.EventStore()
S.append("card.create",C(id="L1",site_id="l1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
S.append("lifecycle",{"card_id":"L1","type":"renewal","month":36,"add_months":24,"new_rent":110_000_000,"certainty":"confirmed"},"2026-10-01","M36")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)   # HZ=48, 갱신 end=60>48
base,_,_=lf.aggregate(P,HZ,"base")
assert base.get(HZ,0)>0, "경계월(48) 누락"
assert HZ+1 not in base, "horizon 초과월이 집계에 포함됨"
# 경계 정확히 끝나는 카드: term이 horizon에 딱 맞음 → 마지막월 존재, 다음월 없음
S2=lf.EventStore()
S2.append("card.create",C(id="L2",site_id="l2",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=HZ,monthly_rent=80_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
P2,_,_=lf.project_portfolio(S2.events,HZ,EPOCH); b2,_,_=lf.aggregate(P2,HZ,"base")
assert b2.get(HZ,0)>0, "term=horizon 카드 마지막월 누락"
ok.append("L horizon 경계 갱신 절단")

# ── M. 부분 전표: 동일 (site,gl,month) 복수 actual.post 합산(덮어쓰기 아님) ──
rows=[];seq=[0]
row("card.create",C(id="M1",site_id="m1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("actual.post",C(site="m1",gl=lf.GL_LEASE,month=1,amount=60_000_000,doc="d1"),"2026-10-05","M01")
row("actual.post",C(site="m1",gl=lf.GL_LEASE,month=1,amount=40_000_000,doc="d2"),"2026-10-06","M01")  # 분할
sp=FakeSP(rows); r=run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)
m1=[x for x in pl("2026-10-31") if x["GL"]==lf.GL_LEASE and x["Month"]==1]
assert sum(x["Amount"] for x in m1)==100_000_000 and all(x["Scenario"]=="actual" for x in m1), \
    f"부분 전표 합산 실패 {sum(x['Amount'] for x in m1)}"
assert r["breaches"]==0, "부분전표 합산 후 오탐"   # 60+40=100=forecast → 위반 없음
ok.append("M 부분 전표 합산")

# ── N. relocation 경계: 겹침/공백 없음(스팬 내 매월 정확히 1줄) ──
S=lf.EventStore()
S.append("card.create",C(id="A",site_id="a",cost_center="c",facility_type="mobile",region="R",
    classification="operating",commencement="2026-09-01",term_months=12,monthly_rent=8_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
lf.relocate(S,"A",C(id="B",site_id="b",cost_center="c",facility_type="mobile",region="R",
    classification="operating",commencement="IGNORED",term_months=12,monthly_rent=8_500_000,certainty="confirmed"),
    month=6,recorded_at="2027-02-20")
P,_,_=lf.project_portfolio(S.events,24,EPOCH)
import collections
permonth=collections.Counter(p.month for p in P if p.gl==lf.GL_LEASE and p.scenario=="base")
span=[m for m in range(1, max(permonth)+1)]
assert all(permonth[m]==1 for m in span), f"relocation 겹침/공백! {dict(permonth)}"
ok.append("N relocation 경계 1줄")

# ── O. booster start_month > horizon: 무크래시, 기여 0 ──
S=lf.EventStore()
S.append("booster.create",C(region="O",planned_count=3,avg_unit_cost=8_000_000,start_month=60,dept_reliability=0.7),"2026-09-30","2026-10-01")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
assert sum(p.amount for p in P if p.source_card.startswith("BOOSTER"))==0, "horizon 밖 booster가 기여"
ok.append("O booster start>horizon 무크래시")

# ── P. as-of 실적 전 시점: actualization 없음(순수 forecast) ──
rows=[];seq=[0]
row("card.create",C(id="P1",site_id="p1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
sp=FakeSP(rows); run_worker(sp,horizon=HZ,today="2026-09-30",epoch=EPOCH)   # 실적 전 마감
assert not [x for x in pl("2026-09-30") if x["Scenario"]=="actual"], "실적 전인데 actual 라인 발생"
ok.append("P 실적 전 순수 forecast")

# ── Q. 비-12배수 term + 부분연도 escalation: 정액 정확, 인덱스 오류 없음 ──
S=lf.EventStore()
S.append("card.create",C(id="Q1",site_id="q1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=30,monthly_rent=100_000_000,
    escalation_annual=0.03,certainty="confirmed"),"2026-09-30","2026-09-01")
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
lease=[p.amount for p in P if p.gl==lf.GL_LEASE and p.source_card=="Q1" and 1<=p.month<=30]
pay=sum(100_000_000*(1.03**((m-1)//12)) for m in range(1,31))   # m1-12 yr0,13-24 yr1,25-30 yr2
assert abs(sum(lease)-pay)<5 and max(lease)-min(lease)<1 and len(lease)==30, "비-12배수 정액 오류"
ok.append("Q 비-12배수 부분연도")

# ── R. rent_schedule 엔트리 부족 → 마지막값 clamp ──
S=lf.EventStore()
S.append("card.create",C(id="R2",site_id="r2",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=0,
    rent_schedule=[100_000_000,110_000_000],certainty="confirmed"),"2026-09-30","2026-09-01")  # 3년차 누락
P,_,_=lf.project_portfolio(S.events,HZ,EPOCH)
y3=[p.amount for p in P if p.gl==lf.GL_LEASE and p.source_card=="R2"]  # 정액이라 flat
exp=(12*100_000_000+12*110_000_000+12*110_000_000)/36   # 3년차=2년차 clamp
assert abs(y3[0]-exp)<1, f"rent_schedule clamp 오류 {y3[0]:.0f} vs {exp:.0f}"
ok.append("R rent_schedule 부족 clamp")

# ── S. 동일 region booster.create 2건 동시각 → 높은 Seq(나중 append) 우선(결정론) ──
S=lf.EventStore()
S.append("booster.create",C(region="S",planned_count=5,avg_unit_cost=8_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01")
S.append("booster.create",C(region="S",planned_count=3,avg_unit_cost=9_000_000,start_month=1,dept_reliability=0.7),"2026-09-30","2026-10-01")
_,b,_=lf.fold(S.events)
assert b["S"]["planned_count"]==3 and b["S"]["avg_unit_cost"]==9_000_000, "동시각 booster 순서 비결정"
ok.append("S 동시각 booster 결정론")

# ── T. actual이 horizon 밖 월: 무크래시, ProjectionLines 미생성 ──
rows=[];seq=[0]
row("card.create",C(id="T1",site_id="t1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
row("actual.post",C(site="t1",gl=lf.GL_LEASE,month=HZ+5,amount=100_000_000,doc="d"),"2026-10-05",f"M{HZ+5}")
sp=FakeSP(rows); run_worker(sp,horizon=HZ,today="2026-10-31",epoch=EPOCH)   # 무크래시
assert not [x for x in pl("2026-10-31") if x["Month"]>HZ], "horizon 밖 실적이 ProjectionLines에 유입"
ok.append("T horizon 밖 실적 무크래시")

# ── U. 다중 필드 amend(monthly_rent + cam_monthly) → 둘 다 반영 ──
S=lf.EventStore()
S.append("card.create",C(id="U1",site_id="u1",cost_center="c",facility_type="sub_hub",region="R",
    classification="operating",commencement="2026-09-01",term_months=36,monthly_rent=100_000_000,cam_monthly=5_000_000,certainty="confirmed"),"2026-09-30","2026-09-01")
S.append("card.amend",C(card_id="U1",field="monthly_rent",value=120_000_000),"2026-10-01","2026-09-01")
S.append("card.amend",C(card_id="U1",field="cam_monthly",value=7_000_000),"2026-10-01","2026-09-01")
cards,_,_=lf.fold(S.events)
assert cards["U1"]["monthly_rent"]==120_000_000 and cards["U1"]["cam_monthly"]==7_000_000, "다중 필드 amend 누락"
ok.append("U 다중 필드 amend")

# ── V. booster 없는 region에 drain → 무크래시, 카드만 추가 ──
S=lf.EventStore()
S.append("booster.drain",{"region":"Z","count_delta":1,"new_card":C(id="z1",site_id="z1",cost_center="c",
    facility_type="mobile",region="Z",classification="operating",commencement="2026-10-01",term_months=12,monthly_rent=8_000_000)},"2026-11-10","2026-10-01")
cards,b,_=lf.fold(S.events)
assert "z1" in cards and "Z" not in b, "booster 없는 drain 처리 오류"
ok.append("V booster 없는 drain")

print("의심 케이스 통과 ✓")
for x in ok: print("  ✓", x)

# 다른 경로(정렬·누적 비율 직접 계산, groupby)로 주요 값을 다시 계산해 check_1.py 결과와 대조
import json, numpy as np, pandas as pd
P="/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
df=pd.read_parquet(P)
res={(r["id"],r["reading_no"]):r for r in map(json.loads, open("/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r3/truth/check_1.jsonl",encoding="utf-8"))}
def q2(sub, var, wv, q):
    s=sub[[var,wv]].dropna().sort_values(var, kind="stable")
    share=s[wv].cumsum()/s[wv].sum()
    return float(s.loc[share>=q-1e-15, var].iloc[0])
def cmp(tag, mine, ref):
    ok = all((a is None and b is None) or (a is not None and b is not None and abs(a-b)<=1e-9*max(1,abs(b))) for a,b in zip(mine,ref))
    print(tag, "OK" if ok else "DIFF", mine if not ok else "", ref if not ok else "")
vals=lambda k:[c["value"] for c in res[k]["cells"]]
# 균등화 소득·빈곤·분위
hh=df.groupby("hid").agg(s=("p_dinc","sum"), n=("hnum","first"))
eq=df.hid.map(hh.s/np.sqrt(hh.n))
t=pd.DataFrame({"eq":eq,"w":df.indwgt})
med=q2(t,"eq","w",0.5); qb=[q2(t,"eq","w",q) for q in (.2,.4,.6,.8)]
poor=eq<med/2
quint=np.digitize(eq, qb, right=False)+1
print("med",med,"qb",qb, "pop poverty rate", (df.indwgt[poor].sum()/df.indwgt.sum()*100), "quint shares", [round(df.indwgt[quint==k].sum()/df.indwgt.sum()*100,3) for k in range(1,6)])
# A009
d=df[df.age>=65]; p=poor[df.age>=65]
g=(d.bp_yn1==1)
cmp("A009",[d.indwgt[g&p].sum()/d.indwgt[g].sum()*100, d.indwgt[~g&p].sum()/d.indwgt[~g].sum()*100], vals(("A009",1)))
# A013
d=df[df.itc_yn==1]; qd=quint[df.itc_yn==1]
cmp("A013",[d.indwgt[qd==k].sum()/d.indwgt.sum()*100 for k in range(1,6)], vals(("A013",1)))
# A033
d=df[df.sido.isin([2,7,16])].assign(poor=poor, a3=pd.cut(df.age,[-1,17,64,200],labels=False))
cmp("A033",[ (x.indwgt*x.poor).sum()/x.indwgt.sum()*100 for _,x in d.groupby("a3")], vals(("A033",1)))
# A024
d=df[(df.age>=7)&(df.age<=18)].assign(poor=poor, num=(df.nbls_edu_amt1>0))
cmp("A024",[ (x.indwgt*x.num).sum()/x.indwgt.sum()*100 for _,x in d.groupby("poor",sort=False) ][::1] if d.poor.iloc[0] else [ (x.indwgt*x.num).sum()/x.indwgt.sum()*100 for _,x in sorted(d.groupby("poor"), key=lambda kv: -kv[0])], vals(("A024",1)))
# A005
h=df[(df["head"]==1)&(df.sido==1)&(df.h_ee_deposit_amt_ptot>0)].assign(k=lambda x:x.hnum.clip(upper=4))
cmp("A005",[q2(x,"h_ee_deposit_amt_ptot","hhwgt",0.5) for _,x in h.groupby("k")], vals(("A005",1)))
# A017
d=df[df.vocaedu_yn==1].assign(k=pd.cut(df.age,[-1,34,49,200],labels=False))
cmp("A017",[q2(x,"vocaedu_amt","indwgt",0.75) for _,x in d.groupby("k")], vals(("A017",1)))
# A036
d=df[(df.age>=60)&(df.pubpen_inc>0)].assign(k=pd.cut(df.age,[59,64,69,79,200],labels=False))
cmp("A036",[q2(x,"pubpen_inc","indwgt",0.5) for _,x in d.groupby("k")], vals(("A036",1)))
# A042, A027
cmp("A042",[q2(df[(df.age>=65)&(df.gender==1)&(df.govp_pension_yn==1)],"govp_pension_amt","indwgt",0.25)], vals(("A042",1)))
d=df[df.ltcare_daynight_yn.astype(float)==1].assign(f=lambda x:x.ltcare_daynight_freq.astype(float))
cmp("A027",[q2(d,"f","indwgt",0.5)], vals(("A027",1)))
# A001 두 해석
d=df[df.age>=65]
for rn,v in ((1,"bp_yn1"),(2,"bp_yn2")):
    x=d.assign(num=(d[v]==1)*d.indwgt).groupby("sido").agg(a=("num","sum"),b=("indwgt","sum"))
    cmp(f"A001-{rn}", list(x.a/x.b*100), vals(("A001",rn)))
# A004
d=df.assign(num=(df.nhi_in_emergency_dur>=1)*df.indwgt, a6=pd.cut(df.age,[-1,17,34,49,64,74,200],labels=False))
x=d.groupby(["a6","gender"]).agg(a=("num","sum"),b=("indwgt","sum"))
cmp("A004", list(x.a/x.b*100), vals(("A004",1)))
# A016
d=df[df.age>=65].assign(num=lambda x:(x.ltcare_bn_yn.astype(float)==1)*x.indwgt, a=lambda x:pd.cut(x.age,[64,74,84,200],labels=False))
x=d.groupby(["a","gender"]).agg(a_=("num","sum"),b=("indwgt","sum"))
cmp("A016", list(x.a_/x.b*100), vals(("A016",1)))
# A020, A003, A045, A014
h=df[df["head"]==1]
x=h[h.sido.isin([3,15])].assign(b=lambda x:pd.cut(x.h_prop,[-1,1e8-0.5,3e8-0.5,6e8-0.5,1e20],labels=False)).groupby(["sido","b"]).hhwgt.sum()
cmp("A020", list(x), vals(("A020",1)))
cmp("A003",[h[(h.age>=65)&(h.hnum==1)&(h.h_prop<100000000)].hhwgt.sum()], vals(("A003",1)))
x=h[h.age>=75].assign(k=lambda x:x.hnum.clip(upper=4)).groupby("k").apply(lambda x:np.average(x.h_pubinc,weights=x.hhwgt))
cmp("A045", list(x), vals(("A045",1)))
x=h.assign(k=pd.cut(h.age,[-1,39,59,200],labels=False), num=(h.h_ptax_building>0)*h.hhwgt).groupby("k").agg(a=("num","sum"),b=("hhwgt","sum"))
cmp("A014", list(x.a/x.b*100), vals(("A014",1)))
# 합계·평균 몇 가지
cmp("A008",[ (df.nhi_in_tehospital_amt*df.indwgt)[df.sido==k].sum() for k in (1,4,9)], vals(("A008",1)))
cmp("A044",[ (df.fainc_tax*df.indwgt)[df.sido<=8].sum(), (df.fainc_tax*df.indwgt)[df.sido>=9].sum()], vals(("A044",1)))
cmp("A030",[ (df.disp_bn_amt*df.indwgt)[df.gender==g].sum() for g in (1,2)], vals(("A030",1)))
cmp("A018",[ (df.milp_premium_amt*df.indwgt).sum()], vals(("A018",1)))
d=df[(df.sido.isin([5,13,14]))&(df.bp_yn2==1)]
x=d.groupby(["bp_type","gender"]).apply(lambda x:np.average(x.bp_amt,weights=x.indwgt))
cmp("A034", list(x), vals(("A034",1)))
d=df[(df.unempbn_jobseekbn_yn==1)].assign(k=lambda x:pd.cut(x.unempbn_jobseekbn_dur,[-1,89,149,10000],labels=False))
cmp("A047", list(d.groupby("k").indwgt.sum()), vals(("A047",1)))
d=df[df.dis_yn==1].assign(t=lambda x:x.nhi_type.map({1:0,2:0,5:1,6:1,7:2,8:2}))
x=d.groupby(["dis_grade_1","t"]).indwgt.sum(); x=x/x.groupby(level=0).transform("sum")*100
cmp("A048", list(x), vals(("A048",1)))
# 참고: A021 대체 변수, A018 고정시점 가입여부
d=df[(df.age>=50)&(df.gender==1)&(df.dainc_sum>0)].assign(t=lambda x:x.nhi_type.map({1:0,2:0,5:1,6:1,7:2,8:2}))
print("A021 dainc_sum", list(d.groupby("t").apply(lambda x:np.average(x.dainc_sum,weights=x.indwgt))))
print("A021 p_dainc  ", list(d.groupby("t").apply(lambda x:np.average(x.p_dainc,weights=x.indwgt))))
print("milp_yn2", df.milp_yn2.value_counts(dropna=False).to_dict(), "sum yn2==1", (df.milp_premium_amt*df.indwgt)[df.milp_yn2==1].sum())
print("p_dainc>0 n", (df.p_dainc>0).sum(), "dainc_sum>0 n", (df.dainc_sum>0).sum())

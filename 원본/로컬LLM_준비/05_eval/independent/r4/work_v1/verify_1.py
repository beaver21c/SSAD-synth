# check_1.jsonl 재검: 다른 경로(pandas groupby·정렬 누적합)로 일부 칸을 다시 계산해 대조
import json, numpy as np, pandas as pd
P="/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT="/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/truth/check_1.jsonl"
df=pd.read_parquet(P)
R={}
for line in open(OUT,encoding="utf-8"):
    r=json.loads(line); R[(r["id"],r["reading_no"])]=r
ids=sorted({k[0] for k in R}); print("ids",len(ids),"lines",len(R), "missing:",[f"A{i:03d}" for i in range(1,49) if f"A{i:03d}" not in ids])
# 형식 점검
for k,r in R.items():
    assert set(r)=={"id","turn","reading_no","reading","pct","cells","ambiguous","note"},k
    for c in r["cells"]:
        assert "labels" in c and "value" in c and "n" in c,k
        if r["pct"]: assert "n_num" in c,k
        if c["n"]==0: assert c["value"] is None,k
        else: assert c["value"] is not None,k
def cell(qid,labels,rn=1):
    for c in R[(qid,rn)]["cells"]:
        if c["labels"]==labels: return c
    raise KeyError((qid,labels))
def close(a,b): return abs(a-b)<=1e-9*max(1,abs(a),abs(b))
def pq(d,col,w,q):
    d=d[[col,w]].dropna().astype(float).sort_values(col,kind="mergesort")
    c=d[w].cumsum(); t=q*d[w].sum()
    i=int((c>=t).to_numpy().argmax())
    # 경계 여유 확인
    margin=min((c.iloc[i]-t), (t-c.iloc[i-1]) if i>0 else np.inf)/d[w].sum()
    return float(d[col].iloc[i]), margin
ok=True
def chk(name,a,b):
    global ok
    good=close(a,b); ok&=good
    print(("OK  " if good else "DIFF"),name,a,b)
# 균등화 소득(가구 합계 h_dinc 사용이라는 다른 경로)
df["eq"]=df["h_dinc"]/np.sqrt(df["hnum"])
med,mg=pq(df,"eq","indwgt",0.5); print("median margin",mg)
df["poor"]=df["eq"]<0.5*med
b=[pq(df,"eq","indwgt",q) for q in (.2,.4,.6,.8)]; print("quint margins",[x[1] for x in b])
df["quint"]=1+sum((df["eq"]>=x[0]).astype(int) for x in b)
# A001 서울
d=df[(df.age>=65)&(df.sido==1)]; chk("A001 서울",100*d.loc[d.nhi_out_tehospital_dur.notna(),"indwgt"].sum()/d.indwgt.sum(),cell("A001",["서울"])["value"])
# A002 75+
d=df[(df.nbls_live_yn2==1)&(df.nbls_house_yn2==1)&(df.age>=75)]; chk("A002 75+",d.indwgt.sum(),cell("A002",["75세 이상"])["value"])
# A005 2인
d=df[(df["head"]==1)&(df.h_ee_deposit_amt_ptot>0)&(df.hnum==2)]; v,mg=pq(d,"h_ee_deposit_amt_ptot","hhwgt",.5); chk("A005 2인",v,cell("A005",["2인"])["value"]); print("  margin",mg)
# A007 70~74 여
d=df[(df.age.between(70,74))&(df.gender==2)]; chk("A007",100*d.loc[d.bp_yn2==1,"indwgt"].sum()/d.indwgt.sum(),cell("A007",["70~74세","여"])["value"])
# A009 직장 18~64
d=df[df.nhi_type.isin([5,6])&df.age.between(18,64)]; chk("A009",(d.nhi_in_gehospital_amt*d.indwgt).sum(),cell("A009",["직장가입","18~64세"])["value"])
# A011
d=df[df.age>=65]; g=d[d.bp_yn1==1]; chk("A011 수급",100*g.loc[g.poor,"indwgt"].sum()/g.indwgt.sum(),cell("A011",["기초연금 수급"])["value"])
g=d[d.bp_yn1!=1]; chk("A011 비수급",100*g.loc[g.poor,"indwgt"].sum()/g.indwgt.sum(),cell("A011",["기초연금 비수급"])["value"])
# A012 경남
d=df[(df["head"]==1)&(df.sido==16)&(df.h_pubinc>=1e7)]; chk("A012 경남",d.hhwgt.sum(),cell("A012",["경남"])["value"])
# A015
d=df[df.ltcare_daynight_yn.astype(float)==1].copy(); d["f"]=d.ltcare_daynight_freq.astype(float); v,mg=pq(d,"f","indwgt",.25); chk("A015",v,cell("A015",[])["value"]); print("  margin",mg)
# A019 65+
d=df[(df["head"]==1)&(df.age>=65)]; chk("A019",100*d.loc[d.h_ptax_building>0,"hhwgt"].sum()/d.hhwgt.sum(),cell("A019",["65세 이상"])["value"])
# A024 여 3분위
d=df[(df.gender==2)&(df.quint==3)&df.nhi_out_clinic_amt.notna()]; v,mg=pq(d,"nhi_out_clinic_amt","indwgt",.5); chk("A024",v,cell("A024",["여","3분위"])["value"]); print("  margin",mg)
for gname,gv in (("남",1),("여",2)):
    for k in range(1,6):
        d=df[(df.gender==gv)&(df.quint==k)&df.nhi_out_clinic_amt.notna()]; v,mg=pq(d,"nhi_out_clinic_amt","indwgt",.5)
        if not close(v,cell("A024",[gname,f"{k}분위"])["value"]) or mg<1e-9: ok=False; print("DIFF/margin A024",gname,k,v,mg)
# A027
d=df[(df["head"]==1)&df.sido.isin([5,13,14])&(df.age>=65)&(df.hnum==1)&(df.h_prop<5e7)]; chk("A027",d.hhwgt.sum(),cell("A027",[])["value"])
# A028 빈곤
d=df[df.age.between(6,17)&df.poor]; chk("A028",100*d.loc[d.pubedu_aftsch_yn==1,"indwgt"].sum()/d.indwgt.sum(),cell("A028",["빈곤"])["value"])
# A031 두 해석
d=df[(df.dis_yn==1)&(df.dis_disp_yn==1)&(df.age>=65)]
chk("A031 r1",100*d.loc[d.disp_yn2==1,"indwgt"].sum()/d.indwgt.sum(),cell("A031",["65세 이상"],1)["value"])
chk("A031 r2",100*d.loc[d.disp_yn1==1,"indwgt"].sum()/d.indwgt.sum(),cell("A031",["65세 이상"],2)["value"])
# A035 남 65~74
d=df[(df.age.between(65,74))&(df.gender==1)&((df.govp_pension_yn==1)|(df.privschp_pension_yn==1)|(df.milip_pension_yn==1))]; chk("A035",d.indwgt.sum(),cell("A035",["남","65~74세"])["value"])
# A036, A045 margins
d=df[df.privschp_pension_yn==1]; v,mg=pq(d,"privschp_pension_amt","indwgt",.5); chk("A036",v,cell("A036",[])["value"]); print("  margin",mg)
for lab,m in (("수도권",df.sido.isin([1,4,9])),("비수도권",~df.sido.isin([1,4,9]))):
    d=df[m&(df.pubedu_aftsch_yn==1)]; v,mg=pq(d,"pubedu_aftsch_amt","indwgt",.5); chk("A045 "+lab,v,cell("A045",[lab])["value"]); print("  margin",mg)
for lab,m in (("1인",df.hnum==1),("3인",df.hnum==3),("4인 이상",df.hnum>=4)):
    d=df[(df["head"]==1)&(df.h_ee_deposit_amt_ptot>0)&m]; v,mg=pq(d,"h_ee_deposit_amt_ptot","hhwgt",.5); chk("A005 "+lab,v,cell("A005",[lab])["value"]); print("  margin",mg)
# A039 3인
d=df[(df.age<=17)&(df.hnum==3)]; chk("A039",100*d.loc[d.poor,"indwgt"].sum()/d.indwgt.sum(),cell("A039",["3인"])["value"])
# A043
d=df[(df.age>=65)&(df.ltcare_bn_yn.astype(float)==1)&df.ltcare_grade.astype(float).isin([1,2,3])]; chk("A043",100*d.loc[d.ltcare_institute_freq.astype(float)>=180,"indwgt"].sum()/d.indwgt.sum(),cell("A043",[])["value"])
# A046
d=df[(df["head"]==1)&(df.sido==17)&(df.age>=65)]; chk("A046",100*d.loc[d.h_prop<1e8,"hhwgt"].sum()/d.hhwgt.sum(),cell("A046",[])["value"])
# A047 여 4등급
d=df[(df.ltcare_bn_yn.astype(float)==1)&(df.gender==2)]; chk("A047",100*d.loc[d.ltcare_grade.astype(float)==4,"indwgt"].sum()/d.indwgt.sum(),cell("A047",["여","4등급"])["value"])
# 구성비 합 100 확인
for q,grp in (("A006",None),("A032",None)):
    print(q,"sum",sum(c["value"] for c in R[(q,1)]["cells"]))
print("A017 sums",[sum(c["value"] for c in R[("A017",1)]["cells"] if c["labels"][0]==a) for a in ("30세 미만","30~34세","35세 이상")])
print("A047 sums",[sum(c["value"] for c in R[("A047",1)]["cells"] if c["labels"][0]==a) for a in ("남","여")])
print("ALL OK" if ok else "SOME DIFF")

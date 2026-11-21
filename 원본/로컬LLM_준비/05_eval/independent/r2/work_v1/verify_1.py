# 다른 구현(pandas groupby·정렬 누적)으로 일부 질문을 재계산해 check_1.jsonl과 대조
import json, numpy as np, pandas as pd
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
rows=[json.loads(l) for l in open('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/truth/check_1.jsonl',encoding='utf-8')]
R={(r['id'],r['reading_no']):r for r in rows}
def vals(i,k=1): return [c['value'] for c in R[(i,k)]['cells']]
def wq(d,x,w,q):
    d=d[[x,w]].dropna().sort_values(x); c=d[w].cumsum(); return d.loc[c.ge(q*d[w].sum()).idxmax(),x] if len(d) else None
ok=True
def chk(name,a,b):
    global ok
    a=[np.nan if v is None else float(v) for v in a]; b=[np.nan if v is None else float(v) for v in b]
    good=np.allclose(a,b,rtol=1e-9,equal_nan=True); ok&=good
    print(name,'OK' if good else f'DIFF {a} vs {b}')
# 균등화 소득
df['eq']=df.groupby('hid')['p_dinc'].transform('sum')/np.sqrt(df['hnum'])
med=wq(df,'eq','indwgt',.5); df['poor']=df['eq']<med/2
b=[wq(df,'eq','indwgt',q) for q in (.2,.4,.6,.8)]
df['qt']=1+sum((df['eq']>=x).astype(int) for x in b)
print('분위별 가중 비중', (df.groupby('qt')['indwgt'].sum()/df['indwgt'].sum()*100).round(3).to_dict(), '전체 빈곤율', round(100*np.average(df['poor'],weights=df['indwgt']),3))
# A001
d=df[df.age>=65].assign(y=lambda t:t.bp_yn2.eq(1)*t.indwgt)
chk('A001',(d.groupby('sido')['y'].sum()/d.groupby('sido')['indwgt'].sum()*100).tolist(),vals('A001'))
# A004
h=df[df['head']==1].copy(); h['g']=pd.cut(h.age,[-1,39,59,200],labels=False)
h['y']=(h.h_ee_deposit_amt_ptot>0)*h.hhwgt
chk('A004',(h.groupby('g')['y'].sum()/h.groupby('g')['hhwgt'].sum()*100).tolist(),vals('A004'))
# A016
t=h[(h.age<=39)&(h.h_ee_deposit_amt_ptot>0)&h.sido.isin([1,4,9])]
chk('A016',[np.average(t[t.sido==s].h_ee_deposit_amt_ptot,weights=t[t.sido==s].hhwgt) for s in (1,4,9)],vals('A016'))
# A033
h['hg']=h.hnum.clip(upper=4)
chk('A033',[wq(h[h.hg==k],'h_prop','hhwgt',.5) for k in (1,2,3,4)],vals('A033'))
# A046
t=h[h.age>=65]; chk('A046',(t.groupby('hg')['hhwgt'].sum()/t.hhwgt.sum()*100).tolist(),vals('A046'))
# A020, A040
d=df[df.age<=5].assign(y=lambda t:t.carebn_yn2.eq(1)*t.indwgt)
chk('A020',(d.groupby('qt')['y'].sum()/d.groupby('qt')['indwgt'].sum()*100).tolist(),vals('A020'))
d=df[df.childbn_yn2.eq(1)]; chk('A040',(d.groupby('qt')['indwgt'].sum()/d.indwgt.sum()*100).tolist(),vals('A040'))
# A022, A048, A010, A013
df['ng']=df.nhi_type.map({1:0,2:0,5:1,6:1,7:2,8:2})
chk('A022',[100*np.average(g.poor,weights=g.indwgt) for _,g in df.groupby('ng')],vals('A022'))
d=df[df.dis_yn.eq(1)]; chk('A048',[100*np.average(g.poor,weights=g.indwgt) for _,g in d.groupby('dis_grade_1')],vals('A048'))
d=df[df.age>=65]; chk('A010',[100*np.average(g.poor,weights=g.indwgt) for g in (d[d.bp_yn1.eq(1)],d[~d.bp_yn1.eq(1)])],vals('A010'))
d=df[df.age.between(6,17)]; chk('A013',[100*np.average(g.pubedu_aftsch_yn.eq(1),weights=g.indwgt) for g in (d[d.poor],d[~d.poor])],vals('A013'))
# A018, A009, A038, A041, A045
d=df[(df.age>=65)&df.pubpen_inc.gt(0)]
chk('A018',[wq(d[(d.gender==g)&m],'pubpen_inc','indwgt',.5) for g in (1,2) for m in (d.age<=74,d.age>=75)],vals('A018'))
d=df[df.p_dainc>0]; chk('A009-1',[wq(d[d.gender==g],'p_dainc','indwgt',.25) for g in (1,2)],vals('A009',1))
chk('A009-2',[wq(df[df.gender==g],'dainc_sum','indwgt',.25) for g in (1,2)],vals('A009',2))
chk('A038',[wq(df[df.privschp_pension_yn.eq(1)],'privschp_pension_amt','indwgt',.5)],vals('A038'))
t=df[df.ltcare_institute_yn.eq(1).fillna(False)].assign(f=lambda t:t.ltcare_institute_freq.astype(float)); chk('A041',[wq(t,'f','indwgt',.5)],vals('A041'))
t=df[(df.hnum==1)&(df.age>=80)&(df.gender==1)]; chk('A045',[wq(t,'nhi_in_gehospital_dur','indwgt',.5)],vals('A045'))
# A006, A043, A014, A034, A039
d=df[df.kua_yn1.eq(1)]; chk('A006',d.groupby(['kua_type','gender'])['indwgt'].sum().tolist(),vals('A006'))
d=df[df.bp_yn2.eq(1)&df.sido.isin([5,13,14])]; chk('A043',d.groupby(['sido','bp_type'])['indwgt'].sum().tolist(),vals('A043'))
chk('A014',[df.loc[df[v].eq(1),'indwgt'].sum() for v in ('govp_yn2','privschp_yn2','milp_yn2')],vals('A014'))
chk('A034',[df.loc[(df.age>=65)&(df.hnum==1)&df.dis_yn.eq(1),'indwgt'].sum()],vals('A034'))
# A027, A035, A042
df['rg']=np.select([df.sido.isin([1,4,9]),df.sido.isin([2,3,7,15,16])],[0,1],2)
chk('A027',(df.pubedu_aftsch_amt*df.indwgt).groupby(df.rg).sum().tolist(),vals('A027'))
chk('A035',(df.nhi_in_gehospital_amt*df.indwgt).groupby(pd.cut(df.age,[-1,17,64,200],labels=False)).sum().tolist(),vals('A035'))
chk('A042',(df.empins_matleave_amt*df.indwgt).groupby(df.age>=35).sum().tolist(),vals('A042'))
# A007, A008, A012, A021, A024, A030, A044, A015
def wm(d,x): d=d.dropna(subset=[x]); return np.average(d[x].astype(float),weights=d.indwgt) if len(d) else None
d=df[df.disp_bn_yn1.eq(1)&(df.age>=18)]; chk('A007',[wm(d[d.age<=64],'disp_bn_amt'),wm(d[d.age>=65],'disp_bn_amt')],vals('A007'))
d=df[df.ltcare_visit_yn.eq(1).fillna(False)]; gg=d.ltcare_grade.astype(float)
chk('A008',[wm(d[gg.isin([1,2])],'ltcare_visit_freq'),wm(d[gg==3],'ltcare_visit_freq'),wm(d[gg==4],'ltcare_visit_freq'),wm(d[gg==5],'ltcare_visit_freq')],vals('A008'))
chk('A012',[wm(df[df.sido==s],'nhi_in_tehospital_dur') for s in (2,7,16)],vals('A012'))
chk('A021',[wm(df[(df.sido==1)&(df.age>=75)&(df.gender==2)],'nhi_out_gehospital_subsidy')],vals('A021'))
d=df[df.milp_yn1.eq(1)]; chk('A024',[wm(d[d.age<30],'milp_premium_amt'),wm(d[d.age.between(30,39)],'milp_premium_amt'),wm(d[d.age>=40],'milp_premium_amt')],vals('A024'))
d=df[(df.age>=30)]; chk('A030',[wm(d[d.p_prop<1e8],'fainc_tax'),wm(d[(d.p_prop>=1e8)&(d.p_prop<5e8)],'fainc_tax'),wm(d[d.p_prop>=5e8],'fainc_tax')],vals('A030'))
chk('A044',[wm(df[df.age.between(a,b)],'nbls_edu_amt1') for a,b in ((6,11),(12,14),(15,17))],vals('A044'))
chk('A015',[wm(df,'empins_matleave_dur')],vals('A015'))
chk('A047',[wm(df[df.sido==s],'empins_spouseleave_dur') for s in range(1,18)],vals('A047'))
# 비율류
def rt(d,numr): return 100*(d.indwgt*numr.reindex(d.index)).sum()/d.indwgt.sum()
chk('A002',[rt(df[df.age>=65],df.nhi_highbp_yn.eq(1))],vals('A002'))
ag=pd.cut(df.age,[-1,39,64,74,200],labels=False)
chk('A005',[rt(df[ag==k],df.nhi_in_emergency_dur.ge(1)) for k in range(4)],vals('A005'))
chk('A011',[rt(df[df.self_yn1.eq(1)],df.self_yn2.eq(1))],vals('A011'))
chk('A017',[rt(df[df.dis_yn.eq(1)&df.dis_disp_yn.eq(1)&df.age.between(18,64)&(df.hnum==1)],df.disp_yn1.eq(1))],vals('A017'))
d=df[df.unempbn_bnextended_yn.eq(1)]; chk('A019',[rt(d,df.unempbn_bnextended_reason.eq(k)) for k in (1,2,5,6,8)],vals('A019'))
chk('A023',[rt(df[df.aid_live_yn1.eq(1)],df.aid_live_yn2.eq(1))],vals('A023'))
chk('A025-1',[rt(df[df.bp_yn2.eq(1)&(df.gender==g)],df.bp_type.eq(t)) for g in (1,2) for t in (1,2,3)],vals('A025',1))
chk('A025-2',[rt(df[df.bp_yn1.eq(1)&(df.gender==g)],df.bp_type.eq(t)) for g in (1,2) for t in (1,2,3)],vals('A025',2))
chk('A026',[rt(df[df.dis_yn.eq(1)],df.nhi_out_tehospital_dur.ge(1)),rt(df[~df.dis_yn.eq(1)],df.nhi_out_tehospital_dur.ge(1))],vals('A026'))
hh=df[(df['head']==1)&(df.hnum==1)&(df.age>=65)&df.nbls_live_yn2.eq(1)]
chk('A028',[100*(hh.hhwgt*hh.evou_yn.eq(1)).sum()/hh.hhwgt.sum()],vals('A028'))
lt=df.ltcare_bn_yn.eq(1).fillna(False).astype(bool)
chk('A029',[rt(df[df.age.between(a,b)&(df.gender==g)],lt) for a,b in ((65,74),(75,84),(85,200)) for g in (1,2)],vals('A029'))
d=df[df.sido.isin([1,4,9])&df.age.between(18,34)&df.empins_yn1.eq(1)]
chk('A031',[rt(d[d.gender==g],df.unempbn_jobseekbn_yn.eq(1)) for g in (1,2)],vals('A031'))
chk('A032',[rt(df[df.empins_parentleave_yn1.eq(1)],df.gender.eq(1))],vals('A032'))
d=df[(df.hnum==1)&(df.age>=75)]; cap=d.sido.isin([1,4,9])
chk('A036',[rt(d[cap],df.oldcare_yn2.eq(1)),rt(d[~cap],df.oldcare_yn2.eq(1))],vals('A036'))
chk('A037',[rt(df[df.oldwork_type2_yn1.eq(1)],df.oldwork_type2_end_yn.eq(1))],vals('A037'))
chk('A003-1',[df.loc[df.childcare_yn1.eq(1)&m,'indwgt'].sum() for m in (df.age<=2,df.age>=3)],vals('A003',1))
chk('A003-2',[df.loc[df.childcare_yn2.eq(1)&m,'indwgt'].sum() for m in (df.age<=2,df.age>=3)],vals('A003',2))
chk('A039',[df.loc[(df.sido==17)&df.aid_live_yn1.eq(1),'indwgt'].sum()],vals('A039'))
print('전체 일치' if ok else '불일치 있음', '/ 줄 수', len(rows), '/ 질문 수', len({r['id'] for r in rows}))

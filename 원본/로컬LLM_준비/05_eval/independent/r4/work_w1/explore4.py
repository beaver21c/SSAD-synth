import sys
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load, codebook, wquantile
df = load()
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 600)
m = df.dainc_sum.notna()
r = (df.loc[m,"p_dainc"]/df.loc[m,"dainc_sum"])
print("p_dainc/dainc_sum ratio quantiles", r.quantile([.01,.25,.5,.75,.99]).round(4).tolist())
m = df.pripen_inc.notna()
r = (df.loc[m,"p_pripeninc"]/df.loc[m,"pripen_inc"])
print("p_pripeninc/pripen_inc ratio quantiles", r.quantile([.01,.25,.5,.75,.99]).round(4).tolist())
m = df.othinc_sum.notna()
print("p_othinc/othinc_sum_inc", (df.loc[m,"p_othinc"]/df.loc[m,"othinc_sum_inc"]).quantile([.01,.25,.5,.75,.99]).round(4).tolist())
inc = [c for c in df.columns if c.startswith("inc_") and c!="inc5"]
print({c:int(df[c].notna().sum()) for c in inc})
def agecounts(mask, bins, name):
    a = df.loc[mask,"age"]
    c = pd.cut(a, bins, right=False).value_counts().sort_index()
    print(name, dict(zip([str(i) for i in c.index], c.values.tolist())))
B = [0,6,12,15,18,25,30,35,40,50,60,65,70,75,80,85,200]
for nm, mk in [("matleave", df.empins_matleave_yn1==1), ("parentleave", df.empins_parentleave_yn1==1), ("jobseek", df.unempbn_jobseekbn_yn==1),
               ("aftsch", df.pubedu_aftsch_yn==1), ("nbls_edu", df.nbls_edu_yn1==1), ("childcare", df.childcare_yn1==1), ("ltcare_bn", df.ltcare_bn_yn==1),
               ("ltcare_yn", df.ltcare_yn==1), ("oldcare", df.oldcare_yn1==1), ("privschp_prem", df.privschp_yn1==1), ("milp", df.milp_yn1==1),
               ("privschp_pen", df.privschp_pension_yn==1), ("govp_pen", df.govp_pension_yn==1), ("disp_bn", df.disp_bn_yn1==1), ("disp", df.disp_yn1==1),
               ("dis", df.dis_yn==1), ("dis_sev", df.dis_grade_1==1), ("youthemp_amt1", df.youthemp_amt1.notna()), ("single_rear", df.single_rear_yn1==1),
               ("single_edu", df.single_edu_yn==1), ("aid_live", df.aid_live_yn1==1), ("disvou", df.disvou_act_yn1==1), ("vocaedu", df.vocaedu_yn==1),
               ("pregnant", df.nhi_pregnant_yn==1), ("bp", df.bp_yn1==1), ("pripen", df.pripen_inc.notna()), ("pubpen", df.pubpen_inc.notna()),
               ("dainc", df.p_dainc>0), ("allo", df.inc_allo>0), ("sehou", df.inc_sehou_sum>0), ("inc_pens", df.inc_pens_sum>0), ("oldwork1", df.oldwork_type1_yn1==1),
               ("childbn", df.childbn_yn1==1), ("carebn", df.carebn_yn1==1), ("infantbn", df.infantbn_yn1==1), ("kua", df.kua_yn1==1), ("evou", df.evou_yn==1),
               ("culvou", df.culvou_yn==1), ("rm", df.rm_yn==1), ("np_pen", df.np_pension_yn==1), ("highbp", df.nhi_highbp_yn==1), ("copd", df.nhi_copd_yn==1),
               ("cardiac", df.nhi_cardiac_yn==1), ("tehosp_in", df.nhi_in_tehospital_dur.notna()), ("emer", df.nhi_in_emergency_dur.notna()), ("all", df.age>=0)]:
    agecounts(mk, B, nm)
print("age 0..7 counts:", df.age[df.age<=7].value_counts().sort_index().to_dict())
print("childcare yn2==1 by age:", df.loc[df.childcare_yn2==1,"age"].value_counts().sort_index().to_dict())
print("gender x parentleave:", df.loc[df.empins_parentleave_yn1==1,"gender"].value_counts().to_dict(), "matleave gender", df.loc[df.empins_matleave_yn1==1,"gender"].value_counts().to_dict())
print("hnum dist heads:", df.loc[df["head"]==1,"hnum"].value_counts().sort_index().to_dict())
print("ltcare_grade x ltcare_bn_yn:", pd.crosstab(df.ltcare_grade, df.ltcare_bn_yn).to_dict())
print("dis_grade x disp_yn2:", pd.crosstab(df.dis_grade_1, df.disp_yn2.fillna(-1)).to_dict())
print("dis_type_1:", df.dis_type_1.value_counts().sort_index().to_dict())
print("nhi_type x nbls_medi_yn2:", pd.crosstab(df.nhi_type, df.nbls_medi_yn2.fillna(0)).to_dict())

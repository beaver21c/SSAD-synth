import sys
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load, codebook, wquantile
df = load()
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 600)
# 1. p_X vs X equality (among X notna)
pairs = [("p_dainc","dainc_sum"),("p_pripeninc","pripen_inc"),("p_privschp_pension_amt","privschp_pension_amt"),
 ("p_empins_matleave_amt","empins_matleave_amt"),("p_empins_spouseleave_amt","empins_spouseleave_amt"),
 ("p_aid_live_amt","aid_live_amt"),("p_aid_house_amt","aid_house_amt"),("p_nbls_edu_amt1","nbls_edu_amt1"),
 ("p_aid_edu_amt","aid_edu_amt"),("p_disp_bn_amt","disp_bn_amt"),("p_single_rear_amt","single_rear_amt"),
 ("p_single_edu_amt","single_edu_amt"),("p_privschp_premium_amt","privschp_premium_amt"),("p_milp_premium_amt","milp_premium_amt"),
 ("p_ptax_building","ptax_building"),("p_ee_deposit_amt_ptot","ee_deposit_amt_ptot"),("pubpen_inc","np_pension_amt"),
 ("p_othinc","othinc_sum"),("p_othinc","othinc_sum_inc"),("p_fininc","fainc_sum"),("inc_pens_sum","pubpen_inc"),("p_bp_amt","bp_amt"),
 ("p_nbls_live_amt","nbls_live_amt"),("p_unempbn_jobseekbn_amt","unempbn_jobseekbn_amt"),("nhi_premium_cal","nhi_premium_set")]
for a,b in pairs:
    m = df[b].notna()
    eq = np.isclose(df.loc[m,a].astype(float), df.loc[m,b].astype(float), rtol=1e-6, atol=1).mean()
    # a>0 where b isna
    extra = ((df[a] > 0) & ~m).sum()
    print(f"{a} vs {b}: equal among {b}.notna = {eq:.4f}; {a}>0 while {b} NaN: {extra}; n={m.sum()}")
# h_ variables consistency
for hv, pv in [("h_ee_deposit_amt_ptot","p_ee_deposit_amt_ptot"),("h_ptax_building","p_ptax_building"),("h_prop","p_prop"),("h_pubinc","p_pubinc")]:
    s = df.groupby("hid")[pv].transform("sum")
    print(hv, "== hh sum of", pv, np.isclose(s, df[hv], atol=1).mean())
# 2. sido sample sizes
print(df.groupby("sido").agg(n=("hid","size"), n65=("age", lambda s:(s>=65).sum()), n017=("age", lambda s:(s<=17).sum()), heads=("head", lambda s:(s==1).sum())).T.to_string())
# 3. inc_* co-missing
inc = [c for c in df.columns if c.startswith("inc_") and c!="inc5"]
print("inc cols", len(inc), "all same notna pattern:", all((df[c].notna()==df[inc[0]].notna()).all() for c in inc))
# labinc/othinc/binc
print("nhi_highbp notna vs nhi_in_dur notna crosstab:")
print(pd.crosstab(df.nhi_highbp_yn.notna(), df.nhi_in_dur.notna()))
print("age>=65 & highbp notna:", ((df.age>=65)&df.nhi_highbp_yn.notna()).sum(), "age<65 & notna:", ((df.age<65)&df.nhi_highbp_yn.notna()).sum())
print("nhi_special notna by?", pd.crosstab(df.nhi_special1_yn.notna(), df.dis_yn.notna()))
print("nhi_out notna by nhi3:", pd.crosstab(df.nhi3, df.nhi_out_dur.notna()))
print("nhi_ceiling_subsidy_yn NaN by nhi3:", pd.crosstab(df.nhi3, df.nhi_ceiling_subsidy_yn.fillna(-1)))
print("age dist key:", df.age.describe().to_string())

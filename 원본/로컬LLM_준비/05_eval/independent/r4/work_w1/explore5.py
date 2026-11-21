import sys
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load
from runner import run_spec
from items_def import S, bins, groups
df = load()
pd.set_option("display.width", 250)
G5 = groups(("수도권", "sido in [1, 4, 9]"), ("충청권", "sido in [6, 8, 11, 12]"), ("호남권", "sido in [5, 13, 14]"), ("영남권", "sido in [2, 3, 7, 15, 16]"), ("강원·제주", "sido in [10, 17]"))
tests = {
 "C4a dis+medi 18+": S("count", "age >= 18 and dis_yn == 1 and nbls_medi_yn2 == 1", [G5]),
 "C4b dis sev + bp?": S("count", "age >= 65 and dis_grade_1 == 1 and bp_yn2 == 1", [G5]),
 "C4c dis + live yn2 18+": S("count", "age >= 18 and dis_yn == 1 and nbls_live_yn2 == 1", [G5]),
 "R7a no bp": S("rate", "sido in [2, 3, 7, 15, 16] and age >= 65 and hnum == 1", [{"std": "poor2"}], numerator="oldcare_yn1 == 1"),
 "R7b bp all sido": S("rate", "age >= 65 and hnum == 1 and bp_yn1 == 1", [{"std": "poor2"}], numerator="oldcare_yn1 == 1"),
 "R7c yeongnam bp by sex": S("rate", "sido in [2, 3, 7, 15, 16] and age >= 65 and hnum == 1 and bp_yn1 == 1", [{"std": "sex"}], numerator="oldcare_yn1 == 1"),
 "R7d yeongnam bp by age75": S("rate", "sido in [2, 3, 7, 15, 16] and age >= 65 and hnum == 1 and bp_yn1 == 1", [bins("age",[75],["65~74","75+"])], numerator="oldcare_yn1 == 1"),
 "R7e yeongnam+honam bp poor2": S("rate", "sido in [2, 3, 5, 7, 13, 14, 15, 16] and age >= 65 and hnum == 1 and bp_yn1 == 1", [{"std": "poor2"}], numerator="oldcare_yn1 == 1"),
 "R14 groups edu": S("rate", "age >= 6 and age <= 17", [groups(("교육급여","nbls_edu_yn1 == 1"),("비수급","nbls_edu_yn1.isna()"))], numerator="pubedu_aftsch_yn == 1"),
 "R14 poor2": S("rate", "age >= 6 and age <= 17", [{"std":"poor2"}], numerator="pubedu_aftsch_yn == 1"),
 "share parent leave 35": S("share", "empins_parentleave_yn1 == 1", [bins("age", [35], ["35-", "35+"])], value_var="sex"),
 "ltcare share nosex": S("share", "ltcare_bn_yn == 1", [], value_var="ltcare_grade"),
 "aid_house rate": S("rate", "aid_house_yn1 == 1", [], numerator="aid_house_yn2 == 1"),
 "poor heads": S("share", "poor == 1", [], unit="household", value_var="hs4"),
}
for k, sp in tests.items():
    print("\n==", k); o = run_spec(df, sp); print(o.assign(value=o["value"].where(o["n"] >= 10)).to_string(float_format=lambda x: f"{x:,.2f}", na_rep="(가림)"))

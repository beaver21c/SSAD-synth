# -*- coding: utf-8 -*-
"""작업자 w2 확인용: G 문항에 붙인 코드를 분석 함수(ssda)로 실제 실행하고, 산출 정의의 참값과 비교.

실행(로컬LLM_준비 폴더에서):
  SSDA_DATA=<parquet> PYTHONPATH=02_library python 05_eval/independent/r2/work_w2/run_G.py
집계 결과만 출력함.
"""
import json, os, re, sys, io, contextlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, compute, sig3

ITEMS = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/items/G.jsonl'
# 결함을 바로잡은 코드(검증용, 문항에는 넣지 않음)
FIX = {
 'G01': "import ssda\nr = ssda.rate('childcare_yn2 == 1', where='age <= 5')",
 'G03': "import ssda\nr = ssda.count(where='kua_yn2 == 1', by='kua_type')",
 'G04': "import ssda\nr = ssda.rate('oldcare_yn2 == 1', where='age >= 65', by='sex')",
 'G05': "import ssda\nr = ssda.rate('h_dinc < 30000000', by='sido', unit='가구')",
 'G06': "import ssda\nr = ssda.mean('culvou_bn', where='culvou_yn == 1', by='sex')",
 'G07': "import ssda\nr = ssda.count(where='govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1')",
 'G08': "import ssda\nr = ssda.mean('nhi_out_dur', by='age10')",
 'G09': "import ssda\nr = ssda.rate('disvou_act_yn1 == 1', where='dis_yn == 1', by='sex')",
 'G10': "import ssda\nr = ssda.total('itc_amt', where='itc_yn == 1', by='itc_hmember')",
 'G11': "import ssda\nr = ssda.mean('h_prop', by='hs4', unit='가구')",
}
AMOUNT_VARS = {'culvou_bn', 'itc_amt', 'h_prop', 'p_prop'}   # 원 단위 → 함수는 만원으로 환산

def run(code):
    ns = {}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, ns)
    except Exception as e:
        return None, f'{type(e).__name__}: {str(e)[:120]}'
    r = ns.get('r')
    t = r.table()
    vals = [None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v) for v in t['값']]
    return vals, None

def truth(spec):
    rows = compute(spec, load())
    out = []
    for lab, v, n, aux in rows:
        if spec['measure'] in ('rate', 'share', 'poverty_rate'):
            out.append(round(float(v), 1))
        else:
            if spec.get('value_var') in AMOUNT_VARS:
                v = v / 1e4
            out.append(float(sig3(float(v))))
    return out

def close(a, b):
    if a is None or b is None or len(a) != len(b):
        return False
    return all(x is not None and y is not None and abs(x - y) <= max(1e-9, 0.006 * abs(y)) for x, y in zip(a, b))

bad = 0
for line in open(ITEMS, encoding='utf-8'):
    it = json.loads(line)
    code = re.findall(r'```python\n(.*?)```', it['turns'][0], flags=re.S)[0]
    tv = truth(it['specs'][0])
    vals, e = run(code)
    same = close(vals, tv)
    if it['defect'] == '없음':
        ok = same
        state = '참값과 일치' if same else '참값과 불일치(문제)'
    elif it['defect'].startswith('실행되지 않는'):
        ok = e is not None
        state = f'실행 오류 발생({e})' if ok else '오류 없이 실행됨(문제)'
    else:
        ok = (e is None) and (not same)
        state = '실행됨, 참값과 다름' if ok else f'의도와 다름(문제): 오류={e}, 일치={same}'
    fixs = ''
    if it['id'] in FIX:
        fv, fe = run(FIX[it['id']])
        fok = close(fv, tv)
        ok = ok and fok
        fixs = f" | 바로잡은 코드: {'참값과 일치' if fok else '불일치(문제) ' + str(fv) + ' ' + str(fe)}"
    bad += (not ok)
    print(f"{it['id']} [{it['defect']}] {state}{fixs}")
    print(f"     붙인 코드 결과: {vals if e is None else '-'}")
    print(f"     산출 정의 참값: {tv}")
print('\n문제 문항 수:', bad)
sys.exit(1 if bad else 0)

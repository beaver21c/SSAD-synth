#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정책 변화 모의실험(정태적 산술 모형) — 연구자 사례

  (가) 기초연금: 수급 범위(65세 이상 중 소득 하위 p%, 5%p 단위) × 월 급여 변화(5만원 단위) × 인구감소지역 추가 지원
  (나) 아동수당: 지급 대상 연령 상한(1세 단위) × 월 지급액(1만원 단위) × 인구감소지역 추가 지원
  인구감소지역: 행정안전부 2021년 10월 지정 89개 시군구(자료 기준연도 2022에 맞춤). 거주 수급자에게 월 추가 지원액을 더함
  (2026-11-21 확장: 범위 5%p 단위, 급여 −10~+20만원, 아동수당 10~20만원 1만원 단위, 인구감소지역 차등 적용, 지역별 빈곤율)

방법
  · 가상데이터(확대본)의 개인별 급여액과 가처분소득에 제도 변경분을 더해 가구 소득을 다시 계산한다.
  · 행동 변화(노동 공급, 신청률 변화)와 다른 급여와의 연동(생계급여의 소득 산정 등)은 반영하지 않는다.
  · 빈곤선은 현행 균등화 가처분소득 중위값의 50%로 고정한다.
  · 산출값은 전국·소득 5분위·시도 단위 집계이며, 가중 인원·금액은 유효숫자 3자리로 반올림한다(출력 통제 R1·R6).

실행
  .venv/bin/python scripts/02_simulate.py data/가상데이터_확대본_n42000.parquet data/sim.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
MIN_CELL = 30                                    # 모의실험 산출 칸의 최소 관측 수


def sig3(x):
    if x is None or not np.isfinite(x):
        return None
    if x == 0:
        return 0
    k = int(math.floor(math.log10(abs(x)))) - 2
    v = round(x / 10 ** k) * 10 ** k
    return int(v) if k >= 0 else round(v, -k)


df = pd.read_parquet(SRC, columns=['hid', 'age', 'hnum', 'sido', 'city', 'indwgt', 'p_dinc', 'bp_yn1', 'bp_amt', 'childbn_yn1', 'childbn_amt'])
N = len(df)
w = df['indwgt'].astype(float).values
age = df['age'].astype(int).values
hid = df['hid'].values
hnum = df['hnum'].astype(float).values
sido = df['sido'].astype(int).values - 1
pd0 = df['p_dinc'].astype(float).values
hcode, _ = pd.factorize(hid)
# 인구감소지역(행정안전부 2021. 10. 지정 89곳, 자료의 옛 시군구 코드). 군위군은 경북 코드(47720)와 대구 편입 코드(27720)를 함께 씀
DEC_CODES = {26170, 26140, 26200, 27200, 27170, 27720, 47720, 28710, 28720, 41820, 41800,
             42820, 42230, 42800, 42830, 42750, 42770, 42780, 42190, 42760, 42720, 42790, 42730,
             43760, 43800, 43720, 43740, 43730, 43150,
             44150, 44710, 44230, 44180, 44760, 44770, 44810, 44790, 44825,
             45790, 45210, 45190, 45730, 45800, 45770, 45750, 45740, 45180, 45720,
             46810, 46770, 46720, 46730, 46710, 46780, 46910, 46870, 46830, 46890, 46880, 46800, 46900, 46860, 46820, 46790,
             47830, 47280, 47920, 47250, 47840, 47170, 47770, 47760, 47210, 47230, 47940, 47930, 47730, 47820, 47750,
             48880, 48820, 48840, 48270, 48860, 48720, 48740, 48850, 48730, 48870, 48890}
dec = np.isin(df['city'].astype(int).values, list(DEC_CODES))
NH = hcode.max() + 1


def eqinc(pdinc):
    return np.bincount(hcode, weights=pdinc, minlength=NH)[hcode] / np.sqrt(hnum)


def wq(x, ww, q):
    o = np.argsort(x); c = np.cumsum(ww[o])
    return x[o][min(np.searchsorted(c, c[-1] * q), len(x) - 1)]


eq0 = eqinc(pd0)
Z = 0.5 * wq(eq0, w, .5)                          # 빈곤선(고정)
quint = np.digitize(eq0, [wq(eq0, w, q) for q in (.2, .4, .6, .8)])


def rate(mask, cond):
    n = int((mask & cond).sum())
    assert n >= MIN_CELL and int((mask & ~cond).sum()) >= MIN_CELL, '출력 통제: 관측 수 미달'
    return round(100 * w[mask & cond].sum() / w[mask].sum(), 2)


def gap(mask, eq):
    return round(100 * (w[mask] * np.clip(Z - eq[mask], 0, None) / Z).sum() / w[mask].sum(), 2)


def by(groups, k, mask, values):
    """집단별 가중 평균(관측 수 미달 칸은 None)."""
    out = []
    for g in range(k):
        m = mask & (groups == g)
        out.append(sig3(float((w[m] * values[m]).sum() / w[m].sum())) if m.sum() >= MIN_CELL else None)
    return out


def bysum(groups, k, mask, values, scale=1.0):
    out = []
    for g in range(k):
        m = mask & (groups == g)
        out.append(sig3(float((w[m] * values[m]).sum() / scale)) if m.sum() >= MIN_CELL else None)
    return out


# ═════════════════════════ 지역별 결과(2026-11-21) ═════════════════════════
def prate(mask, eq):
    """대상 집단의 빈곤율(%) — 관측 수 미달이면 None."""
    pc = eq < Z
    if int((mask & pc).sum()) < MIN_CELL or int((mask & ~pc).sum()) < MIN_CELL:
        return None
    return round(100 * w[mask & pc].sum() / w[mask].sum(), 1)


def region(mask, eq):
    sp = [prate(mask & (sido == g), eq) for g in range(17)]
    ok = [v for v in sp if v is not None]
    return {'sido_pov': sp, 'dec_pov': [prate(mask & dec, eq), prate(mask & ~dec, eq)],
            'rng': round(max(ok) - min(ok), 1), 'sd': round(float(np.std(ok)), 2)}


# ═════════════════════════ (가) 기초연금 ═════════════════════════
old = age >= 65
bp0 = (df['bp_yn1'] == 1).values
a0 = df['bp_amt'].fillna(0).astype(float).values                 # 연 급여액(원)
hh_bp = np.bincount(hcode, weights=a0, minlength=NH)[hcode]
eq_ex = (np.bincount(hcode, weights=pd0, minlength=NH)[hcode] - hh_bp) / np.sqrt(hnum)   # 기초연금 제외 균등화 소득
mean_amt = (w[bp0] * a0[bp0]).sum() / w[bp0].sum()
r0 = 100 * w[bp0].sum() / w[old].sum()
order = np.argsort(eq_ex[old]); idx_old = np.where(old)[0][order]; cum = np.cumsum(w[idx_old]) / w[old].sum() * 100
rank_pct = np.full(N, np.nan); rank_pct[idx_old] = cum                                   # 65세 이상 내 소득 순위(%)

P_LIST = list(range(50, 101, 5))                                  # 수급 범위(%), 5%p 단위
D_LIST = [-10, -5, 0, 5, 10, 15, 20]                              # 월 급여 변화(만원), 5만원 단위
X_LIST = [0, 5, 10]                                               # 인구감소지역 거주 수급자 월 추가 지원(만원)


def bp_scenario(p, d, x):
    if p == 70:
        rec = bp0.copy()
    elif p > 70:                                                  # 확대: 현행 수급자 + 소득이 낮은 순으로 추가
        rec = bp0 | (old & (rank_pct <= p))
    else:                                                         # 축소: 현행 수급자 중 소득 하위 p%만 유지
        rec = bp0 & (rank_pct <= p)
    base = np.where(bp0, a0, mean_amt)
    a1 = np.where(rec, np.clip(base + d * 12e4, 0, None) + np.where(dec, x * 12e4, 0.0), 0.0)
    eq1 = eqinc(pd0 + (a1 - a0))
    return rec, a1, eq1


bp_grid = {}
for p in P_LIST:
    for d in D_LIST:
        for x in X_LIST:
            rec, a1, eq1 = bp_scenario(p, d, x)
            cost = (w * a1).sum()
            g = {
                'rec': sig3(float(w[rec].sum())), 'rate': round(100 * w[rec].sum() / w[old].sum(), 1),
                'cost': sig3(cost / 1e12), 'dcost': sig3((cost - (w * a0).sum()) / 1e12),
                'xcost': sig3(float((w * np.where(rec & dec, x * 12e4, 0.0)).sum()) / 1e12),
                'pov65': rate(old, eq1 < Z), 'pov': rate(np.ones(N, bool), eq1 < Z), 'gap65': gap(old, eq1),
                'q_gain': by(quint, 5, old, (a1 - a0) / 1e4),          # 65세 이상 1인당 연 급여 변화(만원), 소득 분위별
                'q_rate': [round(100 * w[old & (quint == g_) & rec].sum() / w[old & (quint == g_)].sum(), 1) for g_ in range(5)],
                'sido_dcost': bysum(sido, 17, old, a1 - a0, 1e8),      # 시도별 추가 소요액(억원)
                'sido_gain': by(sido, 17, old, (a1 - a0) / 1e4),       # 시도별 65세 이상 1인당 연 급여 변화(만원)
            }
            g.update(region(old, eq1))
            bp_grid[f'{p}|{d}|{x}'] = g
            if x == 0:
                bp_grid[f'{p}|{d}'] = g                           # 이전 주소(#a=70&b=10)와 사례 자료의 호환

# ═════════════════════════ (나) 아동수당 ═════════════════════════
kid = age < 18
cb0 = (df['childbn_yn1'] == 1).values
c0 = df['childbn_amt'].fillna(0).astype(float).values
U_LIST = list(range(8, 19))                                       # 대상 연령 상한(세 미만), 1세 단위
M_LIST = list(range(10, 21))                                      # 월 지급액(만원), 1만원 단위
XC_LIST = [0, 5, 10]                                              # 인구감소지역 거주 수급 아동 월 추가 지원(만원)


def cb_scenario(u, m, x):
    new = (age >= 8) & (age < u)                                  # 새로 대상이 되는 연령(전원 수급 가정)
    rec = cb0 | new
    c1 = np.where(cb0, c0 * (m / 10.0), 0.0) + np.where(new & ~cb0, m * 12e4, 0.0) + np.where(rec & dec, x * 12e4, 0.0)
    eq1 = eqinc(pd0 + (c1 - c0))
    return rec, c1, eq1


cb_grid = {}
for u in U_LIST:
    for m in M_LIST:
        for x in XC_LIST:
            rec, c1, eq1 = cb_scenario(u, m, x)
            cost = (w * c1).sum()
            g = {
                'rec': sig3(float(w[rec].sum())), 'rate': round(100 * w[rec].sum() / w[kid].sum(), 1),
                'cost': sig3(cost / 1e12), 'dcost': sig3((cost - (w * c0).sum()) / 1e12),
                'xcost': sig3(float((w * np.where(rec & dec, x * 12e4, 0.0)).sum()) / 1e12),
                'povkid': rate(kid, eq1 < Z), 'pov': rate(np.ones(N, bool), eq1 < Z), 'gapkid': gap(kid, eq1),
                'q_gain': by(quint, 5, kid, (c1 - c0) / 1e4),
                'q_rate': [round(100 * w[kid & (quint == g_) & rec].sum() / w[kid & (quint == g_)].sum(), 1) for g_ in range(5)],
                'sido_dcost': bysum(sido, 17, kid, c1 - c0, 1e8),
                'sido_gain': by(sido, 17, kid, (c1 - c0) / 1e4),
            }
            g.update(region(kid, eq1))
            cb_grid[f'{u}|{m}|{x}'] = g
            if x == 0:
                cb_grid[f'{u}|{m}'] = g

n_dec = int(np.unique(df['city'].astype(int).values[dec]).size)
pop_dec = round(100 * w[dec].sum() / w.sum(), 1)
sim = {
    'poverty_line': sig3(Z / 1e4),
    'dec': {'name': '인구감소지역', 'n_city': n_dec, 'pop_share': pop_dec, 'old_share': round(100 * w[old & dec].sum() / w[old].sum(), 1),
            'kid_share': round(100 * w[kid & dec].sum() / w[kid].sum(), 1), 'basis': '행정안전부 2021년 10월 지정 89개 시군구'},
    'bp': {'name': '기초연금 수급 범위·급여액 조정', 'p': P_LIST, 'd': D_LIST, 'x': X_LIST, 'base': '70|0|0',
           'p_label': '수급 범위(65세 이상 중 소득 하위 %)', 'd_label': '월 급여 변화(만원)', 'x_label': '인구감소지역 추가 지원(월, 만원)',
           'group': '65세 이상', 'base_rate': round(r0, 1), 'mean_amt': sig3(mean_amt / 1e4), 'grid': bp_grid,
           'notes': ['현행은 자료의 수급 여부를 그대로 사용함(수급률 %.1f%%). 범위 70%%를 현행으로 둠' % r0,
                     '확대 시 비수급자를 기초연금 제외 균등화 소득이 낮은 순으로 편입하고 현행 평균 급여액을 적용함',
                     '인구감소지역 추가 지원: 해당 시군구에 사는 수급자에게 월 추가액을 더함(행정안전부 2021년 지정 89곳)',
                     '부부 감액, 소득역전 방지 감액, 생계급여와의 연동은 반영하지 않음']},
    'child': {'name': '아동수당 대상 연령·지급액 조정', 'u': U_LIST, 'm': M_LIST, 'x': XC_LIST, 'base': '8|10|0',
              'u_label': '대상 연령 상한(세 미만)', 'm_label': '월 지급액(만원)', 'x_label': '인구감소지역 추가 지원(월, 만원)',
              'group': '18세 미만', 'grid': cb_grid,
              'notes': ['현행은 8세 미만, 월 10만원임', '새로 대상이 되는 연령은 전원 수급하는 것으로 가정함',
                        '기존 수급 아동의 급여액은 월 지급액 비율로 조정함',
                        '인구감소지역 추가 지원: 해당 시군구에 사는 수급 아동에게 월 추가액을 더함']},
}
Path(OUT).write_text(json.dumps(sim, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

# 연구자용 결과표(CSV)
rows = []
for k, v in bp_grid.items():
    if k.count('|') != 2:
        continue
    p, d, x = k.split('|')
    rows.append({'제도': '기초연금', '수급 범위(%)': p, '월 급여 변화(만원)': d, '인구감소지역 추가(만원)': x, '수급자(명)': v['rec'], '수급률(%)': v['rate'], '연 소요액(조원)': v['cost'],
                 '추가 소요액(조원)': v['dcost'], '대상 집단 빈곤율(%)': v['pov65'], '전체 빈곤율(%)': v['pov'], '대상 집단 빈곤갭(%)': v['gap65']})
for k, v in cb_grid.items():
    if k.count('|') != 2:
        continue
    u, m, x = k.split('|')
    rows.append({'제도': '아동수당', '대상 연령 상한(세 미만)': u, '월 지급액(만원)': m, '인구감소지역 추가(만원)': x, '수급자(명)': v['rec'], '수급률(%)': v['rate'], '연 소요액(조원)': v['cost'],
                 '추가 소요액(조원)': v['dcost'], '대상 집단 빈곤율(%)': v['povkid'], '전체 빈곤율(%)': v['pov'], '대상 집단 빈곤갭(%)': v['gapkid']})
pd.DataFrame(rows).to_csv(Path(OUT).with_name('모의실험_결과표.csv'), index=False, encoding='utf-8-sig')
b = bp_grid['70|0|0']; c = cb_grid['8|10|0']
print('인구감소지역', sim['dec'])
print('70|10|0 rng', bp_grid['70|10|0']['rng'], bp_grid['70|10|0']['dec_pov'], ' 70|10|10', bp_grid['70|10|10']['rng'], bp_grid['70|10|10']['dec_pov'], bp_grid['70|10|10']['xcost'])
print('빈곤선(만원)', sim['poverty_line'])
print('기초연금 현행:', b['rec'], '명', b['rate'], '%', b['cost'], '조원 · 65+ 빈곤율', b['pov65'], '전체', b['pov'])
print('  70|10:', bp_grid['70|10']['dcost'], '조원, 65+ 빈곤율', bp_grid['70|10']['pov65'], ' / 100|0:', bp_grid['100|0']['dcost'], bp_grid['100|0']['pov65'], ' / 50|10:', bp_grid['50|10']['dcost'], bp_grid['50|10']['pov65'])
print('아동수당 현행:', c['rec'], '명', c['cost'], '조원 · 아동 빈곤율', c['povkid'])
print('  18|10:', cb_grid['18|10']['dcost'], '조원, 아동 빈곤율', cb_grid['18|10']['povkid'], ' / 13|20:', cb_grid['13|20']['dcost'], cb_grid['13|20']['povkid'])
print('q_gain bp 70|10', bp_grid['70|10']['q_gain'], 'q_rate', bp_grid['70|0']['q_rate'])

# -*- coding: utf-8 -*-
"""B32 개인수준 추출의 무편향·분포 점검 (국가 연령·성 구성으로 대규모 MC).
목표: Ⅲ-4 전국 집계(실인원·일수·진료비) 재현 + Ⅲ-11/Ⅲ-12 연간진료비 중위·P90."""
import sys, os
sys.path.insert(0, '/mnt/share/행정데이터_set/work/tools'); os.chdir('/mnt/share/행정데이터_set/work')
import numpy as np, pandas as pd, importlib.util, core
from scipy.stats import norm
spec = importlib.util.spec_from_file_location('b32', 'rules/A5_B32.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

GRIDS, POP_HI, POP_ALL = M._build_grids()
T4 = M._load_t4()
# Ⅲ-11/Ⅲ-12 는 전(全)요양기관 기준이므로 '평균 대비 비율'로 형상만 목표로 삼는다.
#   외래: 중위/평균 = 544,734/977,563 = 0.5572, P90/평균 = 1.7608
#   입원: 중위/평균 = 1,914,755/5,165,572 = 0.3707, P90/평균 = 2.1603
TGT = {'out': dict(rmed=544734/977563, rp90=1721325/977563),
       'in': dict(rmed=1914755/5165572, rp90=11158830/5165572)}


def run(N=400000, sf=None, sr=None, dp=None, seed=7, quiet=False):
    g = np.random.Generator(np.random.PCG64(seed))
    w = (POP_HI / POP_HI.sum()).ravel()
    idx = g.choice(38, size=N, p=w); ai = idx // 2; sj = idx % 2
    zh = norm.ppf(np.clip(g.random(N), 1e-9, 1 - 1e-9))
    POP = POP_HI.sum(); one = np.ones(N)
    out = {}
    for fk, form in (('out', '외래'), ('in', '입원')):
        td = np.zeros(N); ta = np.zeros(N)
        for ik, inst in M.INST.items():
            G = GRIDS[(fk, ik)]; T = T4[(inst, form)]
            use, d, a = M._draw(g, G, ai, sj, zh, one, one, fk,
                                sig_f=(sf or M.SIG_F)[fk], sig_r=(sr or M.SIG_R)[fk], disp=(dp or M.DISP)[fk])
            td += d; ta += a
            out[(form, inst)] = dict(p=use.mean() * POP / T['person'] - 1,
                                     d=d.mean() * POP / T['days'] - 1,
                                     a=a.mean() * POP / T['amt'] - 1)
        x = ta[td > 0]
        out[(form, '총괄')] = dict(med=np.median(x), p90=np.quantile(x, .9), mean=x.mean(),
                                 users=(td > 0).mean() * POP, dmean=td[td > 0].mean())
    return out


if __name__ == '__main__':
    import itertools, json
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if mode == 'tune':
        best = {}
        for fk in ('out', 'in'):
            rows = []
            for sf in (0.30, 0.45, 0.60, 0.75, 0.90):
                for sr in (0.30, 0.45, 0.60, 0.75, 0.90):
                    for dpv in (0.35, 0.6, 1.0, 1.8):
                        sfd = dict(M.SIG_F); srd = dict(M.SIG_R); dpd = dict(M.DISP)
                        sfd[fk] = sf; srd[fk] = sr; dpd[fk] = dpv
                        r = run(120000, sfd, srd, dpd, seed=11)[( '외래' if fk=='out' else '입원', '총괄')]
                        t = TGT[fk]
                        err = abs(np.log((r['med']/r['mean']) / t['rmed'])) + abs(np.log((r['p90']/r['mean']) / t['rp90']))
                        rows.append((err, sf, sr, dpv, round(r['med']/r['mean'],3), round(r['p90']/r['mean'],3), round(r['mean'])))
            rows.sort()
            print('##', fk, 'target', TGT[fk])
            for r in rows[:6]: print('   err=%.3f sf=%.2f sr=%.2f disp=%.2f -> med %s p90 %s mean %s' % r)
            best[fk] = rows[0][1:4]
        print(json.dumps({k: list(v) for k, v in best.items()}))
    else:
        r = run()
        for k, v in r.items():
            if k[1] == '총괄':
                t = TGT['out' if k[0] == '외래' else 'in']
                print(k, 'med/mean %.3f(목표%.3f) p90/mean %.3f(목표%.3f) | med %s p90 %s mean %s users %s dmean %.1f' %
                      (v['med']/v['mean'], t['rmed'], v['p90']/v['mean'], t['rp90'],
                       round(v['med']), round(v['p90']), round(v['mean']), round(v['users']), v['dmean']))
            else:
                print(k, {a: f'{b:+.1%}' for a, b in v.items()})

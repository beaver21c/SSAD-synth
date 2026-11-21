# -*- coding: utf-8 -*-
"""생성 엔진 공통: 난수·분포·파라미터 스키마 (작업지시서 §4.1, §5 규약)."""
from __future__ import annotations
import numpy as np, yaml, os, json, math, re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 난수 (§4.1)
BLOCK_NO = lambda b: int(re.sub(r'\D', '', b))

def rng(block: str) -> np.random.Generator:
    """seed = 20220000 + 블록번호. 블록별 독립·재현 가능."""
    # [T7-a] SYN_SEED_SHIFT=k 이면 seed 에 1000k 를 더한다(강건성 점검 전용, 기본 0)
    return np.random.Generator(np.random.PCG64(20220000 + BLOCK_NO(block)
                                                + 1000 * int(os.environ.get('SYN_SEED_SHIFT', '0'))))

def latent(n: int, seed: int = 20220001):
    """B01에서 1회 생성해 전 블록이 공유하는 개인 잠재변수 (블록 간 상관 유지)."""
    g = np.random.Generator(np.random.PCG64(seed + 1000 * int(os.environ.get('SYN_SEED_SHIFT', '0'))))  # [T7-b]
    return {
        'u_income': g.random(n),   # 소득 성향 분위 (0=저, 1=고)
        'u_health': g.random(n),   # 건강 위험 분위 (0=건강, 1=위험)
        'u_welfare': g.random(n),  # 복지 접촉 성향
        'u_emp': g.random(n),      # 고용 안정성
    }

# ---------------------------------------------------------------- 분포 (§4.1)
def bernoulli(g, p):
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    return (g.random(p.shape) < p).astype(np.int8)

def hist_loguniform(g, edges, weights, n, pareto_alpha=2.0):
    """구간 히스토그램 → 구간 내 로그균등. 마지막 개방구간은 파레토(α).
    edges: [e0, e1, ..., ek] (마지막이 None 이면 개방구간), weights: 길이 k"""
    w = np.asarray(weights, float); w = w / w.sum()
    k = g.choice(len(w), size=n, p=w)
    lo = np.array([edges[i] for i in range(len(w))], float)
    hi_raw = [edges[i + 1] for i in range(len(w))]
    out = np.empty(n)
    for i in range(len(w)):
        m = (k == i)
        c = int(m.sum())
        if c == 0: continue
        a = max(lo[i], 1.0)
        h = hi_raw[i]
        if h is None or (isinstance(h, float) and not np.isfinite(h)):
            # 개방구간: 파레토 (xm = a)
            out[m] = a * (1.0 - g.random(c)) ** (-1.0 / pareto_alpha)
        else:
            b = max(float(h), a * 1.000001)
            out[m] = np.exp(g.uniform(np.log(a), np.log(b), c))
    if edges[0] == 0:
        z = (k == 0)
        out[z] = g.uniform(0, max(edges[1], 1), int(z.sum()))
    return out

def lognormal_mean(g, mean, sigma, n):
    """평균만 알고 분산 미상일 때: 로그정규(σ 명시 필수 — [가정])."""
    mean = np.asarray(mean, float)
    mu = np.log(np.maximum(mean, 1e-9)) - sigma ** 2 / 2
    return g.lognormal(mu, sigma, n if np.isscalar(mean) else None)

def nbinom_mean_disp(g, mean, disp, size=None):
    """음이항: 평균 mean, 과분산 disp(>0, 작을수록 분산 큼)."""
    mean = np.asarray(mean, float)
    p = disp / (disp + np.maximum(mean, 1e-9))
    return g.negative_binomial(disp, p, size)

def dur_months(g, n, pi12, low=1, high=11):
    """급여 수급 개월수: π12 확률로 12개월, 나머지 U(low,high) (§4.1)."""
    d = np.where(g.random(n) < pi12, 12, g.integers(low, high + 1, n))
    return d.astype(np.int16)

def choice_p(g, codes, probs, n):
    p = np.asarray(probs, float); p = p / p.sum()
    return np.asarray(codes)[g.choice(len(codes), size=n, p=p)]

# ---------------------------------------------------------------- 파라미터 (§5 규약)
VALID_STATUS = {'1차확인', '논리적추론', '미확인', '가정'}

@dataclass
class Param:
    var: str
    condition: str = ''
    dist: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)
    status: str = '미확인'
    note: str = ''

    def check(self):
        errs = []
        if self.status not in VALID_STATUS:
            errs.append(f'{self.var}: 잘못된 status {self.status!r}')
        if self.status == '1차확인':
            s = self.source
            if not (s.get('Rcode') or s.get('tblId') or s.get('url') or s.get('file')):
                errs.append(f'{self.var}: status=1차확인 인데 source 근거 없음')
            if not s.get('extract_date'):
                errs.append(f'{self.var}: 1차확인인데 extract_date 없음')
        if not self.dist.get('type'):
            errs.append(f'{self.var}: dist.type 없음')
        return errs

def load_params(path):
    d = yaml.safe_load(open(path, encoding='utf-8')) or {}
    out, errs = {}, []
    for var, spec in (d.get('params') or {}).items():
        p = Param(var=var, condition=spec.get('condition', ''), dist=spec.get('dist', {}) or {},
                  source=spec.get('source', {}) or {}, status=str(spec.get('status', '미확인')),
                  note=spec.get('note', ''))
        errs += p.check(); out[var] = p
    return {'meta': d.get('meta', {}), 'params': out, 'errors': errs}

# ---------------------------------------------------------------- IPF (§4.1 보정)
def ipf(seed_tab, margins, max_iter=1, tol=1e-6):
    """seed_tab: ndarray, margins: [(axis_tuple, target_array), ...]. 반복 1회 원칙."""
    t = np.array(seed_tab, float)
    for _ in range(max_iter):
        for axes, target in margins:
            cur = t.sum(axis=tuple(a for a in range(t.ndim) if a not in axes))
            with np.errstate(divide='ignore', invalid='ignore'):
                f = np.where(cur > 0, np.asarray(target, float) / cur, 1.0)
            shape = [1] * t.ndim
            for i, a in enumerate(axes): shape[a] = t.shape[a]
            t = t * f.reshape([t.shape[a] if a in axes else 1 for a in range(t.ndim)])
    return t

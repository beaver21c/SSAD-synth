# -*- coding: utf-8 -*-
"""§9 검증: S0 캘리브레이션(±3%p) · S1 총량(±10%) · 주변분포 · §7 규칙 위반 0 · NULL 패턴 · seed 재현.
검증 목표값은 targets/*.yaml 에서 읽는다 (전사한 원문 수치 + 출처)."""
from __future__ import annotations
import os, sys, json, html, re, yaml
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consistency

def load_targets(d='targets'):
    ts = []
    if not os.path.isdir(d): return ts
    for f in sorted(os.listdir(d)):
        if f.endswith(('.yaml', '.yml')):
            y = yaml.safe_load(open(os.path.join(d, f), encoding='utf-8')) or {}
            for t in (y.get('targets') or []):
                t.setdefault('file', f); ts.append(t)
    return ts


# ── 파생지표 (targets 의 kind: expr 에서 __이름__ 으로 호출) ──────────────────
def _gini(x, w):
    x = np.asarray(x, float); w = np.asarray(w, float)
    m = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[m], w[m]
    if len(x) < 2: return np.nan
    o = np.argsort(x); x, w = x[o], w[o]
    cw = np.cumsum(w); cxw = np.cumsum(x * w)
    if cxw[-1] <= 0: return np.nan
    return float(1 - np.sum((cxw[:-1] + cxw[1:]) * np.diff(cw)) / (cxw[-1] * cw[-1]))


def _eq(df, col):
    """균등화 가구소득 = 가구합 / sqrt(가구원수)"""
    if col not in df.columns or 'hid' not in df.columns: return None
    h = df.groupby('hid')[col].transform('sum')
    return h / np.sqrt(df['hnum'].clip(lower=1))


def _pov(df, col, mask=None):
    e = _eq(df, col)
    if e is None: return np.nan
    w = df['indwgt'] if 'indwgt' in df.columns else pd.Series(1.0, index=df.index)
    med = _wq(e, w, 0.5)
    poor = e < 0.5 * med
    if mask is not None: 
        if mask.sum() == 0: return np.nan
        return float((poor[mask] * w[mask]).sum() / w[mask].sum())
    return float((poor * w).sum() / w.sum())


def _wq(x, w, q):
    x = np.asarray(x, float); w = np.asarray(w, float)
    m = np.isfinite(x) & np.isfinite(w)
    x, w = x[m], w[m]
    o = np.argsort(x); x, w = x[o], w[o]
    c = np.cumsum(w) / w.sum()
    return float(np.interp(q, c, x))


def _hh_any(df, cols, wcol='hhwgt'):
    """가구 내 **누구라도** 해당 급여를 받으면 그 가구를 수급가구로 센다.
    급여가 개인(아동·수급자)에게 귀속되므로 가구주 행만 보면 0 이 나온다."""
    cols = [c for c in cols if c in df.columns]
    if not cols or 'hid' not in df.columns: return np.nan
    any_p = (df[cols].fillna(0) == 1).any(axis=1).astype(int)
    hh = df.assign(_a=any_p).groupby('hid').agg(a=('_a', 'max'), w=(wcol, 'first'))
    return float((hh['a'] * hh['w']).sum() / hh['w'].sum())


CHILD_BEN = ['childbn_yn1', 'carebn_yn1', 'carebn_dischild_yn1', 'carebn_rural_yn1',
             'infantbn_yn1', 'childcare_yn1']
NBLS_BEN = ['nbls_live_yn1', 'nbls_medi_yn1', 'nbls_house_yn1', 'nbls_edu_yn1']


def derived(df, name):
    w = df['indwgt'] if 'indwgt' in df.columns else pd.Series(1.0, index=df.index)
    if name == 'gini_disp':
        e = _eq(df, 'p_dinc');  return _gini(e, w) if e is not None else np.nan
    if name == 'gini_market':
        e = _eq(df, 'p_minc');  return _gini(e, w) if e is not None else np.nan
    if name == 'poverty_disp_all':   return _pov(df, 'p_dinc')
    if name == 'poverty_disp_65':    return _pov(df, 'p_dinc', df['age'] >= 65)
    if name == 'poverty_disp_017':   return _pov(df, 'p_dinc', df['age'] <= 17)
    if name == 'poverty_disp_1864':  return _pov(df, 'p_dinc', (df['age'] >= 18) & (df['age'] <= 64))
    if name == 'poverty_market_all': return _pov(df, 'p_minc')
    if name == 'poverty_market_65':  return _pov(df, 'p_minc', df['age'] >= 65)
    if name == 'hh_rate_child_benefit': return _hh_any(df, CHILD_BEN)
    if name == 'hh_rate_nbls':           return _hh_any(df, NBLS_BEN)
    if name == 'median_eq_disp':
        e = _eq(df, 'p_dinc');  return _wq(e, w, 0.5) if e is not None else np.nan
    if name == 'median_eq_market':
        e = _eq(df, 'p_minc');  return _wq(e, w, 0.5) if e is not None else np.nan
    # [T7-c] 노인 가구유형별 빈곤율 (S0 R02 <표 4-7>): pov65_{alone|only|mix}_{m|d}
    if name.startswith('pov65_'):
        _, grp, inc = name.split('_')
        e = _eq(df, 'p_minc' if inc == 'm' else 'p_dinc')
        poor = e < 0.5 * _wq(e, w, 0.5)
        n65 = df.groupby('hid')['age'].transform(lambda s: int((s >= 65).sum()))
        hn = df['hnum']
        g = {'alone': hn == 1, 'only': (hn > 1) & (n65 == hn), 'mix': n65 < hn}[grp] & (df['age'] >= 65)
        return float((poor[g] * w[g]).sum() / w[g].sum()) if g.any() else np.nan
    # [T7-d] 연령별 세대구성 거주 비중 (KOSIS 101/DT_1IN1509): la_{u15|o65}_{유형}
    if name.startswith('la_'):
        _, ag, typ = name.split('_', 2)
        m = (df['age'] < 15) if ag == 'u15' else (df['age'] >= 65)
        t = df['_hhtype'] == {'couplechild': 'couple_child', 'oneparent': 'oneparent_child',
                              'grand': 'grandparent_child', 'threegen': 'threegen',
                              'single': 'single', 'couple': 'couple'}[typ]
        return float(w[m & t].sum() / w[m].sum())
    # [T7-e] 일차소득 빈곤율 — 가처분소득 빈곤선 적용 (S0 R01 <표 2-38> 주5)
    if name == 'poverty_market_all_dline':
        em, ed = _eq(df, 'p_minc'), _eq(df, 'p_dinc')
        return float(((em < 0.5 * _wq(ed, w, 0.5)) * w).sum() / w.sum())
    raise KeyError(f'미정의 파생지표 {name}')


class _ScalarExpr(Exception):
    """expr 이 스칼라(이미 가중 비율)를 반환할 때 alt 표기를 전달하는 신호."""


def eval_target(df, t):
    """t: {name, kind: rate|mean|share|count, expr, group, target, tol, tol_kind: pp|rel, source}"""
    kind, expr = t.get('kind', 'rate'), t.get('expr', '')
    try:
        sub = df.query(t['filter']) if t.get('filter') else df
        if kind == 'expr':
            got = float(derived(sub, expr.strip('_')))
        elif kind == 'wrate':
            # 모집단 비율 = 가중 평균. R01/R02·원기관 공표 비율은 모두 모집단 비율이므로
            # 불균등 가중 표본에서는 반드시 가중해야 한다 (비가중은 구조적으로 어긋난다).
            _m = pd.eval(expr, local_dict={'df': sub}).astype(float)
            _w = sub['indwgt'] if t.get('unit', 'person') == 'person' else sub['hhwgt']
            got = float((_m * _w).sum() / _w.sum())
        elif kind == 'rate':
            got = float(pd.eval(expr, local_dict={'df': sub}).mean())
        elif kind == 'wmean':
            # 모집단 평균 = 가중 평균. 목표값이 "공표 총액 ÷ 공표 인원" 처럼 두 모집단
            # 총계의 비(比)로 정의돼 있으면, 그 모수의 표본추정량은 Σ(w·y)/Σw 다.
            # 비가중 표본평균은 **다른 모수**를 추정하므로 구조적으로 어긋난다.
            _v = pd.eval(expr, local_dict={'df': sub}).astype(float)
            _w = sub['indwgt'] if t.get('unit', 'person') == 'person' else sub['hhwgt']
            _m = np.isfinite(_v) & np.isfinite(_w)
            got = float((_v[_m] * _w[_m]).sum() / _w[_m].sum())
        elif kind == 'mean':
            got = float(pd.eval(expr, local_dict={'df': sub}).mean())
        elif kind == 'count':
            got = float(pd.eval(expr, local_dict={'df': sub}).sum())
        elif kind == 'wcount':   # 가중 추정 모집단 규모
            w = sub['indwgt'] if t.get('unit', 'person') == 'person' else sub['hhwgt']
            got = float((pd.eval(expr, local_dict={'df': sub}).astype(float) * w).sum())
        else:
            got = float(pd.eval(expr, local_dict={'df': sub}))
    except Exception as e:
        return {'name': t['name'], 'target': t.get('target'), 'got': None,
                'pass': None, 'err': f'{type(e).__name__}: {e}', 'source': t.get('source', '')}
    tgt = float(t['target']); tol = float(t.get('tol', 0.03))
    if t.get('tol_kind', 'pp') == 'pp':
        ok = abs(got - tgt) <= tol
        dev = f'{(got-tgt)*100:+.2f}%p'
    else:
        ok = (abs(got - tgt) / max(abs(tgt), 1e-9)) <= tol
        dev = f'{(got-tgt)/max(abs(tgt),1e-9)*100:+.1f}%'
    # ── 비가중·가중 병기 (alt) ────────────────────────────────────────────────
    #   비율·평균 목표는 "무엇의 비율/평균인가"에 따라 추정량이 달라진다.
    #   본 표본은 자기가중이 아니므로 두 값이 갈리고, **모집단 비율·평균 목표는 가중이 맞다.**
    #   판정에 실제로 쓴 쪽(kind)에 ← 표시를 붙여 리포트에 그대로 노출한다.
    alt = ''
    try:
        if kind in ('rate', 'wrate', 'mean', 'wmean'):
            _m = pd.eval(expr, local_dict={'df': sub})
            _w = sub['indwgt'] if t.get('unit', 'person') == 'person' else sub['hhwgt']
            if np.ndim(_m) == 0:
                # expr 자체가 Σ(w·x)/Σw 를 계산하는 스칼라 식 (wrate 의 항등식 용법).
                # 대응하는 비가중 값이 식에 존재하지 않으므로 그 사실을 그대로 적는다.
                _fs = (lambda v: f'{v*100:.2f}%') if t.get('tol_kind', 'pp') == 'pp' else \
                      (lambda v: f'{v:,.0f}' if abs(v) >= 1e4 else f'{v:,.4g}')
                raise _ScalarExpr(f'가중 {_fs(float(_m))} ←판정 (식 자체가 Σ(w·x)/Σw — 비가중 대응값 없음)')
            _m = _m.astype(float)
            _ok = np.isfinite(_m) & np.isfinite(_w)
            _wv = float((_m[_ok] * _w[_ok]).sum() / _w[_ok].sum()); _uv = float(_m[_ok].mean())
            _f = (lambda v: f'{v*100:.2f}%') if t.get('tol_kind', 'pp') == 'pp' else \
                 (lambda v: f'{v:,.0f}' if abs(v) >= 1e4 else f'{v:,.4g}')
            _u_mark = ' ←판정' if kind in ('rate', 'mean') else ''
            _w_mark = ' ←판정' if kind in ('wrate', 'wmean') else ''
            _wu = '가구' if t.get('unit', 'person') == 'household' else '개인'
            alt = f'비가중 {_f(_uv)}{_u_mark} / 가중({_wu}) {_f(_wv)}{_w_mark}'
    except _ScalarExpr as e:
        alt = str(e)
    except Exception:
        pass
    return {'name': t['name'], 'grade': t.get('grade', ''), 'target': tgt, 'got': got, 'alt': alt,
            'dev': dev, 'tol': f"{tol}{'pp' if t.get('tol_kind','pp')=='pp' else ' rel'}",
            'pass': bool(ok), 'source': t.get('source', ''), 'err': ''}

def null_pattern(df, cb):
    rows = []
    for c in df.columns:
        s = df[c]
        rows.append({'var': c, 'n_null': int(s.isna().sum()),
                     'pct_null': round(100 * s.isna().mean(), 2),
                     'scope': (cb.get(c, {}) or {}).get('scope', '')[:110]})
    return pd.DataFrame(rows).sort_values('pct_null', ascending=False)

def summary_stats(df):
    rows = []
    for c in df.columns:
        s = df[c]
        r = {'var': c, 'dtype': str(s.dtype), 'n': int(s.notna().sum())}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            q = s.dropna()
            r.update(mean=round(float(q.mean()), 2), std=round(float(q.std()), 2),
                     p25=float(q.quantile(.25)), p50=float(q.quantile(.5)),
                     p75=float(q.quantile(.75)), min=float(q.min()), max=float(q.max()),
                     nuniq=int(q.nunique()))
        rows.append(r)
    return pd.DataFrame(rows)

def _tbl(df, cls=''):
    return df.to_html(index=False, escape=True, border=0, na_rep='',
                      classes=('tbl ' + cls).strip())

def coverage(df, cb):
    """생성 커버리지: Tier1+2 595변수 중 몇 개 생성했는지 + 주장지위 분포.
    '값 있음' = 컬럼이 있고 전량 NULL 이 아닌 변수. '전량 NULL' 은 표본 규모 미달·파라미터 미확정."""
    import yaml as _y, glob as _g
    blocks = json.load(open('registry/blocks.json', encoding='utf-8')) if os.path.exists('registry/blocks.json') else []
    tier12 = {v for b in blocks for v in b['vars']}
    stat = {}
    for f in sorted(_g.glob('params/*.yaml')):
        d = _y.safe_load(open(f, encoding='utf-8')) or {}
        for var, pspec in (d.get('params') or {}).items():
            stat[var] = str((pspec or {}).get('status', '미확인'))
    rows = []
    for b in sorted(blocks, key=lambda x: (x['order'], x['agent'], x['block'])):
        have = [v for v in b['vars'] if v in df.columns]
        nulls = [v for v in have if df[v].isna().all()]
        good = [v for v in have if v not in nulls]
        miss = [v for v in b['vars'] if v not in df.columns]
        st = pd.Series([stat.get(v, '미기재') for v in good]).value_counts().to_dict()
        rows.append({'블록': b['block'], '담당': b['agent'], 'order': b['order'], '제목': b['title'][:36],
                     '선언변수': len(b['vars']), '값 있음': len(good), '전량 NULL': len(nulls),
                     '미생성': len(miss),
                     '1차확인': st.get('1차확인', 0), '논리적추론': st.get('논리적추론', 0),
                     '가정': st.get('가정', 0), '미확인': st.get('미확인', 0),
                     '미생성 변수': ', '.join(miss)[:120],
                     '전량 NULL 변수': ', '.join(nulls)[:160]})
    t = pd.DataFrame(rows)
    num = ['선언변수', '값 있음', '전량 NULL', '미생성', '1차확인', '논리적추론', '가정', '미확인']
    total = {'블록': '합계', '담당': '', 'order': '', '제목': f'Tier1+2 {len(tier12)}변수',
             '미생성 변수': '', '전량 NULL 변수': ''}
    total.update({c: int(t[c].sum()) for c in num})
    return pd.concat([t, pd.DataFrame([total])], ignore_index=True)


def marginal_fit(df):
    """주변분포 적합: 성×10세 연령대 (가중) vs 주민등록 2022.11"""
    f = 'params/raw/POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'
    if not (os.path.exists(f) and 'indwgt' in df.columns): return None
    p = pd.read_csv(f)
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['sex_c'] = np.where(p.sex == 'male', 1, 2)
    p['band'] = np.minimum((p.age // 10) * 10, 90)
    tgt = p.groupby(['sex_c', 'band'])['pop'].sum()
    tgt = tgt / tgt.sum() * 100
    b = np.minimum((df['age'] // 10) * 10, 90)
    got = df.groupby([df['gender'].astype(int), b])['indwgt'].sum()
    got = got / got.sum() * 100
    idx = tgt.index
    return pd.DataFrame({
        '성': ['남성' if i[0] == 1 else '여성' for i in idx],
        '연령대': [f'{i[1]}~{i[1]+9}세' if i[1] < 90 else '90세+' for i in idx],
        '모집단%': tgt.round(2).values,
        '표본가중%': [round(float(got.get(i, 0)), 2) for i in idx],
    }).assign(**{'차이(%p)': lambda d: (d['표본가중%'] - d['모집단%']).round(2)})




# ══════════════════════════════════════════════════════════════════════════════
# ③ S0 캘리브레이션 — R01(2020, 1기) / R02(2021, 2기) 대비 재현오차 + 연도차 주석
#    근거: registry/s0_basis_finding.md  (지시서 v2 의 "R01=2021·R02=2022" 전제는 오류)
# ══════════════════════════════════════════════════════════════════════════════
S0_BASIS = {                     # targets 파일 → (보고서코드, 기준연도, 기(期))
    'S0_core.yaml':     ('R01', 2020, '1기'),
    'S0_R02_2021.yaml': ('R02', 2021, '2기'),
}
YEAR_NOTE = {
    2020: '(c) 연도차 2년 — R01 2020년(1기) 기준 vs 본 데이터 2022년. '
          '영아수당 신설(2022)·기초연금 기준연금액 인상·물가·인구고령화 미반영.',
    2021: '(c) 연도차 1년 — R02 2021년(2기) 기준 vs 본 데이터 2022년. '
          '급여 확대·물가 상승분 미반영.',
}
# 자산조사형 급여 = 시설거주자 제외 효과가 큰 항목 (s0_basis_finding.md §3)
MEANS_TESTED = ('생계급여', '의료급여', '주거급여', '교육급여', '기초연금', '기초생활', '기초보장')


def _s0_basis(t):
    f = t.get('file', '')
    if f in S0_BASIS: return S0_BASIS[f]
    s = f"{t.get('source','')} {t.get('name','')}"
    if 'R02' in s: return ('R02', 2021, '2기')
    if 'R01' in s: return ('R01', 2020, '1기')
    return ('S0', None, '')


def _fmt(v, tol_kind):
    """tol_kind='pp' 이면 비율(%) 표기, 'rel' 이면 실수·금액 표기."""
    if v is None: return ''
    try: v = float(v)
    except (TypeError, ValueError): return str(v)
    if not np.isfinite(v): return ''
    if tol_kind == 'pp': return f'{v*100:.2f}%'
    if abs(v) >= 1e4: return f'{v:,.0f}'
    return f'{v:,.4g}'


def _verdict(p):
    return '✅ 통과' if p is True else ('❌ 이탈' if p is False else '⚠ 평가불가')


def s0_calibration(tg, res):
    """S0 등급 목표 전량 — 항목별 재현오차와 연도차·표본 주석."""
    rows = []
    for t, r in zip(tg, res):
        if t.get('grade') != 'S0': continue
        code, yr, gen = _s0_basis(t)
        tk = t.get('tol_kind', 'pp')
        note = YEAR_NOTE.get(yr, '기준연도 미표기 — 출처 확인 필요')
        if any(k in t.get('name', '') for k in MEANS_TESTED):
            note += ' / (d) 일반가구 표본 — 시설거주자 제외로 정부공표보다 수급률이 낮은 것이 정상.'
        if t.get('note'):
            note += ' ▸ ' + str(t['note'])[:400]
        rows.append({
            '항목': t['name'], 'S0 기준': f'{code}({yr}, {gen})' if yr else code,
            '기준연도': yr or '', '목표(S0)': _fmt(t.get('target'), tk),
            '재현값': _fmt(r.get('got'), tk), '비가중 / 가중 (병기)': r.get('alt', ''),
            '재현오차': r.get('dev', ''),
            '허용': r.get('tol', ''), '판정': _verdict(r.get('pass')),
            '연도차·표본 주석': note, '출처': t.get('source', ''),
        })
    d = pd.DataFrame(rows)
    if len(d): d = d.sort_values(['기준연도', '판정', '항목'], ascending=[False, True, True])
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ④ S1 총량표 — 급여별 가중 추정 vs 원기관 2022 집계
# ══════════════════════════════════════════════════════════════════════════════
_UNIT_LABEL = {'wcount': {'person': '명(가중 추정 모집단)', 'household': '가구(가중 추정)'},
               'rate': '비율(비가중)', 'wrate': '비율(가중)', 'mean': '평균(비가중)',
               'wmean': '평균(가중)', 'count': '표본 수', 'expr': '파생지표(가중)'}


def s1_totals(tg, res):
    rows = []
    for t, r in zip(tg, res):
        if t.get('grade') != 'S1': continue
        k, tk = t.get('kind', 'rate'), t.get('tol_kind', 'pp')
        u = _UNIT_LABEL['wcount'].get(t.get('unit', 'person'), '') if k == 'wcount' else _UNIT_LABEL.get(k, '')
        tgt, got = t.get('target'), r.get('got')
        try:
            rel = (float(got) - float(tgt)) / max(abs(float(tgt)), 1e-9)
            rel_s = f'{rel*100:+.1f}%'
        except (TypeError, ValueError):
            rel_s = ''
        rows.append({
            '급여·지표': t['name'], '단위': u,
            '원기관 2022 집계(목표)': _fmt(tgt, tk), '가중 추정': _fmt(got, tk),
            '비가중 / 가중 (병기)': r.get('alt', ''),
            '상대오차': rel_s, '표기편차': r.get('dev', ''), '허용': r.get('tol', ''),
            '판정': _verdict(r.get('pass')), '출처': t.get('source', ''),
        })
    d = pd.DataFrame(rows)
    if len(d):
        d['_o'] = d['단위'].str.startswith('명').map({True: 0, False: 1})
        d = d.sort_values(['_o', '판정', '급여·지표']).drop(columns='_o')
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ⑥ 주변분포 적합 — 성×5세×시도 인구 · 가구원수 · 지니·상대빈곤율
# ══════════════════════════════════════════════════════════════════════════════
_MOIS = 'params/raw/POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'
_CENSUS_HH = 'params/raw/POPUL_CENSUS05_T5_sido_hhtype_hhsize.csv'


def _mois(level):
    if not os.path.exists(_MOIS): return None
    p = pd.read_csv(_MOIS)
    p = p[(p.level == level) & (p.sex.isin(['male', 'female']))].copy()
    return p if len(p) else None


def marginal_age_sex(df, width=5, cap=85):
    """성 × 5세 연령대 (주민등록 2022.11 시군구×1세×성 원자료 집계)."""
    p = _mois('sigungu')
    if p is None or 'indwgt' not in df.columns: return None
    p['sex_c'] = np.where(p.sex == 'male', 1, 2)
    p['band'] = np.minimum((p.age // width) * width, cap)
    tgt = p.groupby(['sex_c', 'band'])['pop'].sum()
    tgt = tgt / tgt.sum() * 100
    b = np.minimum((df['age'] // width) * width, cap)
    got = df.groupby([df['gender'].astype(int), b])['indwgt'].sum()
    got = got / got.sum() * 100
    idx = tgt.index
    lab = lambda a: f'{a}~{a+width-1}세' if a < cap else f'{cap}세+'
    d = pd.DataFrame({'성': ['남성' if i[0] == 1 else '여성' for i in idx],
                      '연령대': [lab(i[1]) for i in idx],
                      '모집단%': tgt.round(3).values,
                      '표본가중%': [round(float(got.get(i, 0.0)), 3) for i in idx]})
    d['차이(%p)'] = (d['표본가중%'] - d['모집단%']).round(3)
    return d


def marginal_sido(df):
    """시도(17) 인구 구성비."""
    p = _mois('sido')
    if p is None or 'sido' not in df.columns or 'indwgt' not in df.columns: return None
    nm = p.drop_duplicates('sido').set_index('sido')['sido_name'].to_dict()
    tgt = p.groupby('sido')['pop'].sum(); tgt = tgt / tgt.sum() * 100
    got = df.groupby(df['sido'].astype(int))['indwgt'].sum(); got = got / got.sum() * 100
    d = pd.DataFrame({'시도': [f'{i} {nm.get(i,"")}' for i in tgt.index],
                      '모집단%': tgt.round(3).values,
                      '표본가중%': [round(float(got.get(i, 0.0)), 3) for i in tgt.index]})
    d['차이(%p)'] = (d['표본가중%'] - d['모집단%']).round(3)
    return d


def marginal_hhsize(df):
    """가구원수 (2022 등록센서스 일반가구 21,773,507 기준)."""
    if not os.path.exists(_CENSUS_HH) or 'hnum' not in df.columns: return None
    d0 = pd.read_csv(_CENSUS_HH)
    n = d0[d0.level == 'nation'].set_index('item')['households']
    m = {'ord_hh_1p': 1, 'ord_hh_2p': 2, 'ord_hh_3p': 3, 'ord_hh_4p': 4, 'ord_hh_5p_plus': 5}
    if not set(m).issubset(n.index): return None
    tgt = pd.Series({v: float(n[k]) for k, v in m.items()})
    tgt = tgt / tgt.sum() * 100
    hh = df[df['head'] == 1]
    sz = np.minimum(hh['hnum'].astype(int), 5)
    w = hh['hhwgt'] if 'hhwgt' in hh.columns else pd.Series(1.0, index=hh.index)
    got = w.groupby(sz).sum(); got = got / got.sum() * 100
    cnt = sz.value_counts().sort_index()
    lab = {1: '1인', 2: '2인', 3: '3인', 4: '4인', 5: '5인 이상'}
    d = pd.DataFrame({'가구원수': [lab[i] for i in tgt.index],
                      '모집단%': tgt.round(3).values,
                      '표본가중%': [round(float(got.get(i, 0.0)), 3) for i in tgt.index],
                      '표본가구수': [int(cnt.get(i, 0)) for i in tgt.index]})
    d['차이(%p)'] = (d['표본가중%'] - d['모집단%']).round(3)
    return d


_CENSUS_HHTYPE = 'params/raw/POPUL_CENSUS_PR_T22_hhtype_nation_2022.csv'
_HHPROJ_HHTYPE = 'params/raw/POPUL_HHPROJ_T2_hhtype_2022.csv'

# B01 `_hhtype` → 2022 장래가구추계 <표2> 가구유형. 「기타(친족)」는 B01 이 부부+부모
# (`couple_parent`)·조손(`grandparent_child`) 두 형태로만 표현하므로 둘을 묶어 대조한다.
_HHTYPE_MAP = {'single': '1인가구', 'couple': '부부', 'couple_child': '부부+자녀',
               'oneparent_child': '부(모)+자녀', 'threegen': '3세대이상',
               'couple_parent': '기타(친족)', 'grandparent_child': '기타(친족)',
               'nonrel': '비친족가구'}
_HHTYPE_ORDER = ['1인가구', '부부', '부부+자녀', '부(모)+자녀', '3세대이상', '기타(친족)', '비친족가구']


def marginal_hhtype(df):
    """세대구성(가구유형) 주변분포 — 2022 장래가구추계 <표2> [1차확인].
    등록센서스 보도자료 <표22>(1인 34.45% · 3세대이상 3.06% · 비친족 2.36%)와
    세 항목이 모두 일치하므로 두 출처를 함께 싣는다.
    ※ B01 의 세대구성 템플릿 확률은 `[가정 A1-1]` 이며 이 주변분포에 적합되어 있지 않다."""
    if not os.path.exists(_HHPROJ_HHTYPE) or '_hhtype' not in df.columns: return None
    pr = pd.read_csv(_HHPROJ_HHTYPE)
    tgt = {}
    for nm, sh in zip(pr['가구유형'].astype(str), pr['share_pct'].astype(float)):
        nm = nm.strip()
        if nm in ('부+자녀', '모+자녀'):
            tgt['부(모)+자녀'] = tgt.get('부(모)+자녀', 0.0) + sh
        elif nm == '기타':
            tgt['기타(친족)'] = tgt.get('기타(친족)', 0.0) + sh
        elif nm in _HHTYPE_ORDER:
            tgt[nm] = tgt.get(nm, 0.0) + sh
    if not tgt: return None
    cen = {}
    if os.path.exists(_CENSUS_HHTYPE):
        c = pd.read_csv(_CENSUS_HHTYPE).set_index('item')['value']
        if 'ordinary_households' in c.index:
            t = float(c['ordinary_households'])
            cen = {'1인가구': 100 * float(c.get('one_person_households', np.nan)) / t,
                   '3세대이상': 100 * float(c.get('family_3gen_plus', np.nan)) / t,
                   '비친족가구': 100 * float(c.get('nonfamily_households', np.nan)) / t}
    hh = df[df['head'] == 1]
    w = hh['hhwgt'] if 'hhwgt' in hh.columns else pd.Series(1.0, index=hh.index)
    grp = hh['_hhtype'].map(_HHTYPE_MAP)
    got = w.groupby(grp).sum(); got = got / got.sum() * 100
    cnt = grp.value_counts()
    rows = []
    for k in _HHTYPE_ORDER:
        gv, tv = float(got.get(k, 0.0)), float(tgt.get(k, np.nan))
        rows.append({'가구유형(세대구성)': k,
                     '모집단%(장래가구추계 표2)': round(tv, 2),
                     '모집단%(등록센서스 표22)': (round(cen[k], 2) if k in cen else ''),
                     '표본가중%': round(gv, 2), '표본가구수': int(cnt.get(k, 0)),
                     '차이(%p)': round(gv - tv, 2),
                     '배수': (round(gv / tv, 3) if tv else '')})
    return pd.DataFrame(rows)


DIST_IND = [
    ('gini_disp',        '지니계수 — 균등화 가구가처분소득', 'pp'),
    ('gini_market',      '지니계수 — 균등화 가구일차소득',   'pp'),
    ('poverty_disp_all', '상대빈곤율 — 가처분소득 (전인구)', 'pp'),
    ('poverty_disp_65',  '상대빈곤율 — 가처분소득 (65세+)',  'pp'),
    ('poverty_disp_017', '상대빈곤율 — 가처분소득 (0~17세)', 'pp'),
    ('poverty_disp_1864','상대빈곤율 — 가처분소득 (18~64세)','pp'),
    ('poverty_market_all','상대빈곤율 — 일차소득 (전인구)',  'pp'),
    ('poverty_market_65','상대빈곤율 — 일차소득 (65세+)',    'pp'),
    ('median_eq_disp',   '균등화 가구가처분소득 중윗값(원)', 'rel'),
    ('median_eq_market', '균등화 가구일차소득 중윗값(원)',   'rel'),
]


def dist_indicators(df, tg, res):
    """지니·상대빈곤율 등 분포지표: 재현값 + (있으면) S0 목표 대비 편차."""
    byname = {}
    for t, r in zip(tg, res):
        if t.get('kind') == 'expr' and not t.get('filter'):
            byname.setdefault(str(t.get('expr', '')).strip('_'), (t, r))
    rows = []
    for key, label, tk in DIST_IND:
        try:
            got = float(derived(df, key))
        except Exception:
            got = np.nan
        t, r = byname.get(key, ({}, {}))
        rows.append({'지표': label, '재현값': _fmt(got, tk),
                     '목표(S0)': _fmt(t.get('target'), tk) if t else '—',
                     '편차': r.get('dev', '') if t else '',
                     '허용': r.get('tol', '') if t else '',
                     '판정': _verdict(r.get('pass')) if t else '(목표 없음)',
                     '출처': t.get('source', '') if t else ''})
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# ⑧ NULL 패턴 = 추출대상 정의 일치 여부
# ══════════════════════════════════════════════════════════════════════════════
_FULL_KEYS = ('일반가구 및 일반가구원', '일반가구원')
_COND_KEYS = ('집단', '한 번이라도', '한번이라도', '1일 이상', '1일이라도', '등록장애인', '부과된',
              '참여자', '수급권을 가진', '수급권자', '납부예외자', '신청자', '계약 건', '가입자',
              '수급자', '이용자', '지원받은', '신청한')
# 코드북 "변수 내용" 이 "…했으면 1" 형식이면 전 표본에 대한 0/1 지시변수 → NULL 이 없는 것이 정상
_IND_PAT = re.compile(r'(했으면|하면|받았으면|있으면|되면|이면)\s*1')


def scope_kind(scope):
    """코드북 '추출대상' 문구 → 전수형 / 조건부형 / 기타 분류."""
    s = (scope or '').replace('\n', ' ')
    if not s.strip(): return '미기재'
    if '무정보 사례 0원' in s: return '전수(0원 처리)'
    if any(k in s for k in _COND_KEYS): return '조건부'
    if any(k in s for k in _FULL_KEYS): return '전수'
    return '기타'


def _param_status():
    """params/*.yaml 의 변수별 주장지위·비고 (전량 NULL 사유 설명에 쓴다)."""
    import glob as _g
    out = {}
    for f in sorted(_g.glob('params/*.yaml')):
        try:
            d = yaml.safe_load(open(f, encoding='utf-8')) or {}
        except Exception:
            continue
        for var, p in (d.get('params') or {}).items():
            p = p or {}
            out[var] = (str(p.get('status', '')), str(p.get('note', '') or '').replace('\n', ' '))
    return out


def null_scope_check(df, cb):
    """변수별 NULL 비율이 코드북 추출대상 정의와 정합한지 기계 점검.
    ① 전수형 → NULL 0% 이어야 함  ② 조건부형 → 0% < NULL < 100%
    ③ X_yn2/_dur/_amt/_type 의 관측집합 ⊆ {X_yn1==1}
    ※ 코드북 '변수 내용'이 "…했으면 1" 형식인 0/1 지시변수는 전수 관측이 정상이다."""
    PS = _param_status()
    rows = []
    for c in [x for x in df.columns if not x.startswith('_')]:
        s = df[c]
        v = cb.get(c, {}) or {}
        scope = (v.get('scope', '') or '').replace('\n', ' ')
        content = (v.get('content', '') or '').replace('\n', ' ')
        kind = scope_kind(scope)
        is_ind = bool(_IND_PAT.search(content))
        nn, pn = int(s.notna().sum()), float(s.isna().mean() * 100)
        chk, bad, verdict, rem = [], 0, '✅ 일치', ''
        st, note = PS.get(c, ('', ''))
        if nn == 0:
            verdict = '⚠ 전량 NULL(미생성)'
            rem = (f'주장지위 {st or "미기재"} — ' if st else '') + \
                  ('표본 규모 미달(기대 수급자 <1명) 또는 파라미터 미확정. report/assumptions.md 참조. '
                   + note[:160])
        else:
            if kind.startswith('전수'):
                chk.append('전수형 → NULL 0%')
                if pn > 0:
                    bad = int(s.isna().sum()); verdict = '❌ 전수형인데 NULL 존재'
                    rem = '추출대상이 2022.11.1 일반가구·일반가구원 전원인데 결측이 있다'
            elif kind == '조건부':
                chk.append('조건부형 → 부분 NULL')
                if pn == 0:
                    if is_ind:
                        verdict = '✅ 일치(0/1 지시변수)'
                        rem = '코드북 변수 내용이 "…했으면 1" 형식의 전수 0/1 지시변수 → NULL 없음이 정상'
                    else:
                        verdict = '⚠ 조건부인데 전수 관측'
                        rem = ('추출대상은 특정 집단인데 전 표본에 값이 있다 — '
                               '제도상 전 국민을 포괄하는 변수인지 확인 필요')
            else:
                chk.append('추출대상 문구 자동분류 불가 → 판정 보류')
                verdict = '· 판정보류'
            base = None
            for suf in ('_yn2', '_dur', '_amt', '_type'):
                if c.endswith(suf) and (c[:-len(suf)] + '_yn1') in df.columns:
                    base = c[:-len(suf)] + '_yn1'; break
            if base is not None:
                chk.append(f'관측집합 ⊆ {{{base}=1}}')
                v2 = int((s.notna() & (df[base].fillna(0) != 1)).sum())
                if v2:
                    bad += v2; verdict = '❌ yn1 밖 관측'
                    rem = f'{base}=1 이 아닌 행에 값이 있다'
        rows.append({'변수': c, '변수명(한글)': v.get('name_ko', ''),
                     '추출대상 유형': kind, '관측(비NULL)': nn, 'NULL%': round(pn, 2),
                     '적용 점검': ' · '.join(chk) or '(점검 없음)',
                     '불일치 건수': bad, '판정': verdict, '비고': rem[:260],
                     '추출대상(코드북)': scope[:150]})
    d = pd.DataFrame(rows)
    order = {'❌ 전수형인데 NULL 존재': 0, '❌ yn1 밖 관측': 0, '⚠ 조건부인데 전수 관측': 1,
             '⚠ 전량 NULL(미생성)': 2, '· 판정보류': 3, '✅ 일치(0/1 지시변수)': 4, '✅ 일치': 5}
    d['_o'] = d['판정'].map(order).fillna(6)
    return d.sort_values(['_o', '변수']).drop(columns='_o')


# ══════════════════════════════════════════════════════════════════════════════
# ⑨ seed 재현성 — 동일 seed 로 2회 생성해 완전 동일한지 실제 실행 확인
# ══════════════════════════════════════════════════════════════════════════════
def seed_repro(n_hh=4200, df_ref=None):
    """파이프라인을 처음부터 2회 재실행해 결과가 완전히 같은지 확인한다."""
    import importlib
    import pipeline
    importlib.reload(pipeline)
    out = {'실행': 2, 'n_hh': n_hh}
    try:
        a, la, _ = pipeline.run(n_hh=n_hh, verbose=False)
        b, lb, _ = pipeline.run(n_hh=n_hh, verbose=False)
    except Exception as e:
        return pd.DataFrame([{'점검': '2회 재실행', '결과': f'실행 실패: {type(e).__name__}: {e}'}])
    rows = [{'점검': 'seed 규칙', '결과': 'numpy PCG64 · seed = 20220000 + 블록번호 (core.rng), '
                                        'np.random 전역 사용 금지 (§4.1)'},
            {'점검': '재실행 횟수', '결과': f'{n_hh}가구로 파이프라인 전체를 2회 독립 실행'},
            {'점검': '블록 상태', '결과': f"1회차 OK {int((la.status=='OK').sum())}/{len(la)} · "
                                        f"2회차 OK {int((lb.status=='OK').sum())}/{len(lb)}"},
            {'점검': '행·열', '결과': f'1회차 {len(a):,}×{len(a.columns):,} · 2회차 {len(b):,}×{len(b.columns):,}'}]
    same_cols = list(a.columns) == list(b.columns)
    rows.append({'점검': '컬럼 순서·목록', '결과': '완전 동일' if same_cols else '❌ 불일치'})
    diff = []
    if same_cols and len(a) == len(b):
        for c in a.columns:
            if not a[c].equals(b[c]): diff.append(c)
    eq = bool(same_cols and len(a) == len(b) and not diff)
    rows.append({'점검': '전 컬럼 값 일치', '결과': ('✅ 2회 결과 완전 동일 (bit-identical)'
                                                 if eq else f'❌ 불일치 컬럼 {len(diff)}개: ' + ', '.join(diff[:15]))})
    if df_ref is not None:
        try:
            same_ref = (list(df_ref.columns) == list(a.columns) and len(df_ref) == len(a)
                        and not [c for c in a.columns if not df_ref[c].equals(a[c])])
        except Exception:
            same_ref = False
        rows.append({'점검': '리포트 대상 데이터와 일치',
                     '결과': '✅ 동일' if same_ref else '⚠ 리포트 df 와 재실행 결과가 다름 (파라미터 수정 중일 수 있음)'})
    out['equal'] = eq
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# 리포트 조립
# ══════════════════════════════════════════════════════════════════════════════
CAVEATS = [
    ('가중치 없이 쓰면 안 된다',
     '표본은 가구수 비례(PPS) 추출이다. 모수 추정에는 반드시 <code>indwgt</code>(개인) 또는 '
     '<code>hhwgt</code>(가구, 가구주 행)를 써야 한다.'),
    ('시군구 단위 분석은 불가능하다',
     '표본 가구가 5개 이하인 시군구가 다수다. 분석 가능한 지역 단위는 <code>sido</code>(17개)까지다.'),
    ('시설거주 수급자가 빠져 있다',
     '원 사회보장행정데이터가 등록센서스 <b>일반가구</b> 표본이라 시설거주자가 제외된다. '
     '생계·의료급여·기초연금 등 자산조사형 급여의 수급률은 정부 공표 총량보다 낮은 것이 정상이다. '
     '(R02 &lt;표 2-20&gt;: 생계급여 수급자 비율 행정데이터 2.53% vs 정부공표 2.88%, 2021년)'),
    ('S0 기준연도가 본 데이터와 다르다',
     '캘리브레이션에 쓴 KIHASA 기초분석 보고서는 <b>R01 = 2020년(1기)</b>, <b>R02 = 2021년(2기)</b> 이다. '
     '3기(2022년) 기초분석은 미발간이라, 조건부 구조는 2020~2021년 값에, 총량·단가는 2022년 원기관 집계에 맞췄다. '
     '근거: <code>registry/s0_basis_finding.md</code>'),
    ('변수마다 근거 수준이 다르다',
     '<code>final/codebook_synthetic.xlsx</code> 의 <b>주장지위</b> 열(1차확인 / 논리적추론 / 가정 / 미확인)과 '
     '<code>report/assumptions.md</code> 를 확인할 것.'),
]

CSS = """<style>
:root{--bd:#e3e6ea;--mut:#667085;--bg:#fff;--fg:#16191d;--soft:#f7f8fa;--hd:#eef1f4}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR','Malgun Gothic','Apple SD Gothic Neo',sans-serif;
margin:0;padding:26px 30px 80px;line-height:1.6;color:var(--fg);background:var(--bg);
-webkit-font-smoothing:antialiased}
h1{font-size:23px;margin:0 0 4px;letter-spacing:-.3px}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--bd)}
h3{font-size:14px;margin:18px 0 6px;color:#2f3640}
.sub{color:var(--mut);font-size:13px;margin-bottom:6px}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 6px}
.card{border:1px solid var(--bd);border-radius:9px;padding:11px 15px;min-width:124px;background:var(--soft)}
.card b{display:block;font-size:21px;line-height:1.25} .card span{font-size:11.5px;color:var(--mut)}
.ok{color:#1a7f37} .bad{color:#c0392b} .na{color:#8a8f98} .warn{color:#b7791f}
.note{background:#fbfbfd;border:1px solid var(--bd);border-left:3px solid #8b9bb4;
border-radius:0 7px 7px 0;padding:10px 14px;margin:12px 0;font-size:12.6px;color:#3a4048}
.note b{color:#1f2933}
.note ol{margin:6px 0 0 18px;padding:0} .note li{margin:3px 0}
.wrap{overflow-x:auto;overflow-y:auto;max-height:600px;border:1px solid var(--bd);border-radius:7px;
-webkit-overflow-scrolling:touch}
table.tbl{border-collapse:separate;border-spacing:0;font-size:11.8px;width:100%;min-width:max-content}
table.tbl th{position:sticky;top:0;z-index:2;background:var(--hd);text-align:left;padding:7px 10px;
border-bottom:1px solid var(--bd);white-space:nowrap;font-weight:600}
table.tbl td{padding:5px 10px;border-bottom:1px solid #f0f2f4;vertical-align:top;
max-width:520px;word-break:break-word}
table.tbl tr:hover td{background:#fafbfc}
table.tbl td:nth-child(1){white-space:nowrap}
code{background:#f1f3f5;padding:1px 5px;border-radius:3px;font-size:11.5px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.toc{font-size:12.5px;color:var(--mut);margin:10px 0 0;line-height:2}
.toc a{color:#3b5bdb;text-decoration:none;margin-right:14px;white-space:nowrap}
.toc a:hover{text-decoration:underline}
.small{font-size:11.8px;color:var(--mut);margin:6px 0 0}
</style>"""

SECTIONS = [('s1', '① 요약 KPI'), ('s2', '② 검증목표(등급별)'), ('s3', '③ S0 캘리브레이션'),
            ('s4', '④ S1 총량'), ('s5', '⑤ 생성 커버리지'), ('s6', '⑥ 주변분포 적합'),
            ('s7', '⑦ §7 정합성 규칙'), ('s8', '⑧ NULL 패턴'), ('s9', '⑨ seed 재현성'),
            ('s10', '⑩ 변수별 요약통계')]


def _sec(sid, title):
    return f"<h2 id='{sid}'>{html.escape(title)}</h2>"


def _grade_block(t2, g, label):
    d = t2[t2['grade'] == g] if 'grade' in t2.columns else t2.iloc[0:0]
    if not len(d): return ''
    npass = int((d['판정'] == '✅ 통과').sum()); ntot = int((d['판정'] != '⚠ 평가불가').sum())
    cls = 'ok' if ntot and npass == ntot else 'bad'
    return (f"<h3>{label} — <span class='{cls}'>{npass}/{ntot} 통과</span> (총 {len(d)}건)</h3>"
            "<div class='wrap'>" + _tbl(d.drop(columns=['grade'], errors='ignore')) + "</div>")


def build_html(df, pop=None, out='report/validation.html', cb=None, extra=None,
               check_seed=True, gen_date='2026-09-02'):
    cb = cb or {}
    if pop is None and {'_N_pop_person', '_N_pop_hh'} <= set(df.columns):
        pop = {'persons': float(df['_N_pop_person'].iloc[0]),
               'households': float(df['_N_pop_hh'].iloc[0])}
    tg = load_targets()
    res = [eval_target(df, t) for t in tg]
    tr = pd.DataFrame(res) if res else pd.DataFrame()
    cons = consistency.run(df, pop)
    nul = null_pattern(df, cb)
    nsc = null_scope_check(df, cb)
    stt = summary_stats(df)
    n_pass = int(tr['pass'].sum()) if len(tr) and 'pass' in tr else 0
    n_tot = int(tr['pass'].notna().sum()) if len(tr) and 'pass' in tr else 0
    n_na = (len(tr) - n_tot) if len(tr) else 0
    viol = cons[cons.violations.apply(lambda v: isinstance(v, (int, np.integer)) and v > 0)]
    n_viol = int(viol['violations'].sum()) if len(viol) else 0
    n_hh_s = df['hid'].nunique() if 'hid' in df.columns else 0
    sw_i = float(df['indwgt'].sum()) if 'indwgt' in df.columns else float('nan')
    sw_h = float(df.loc[df['head'] == 1, 'hhwgt'].sum()) if {'head', 'hhwgt'} <= set(df.columns) else float('nan')

    P = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>가상데이터 검증 리포트</title>{CSS}</head><body>",
         "<h1>3기 사회보장행정데이터(2022년 기준) 가상데이터 — 검증 리포트</h1>",
         f"<div class='sub'>작업지시서 v2 §9 · 개인 {len(df):,}행 × 변수 {len(df.columns):,}개 "
         f"(코드북 변수 {len([c for c in df.columns if not c.startswith('_')]):,} + 헬퍼 "
         f"{len([c for c in df.columns if c.startswith('_')]):,}) · 생성일 {gen_date}</div>",
         "<div class='toc'>" + ''.join(f"<a href='#{i}'>{n}</a>" for i, n in SECTIONS) + "</div>"]

    # ── ① 요약 KPI ────────────────────────────────────────────────────────────
    P.append(_sec('s1', '① 요약 KPI'))
    P.append("<div class='kpi'>"
             f"<div class='card'><b>{len(df):,}</b><span>개인(표본)</span></div>"
             f"<div class='card'><b>{n_hh_s:,}</b><span>가구(표본)</span></div>"
             f"<div class='card'><b>{len([c for c in df.columns if not c.startswith('_')]):,}</b><span>코드북 변수</span></div>"
             f"<div class='card'><b class='{'ok' if n_viol==0 else 'bad'}'>{n_viol:,}</b><span>§7 규칙 위반 건수</span></div>"
             f"<div class='card'><b class='{'ok' if n_tot and n_pass==n_tot else 'bad'}'>{n_pass}/{n_tot}</b><span>검증목표 통과</span></div>"
             f"<div class='card'><b>{sw_i:,.0f}</b><span>Σ indwgt (모집단 인구)</span></div>"
             f"<div class='card'><b>{sw_h:,.0f}</b><span>Σ hhwgt (일반가구)</span></div>"
             "</div>")
    P.append(f"<p class='small'>§7 규칙 {len(cons)}건 중 위반 규칙 {len(viol)}개 · 위반 레코드 {n_viol:,}건 · "
             f"평가불가 목표 {n_na}건 (해당 변수 미생성 등).</p>")
    P.append("<div class='note'><b>이 데이터를 쓰기 전에 반드시 알아야 할 5가지</b><ol>"
             + ''.join(f"<li><b>{t}</b> — {b}</li>" for t, b in CAVEATS) + "</ol></div>")

    # ── ② 검증목표 (등급별) ───────────────────────────────────────────────────
    P.append(_sec('s2', '② 검증목표 — 등급별 (S0 ±3%p · S1 ±10% 원칙)'))
    P.append(
        "<div class='note'><b>비율·평균 목표는 비가중·가중을 병기한다 — 어느 쪽을 판정에 썼는지 반드시 확인할 것</b>"
        "<p>본 가상데이터는 <b>자기가중 표본이 아니다</b>. 표본 9,535명은 인구 51,450,829명을 "
        "<code>indwgt</code>(가구는 <code>hhwgt</code>)로 대표하며, 가중치는 개인마다 다르다. "
        "따라서 같은 지표라도 <b>비가중 표본평균</b>과 <b>가중 평균</b>은 서로 다른 값이 되고, "
        "<b>서로 다른 모수를 추정한다</b>.</p>"
        "<ul>"
        "<li><b>모집단 비율·평균 목표에 비가중을 쓰면 구조적으로 어긋난다.</b> 출처가 "
        "「공표 총액 ÷ 공표 인원」(예: 국세통계 총연금수령액 ÷ 수령 인원)이나 "
        "「전국 가구 중 ○○ 가구 비율」(예: 가계금융복지조사)처럼 <b>두 모집단 총계의 비(比)</b>로 "
        "정의된 모수라면, 그 불편추정량은 Σ(w·y)/Σw <b>뿐</b>이다. 비가중 표본평균은 "
        "「표본에 뽑힌 사람들의 평균」이라는 <b>다른 양</b>을 재며, 층화추출로 과대·과소 대표된 층이 "
        "그대로 섞여 들어간다. 편차가 tol 안에 들어오더라도 그것은 우연이지 정합성의 근거가 아니다.</li>"
        "<li>반대로 <b>표본 구성 자체를 기준으로 만든 목표</b>(예: 표본 등급분포로 재가중해 산출한 "
        "이용률)나 <b>부분집단 내부 비율</b>은 비가중 비교가 의도된 것일 수 있다. "
        "그래서 kind 를 임의로 바꾸지 않고 <b>두 값을 모두 표에 노출</b>한다.</li>"
        "</ul>"
        "<p><code>추정량</code> 열: <code>rate</code>·<code>mean</code> = 비가중, "
        "<code>wrate</code>·<code>wmean</code> = 가중, <code>wcount</code> = 가중 총량(모집단 규모), "
        "<code>expr</code> = 파생지표(지니·상대빈곤율 등, 내부적으로 <code>indwgt</code> 가중). "
        "<code>비가중 / 가중 (병기)</code> 열의 <b>←판정</b> 표시가 실제 합격 판정에 쓰인 값이다.</p>"
        "<p>가중 기준으로 전부 재계산했을 때 판정이 뒤집히는 목표와 그 사유는 "
        "<code>registry/deviation_analysis.md</code> §4 에 전수 기록했다.</p></div>")
    if len(tr):
        t2 = tr.copy()
        for c in ('name', 'target', 'got', 'alt', 'dev', 'tol', 'pass', 'source', 'err'):
            if c not in t2.columns: t2[c] = None
        tks = [t.get('tol_kind', 'pp') for t in tg]
        t2['grade'] = [t.get('grade', '') for t in tg]
        t2['출처파일'] = [t.get('file', '') for t in tg]
        t2['target'] = [_fmt(v, k) for v, k in zip(t2['target'], tks)]
        t2['got'] = [_fmt(v, k) for v, k in zip(t2['got'], tks)]
        t2['pass'] = t2['pass'].map({True: '✅ 통과', False: '❌ 이탈'}).fillna('⚠ 평가불가')
        t2['kind'] = [t.get('kind', 'rate') for t in tg]
        t2 = t2.rename(columns={'name': '항목', 'target': '목표', 'got': '재현값', 'dev': '편차',
                                'tol': '허용', 'pass': '판정', 'source': '출처', 'err': '오류',
                                'alt': '비가중 / 가중 (병기)', 'kind': '추정량'})
        t2 = t2[['grade', '항목', '추정량', '목표', '재현값', '비가중 / 가중 (병기)', '편차',
                 '허용', '판정', '출처파일', '출처', '오류']]
        for g, lab in (('S0', 'S0 — 사회보장행정데이터 자체 기초분석 (R01=2020 · R02=2021)'),
                       ('S1', 'S1 — 원기관 행정집계 (2022)'),
                       ('S2', 'S2 — 승인통계·기타')):
            P.append(_grade_block(t2, g, lab))
        other = t2[~t2['grade'].isin(['S0', 'S1', 'S2'])]
        if len(other):
            P.append("<h3>등급 미표기</h3><div class='wrap'>" + _tbl(other.drop(columns=['grade'])) + "</div>")
    else:
        P.append("<p class='na'>targets/*.yaml 미작성 — 검증 목표 없음</p>")

    # ── ③ S0 캘리브레이션 ─────────────────────────────────────────────────────
    P.append(_sec('s3', '③ S0 캘리브레이션 — R01(2020, 1기) · R02(2021, 2기) 대비 재현오차'))
    P.append("<div class='note'><b>연도차 주석 (필수)</b><br>"
             "S0 로 쓴 KIHASA 기초분석 보고서는 <b>R01 = 2020년(1기)</b>, <b>R02 = 2021년(2기)</b> 기준이고 "
             "본 가상데이터는 <b>2022년(3기)</b> 코드북을 재현한다. 3기 기초분석은 미발간이라 "
             "<b>1~2년의 연도차</b>가 구조적으로 존재한다 (영아수당 2022년 신설, 기초연금 기준연금액 인상, "
             "물가·인구고령화). 또한 원 데이터가 등록센서스 <b>일반가구</b> 표본이므로 "
             "<b>시설거주 수급자가 제외</b>되어 자산조사형 급여 수급률은 정부 공표 총량보다 낮게 나오는 것이 정상이다. "
             "근거: <code>registry/s0_basis_finding.md</code></div>")
    s0 = s0_calibration(tg, res)
    if len(s0):
        npass = int((s0['판정'] == '✅ 통과').sum())
        P.append(f"<p class='small'>S0 목표 {len(s0)}건 중 <b class='{'ok' if npass==len(s0) else 'bad'}'>"
                 f"{npass}건 통과</b> · R01 기준 {int((s0['기준연도']==2020).sum())}건 / "
                 f"R02 기준 {int((s0['기준연도']==2021).sum())}건</p>")
        P.append("<div class='wrap'>" + _tbl(s0) + "</div>")
    else:
        P.append("<p class='na'>S0 등급 목표 없음</p>")

    # ── ④ S1 총량 ─────────────────────────────────────────────────────────────
    P.append(_sec('s4', '④ S1 총량 — 급여별 가중 추정 vs 원기관 2022 집계'))
    s1 = s1_totals(tg, res)
    if len(s1):
        npass = int((s1['판정'] == '✅ 통과').sum())
        P.append(f"<p class='small'>S1 목표 {len(s1)}건 중 <b class='{'ok' if npass==len(s1) else 'bad'}'>"
                 f"{npass}건 통과</b>. 가중 추정 = Σ(해당 조건 × <code>indwgt</code> 또는 "
                 f"<code>hhwgt</code>). 자산조사형 급여는 <b>시설수급자를 뺀 일반수급자</b> 값을 목표로 쓴다.</p>")
        P.append("<div class='wrap'>" + _tbl(s1) + "</div>")
    else:
        P.append("<p class='na'>S1 등급 목표 없음</p>")

    # ── ⑤ 생성 커버리지 ───────────────────────────────────────────────────────
    P.append(_sec('s5', '⑤ 생성 커버리지 — 블록별·주장지위별'))
    try:
        cov = coverage(df, cb)
        st = cov.iloc[-1]
        dec, gen, n_nullvar, mis = (int(st['선언변수']), int(st['값 있음']),
                                    int(st['전량 NULL']), int(st['미생성']))
        P.append(f"<p class='small'>Tier1+2 <b>{dec}변수</b> 중 <b>값이 있는 변수 {gen}개</b> "
                 f"({gen/max(dec,1)*100:.1f}%) · 컬럼은 있으나 전량 NULL {n_nullvar}개 · 컬럼 미생성 {mis}개. "
                 f"코드북 전체 993변수 대비 {gen/993*100:.1f}%. "
                 f"주장지위(값 있는 변수): 1차확인 {int(st['1차확인'])} · 논리적추론 {int(st['논리적추론'])} · "
                 f"가정 {int(st['가정'])} · 미확인 {int(st['미확인'])}. "
                 f"전량 NULL 은 표본 9,535명에서 기대 수급자가 1명 미만이거나(§4 규모 미달) "
                 f"단가·인원 파라미터를 확보하지 못한 변수다 — report/assumptions.md 부록 참조.</p>")
        P.append("<div class='wrap'>" + _tbl(cov) + "</div>")
    except Exception as e:
        P.append(f"<p class='na'>산출 실패: {html.escape(str(e))}</p>")

    # ── ⑥ 주변분포 적합 ───────────────────────────────────────────────────────
    P.append(_sec('s6', '⑥ 주변분포 적합 — 성×5세 연령 · 시도 · 가구원수 · 지니·상대빈곤율'))
    for fn, title, src in ((marginal_age_sex, '6-1. 성 × 5세 연령대 (가중)',
                            '주민등록 2022.11 시군구×1세×성 (Σ 51,450,829)'),
                           (marginal_sido, '6-2. 시도 17개 인구 구성비 (가중)',
                            '주민등록 2022.11 시도×성'),
                           (marginal_hhsize, '6-3. 가구원수 분포 (가구 가중)',
                            '2022 인구주택총조사 일반가구 21,773,507'),
                           (marginal_hhtype, '6-4. 세대구성(가구유형) 분포 (가구 가중)',
                            '2022 장래가구추계 <표2> · 등록센서스 보도자료 <표22> [1차확인]')):
        try:
            m = fn(df)
        except Exception as e:
            m = None
            P.append(f"<h3>{title}</h3><p class='na'>산출 실패: {html.escape(str(e))}</p>")
        if m is not None and len(m):
            mx = float(m['차이(%p)'].abs().max())
            cls = 'ok' if mx <= 1.0 else ('warn' if mx <= 3.0 else 'bad')
            P.append(f"<h3>{title} — 최대 편차 <span class='{cls}'>{mx:.3f}%p</span></h3>"
                     f"<p class='small'>모집단 기준: {src}</p>"
                     "<div class='wrap'>" + _tbl(m) + "</div>")
            if fn is marginal_hhtype:
                P.append("<div class='note'><b>이 표는 적합되지 않은 주변분포다 — 알려진 한계</b><br>"
                         "성×연령·시도·가구원수 3개 주변분포는 생성 단계에서 모집단에 맞췄지만, "
                         "<b>세대구성은 맞추지 않았다</b>. B01 의 세대구성 템플릿 확률은 "
                         "<code>[가정 A1-1]</code>(가구원수 조건부 배분의 통상 구조)이고, "
                         "가구원수×세대구성 <b>교차표</b>가 확보되지 않아 IPF 적합을 하지 않았다. "
                         "위 표의 주변분포 자체는 <b>[1차확인]</b>이므로 편차는 실측값이다. "
                         "영향: 3세대·비친족 가구가 과대하여 <b>노인 상대빈곤율이 낮게</b>, "
                         "한부모 가구가 과대하여 <b>아동 상대빈곤율이 높게</b> 나온다. "
                         "사후층화 실험으로 정량화한 기여분은 노인 +1.9%p · 아동 −1.1%p 로, "
                         "각 이탈폭(−8.8%p · +8.7%p)의 20% 안팎이다. "
                         "전체 원인 분해는 <code>registry/deviation_analysis.md</code> §3-B 참조.</div>")
    try:
        di = dist_indicators(df, tg, res)
        P.append("<h3>6-5. 소득분포 지표 — 지니계수 · 상대빈곤율</h3>"
                 "<p class='small'>균등화 소득 = 가구합 / √가구원수. 빈곤선 = 균등화 중위소득의 50%. "
                 "가중치 <code>indwgt</code> 적용. 목표는 S0(R01·R02) 값이므로 연도차 주석(③)이 함께 적용된다.</p>"
                 "<div class='wrap'>" + _tbl(di) + "</div>")
    except Exception as e:
        P.append(f"<p class='na'>분포지표 산출 실패: {html.escape(str(e))}</p>")

    # ── ⑦ §7 규칙 ─────────────────────────────────────────────────────────────
    P.append(_sec('s7', f'⑦ §7 조건부 정합성 규칙 {len(cons)}건 — 위반 0건이 합격'))
    P.append(f"<p class='small'>위반 규칙 <b class='{'ok' if len(viol)==0 else 'bad'}'>{len(viol)}개</b> · "
             f"위반 레코드 <b class='{'ok' if n_viol==0 else 'bad'}'>{n_viol:,}건</b> · "
             f"<code>N/A</code> 는 판정에 필요한 컬럼이 없어 검사하지 못한 규칙이다.</p>")
    P.append("<div class='wrap'>" + _tbl(cons) + "</div>")

    # ── ⑧ NULL 패턴 ───────────────────────────────────────────────────────────
    P.append(_sec('s8', '⑧ NULL 패턴 = 추출대상 정의 일치 여부'))
    vc = nsc['판정'].value_counts()
    P.append("<p class='small'>코드북 <b>추출대상</b> 문구를 <b>전수형</b>(2022.11.1 일반가구·일반가구원 전원, "
             "무정보 0원 처리 포함)과 <b>조건부형</b>(“한 번이라도 수급/가입/참여한 집단” 등)으로 분류한 뒤, "
             "① 전수형 → NULL 0% ② 조건부형 → 0%&lt;NULL&lt;100% ③ <code>X_yn2/_dur/_amt/_type</code> 의 "
             "관측집합 ⊆ <code>{X_yn1=1}</code> 을 기계 점검했다. 판정: "
             + ' · '.join(f'{k} {v}건' for k, v in vc.items()) + "</p>")
    P.append("<div class='wrap'>" + _tbl(nsc) + "</div>")
    P.append("<h3>8-2. 변수별 NULL 비율 (내림차순)</h3><div class='wrap'>" + _tbl(nul) + "</div>")

    # ── ⑨ seed 재현성 ─────────────────────────────────────────────────────────
    P.append(_sec('s9', '⑨ seed 재현성 — 동일 seed 2회 생성 결과 비교 (실제 실행)'))
    if check_seed:
        try:
            sr = seed_repro(n_hh=int(df['hid'].nunique()) if 'hid' in df.columns else 4200, df_ref=df)
            P.append("<div class='wrap'>" + _tbl(sr) + "</div>")
        except Exception as e:
            P.append(f"<p class='bad'>재현성 검사 실패: {html.escape(type(e).__name__ + ': ' + str(e))}</p>")
    else:
        P.append("<p class='na'>check_seed=False 로 건너뜀</p>")

    # ── ⑩ 변수별 요약통계 ─────────────────────────────────────────────────────
    P.append(_sec('s10', '⑩ 변수별 요약통계'))
    P.append("<div class='wrap'>" + _tbl(stt) + "</div>")

    if extra:
        for title, obj in extra:
            P.append(f"<h2>{html.escape(title)}</h2>")
            P.append("<div class='wrap'>" + (_tbl(obj) if isinstance(obj, pd.DataFrame)
                                             else f"<pre>{html.escape(str(obj))}</pre>") + "</div>")
    P.append("</body></html>")
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w', encoding='utf-8').write('\n'.join(P))
    return {'out': out, 'targets_pass': n_pass, 'targets_total': n_tot,
            'targets_na': n_na, 'rule_violations': len(viol), 'violation_records': n_viol,
            'rows': len(df), 'cols': len(df.columns)}


if __name__ == '__main__':
    df = pd.read_parquet(sys.argv[1] if len(sys.argv) > 1 else 'data/stage_all.parquet')
    cb = {v['var']: v for v in json.load(open('registry/codebook.json', encoding='utf-8'))}
    print(build_html(df, cb=cb))

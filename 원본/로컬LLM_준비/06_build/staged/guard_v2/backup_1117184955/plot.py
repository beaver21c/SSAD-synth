# -*- coding: utf-8 -*-
"""ssda.plot — 집계 결과(Result)를 그림으로 그린다. 개인 단위 점 그림은 제공하지 않는다(R7).
억제 칸은 그리지 않고 「억제」로 표기한다. 그림은 save()로 반출 신청 폴더에 저장한다."""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from .core import QueryError, Result, ST_OK  # noqa: E402

PKG = Path(__file__).resolve().parent
COLORS = ['#1F4E79', '#C55A11', '#2E7D32', '#7F6000', '#6A3D9A', '#00838F', '#8D8C86']
_FONT = None
LABEL_SHIFT = {'경기': (16, 46)}      # 시도 지도에서 값 표기가 이웃 시도와 겹치지 않도록 옮기는 거리(경기의 중심이 서울과 겹침)


def _font():
    global _FONT
    if _FONT is None:
        have = {f.name for f in font_manager.fontManager.ttflist}
        _FONT = next((n for n in ('KoPubDotum', 'KoPub돋움체', 'Noto Sans CJK KR', 'NanumGothic', 'Malgun Gothic', 'AppleGothic') if n in have), 'sans-serif')
        plt.rcParams['font.family'] = _FONT
        plt.rcParams['axes.unicode_minus'] = False
    return _FONT


def _check(res, dims):
    if not isinstance(res, Result):
        raise QueryError('그림은 ssda 집계 결과(Result)로만 그릴 수 있음')
    if len(res.by) not in dims:
        raise QueryError(f'이 그림은 분류 기준이 {" 또는 ".join(map(str, dims))}개인 결과에 사용함(현재 {len(res.by)}개)')
    _font()
    return res.table()


def _fmt(v, unit):
    return f'{v:,.1f}' if unit in ('%', '일') or abs(v) < 100 else f'{v:,.0f}'


def _finish(fig, ax, res, title):
    ax.set_title(title or res.label, fontsize=13, fontweight='bold', loc='left')
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, f'단위: {res.unit} · 등급 {res.grade} · 최소 관측 수 미달 칸은 표시하지 않음(「억제」 또는 ×)', fontsize=8, color='#63625C')
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    return fig


def bar(res, title=None, sort=False, values=True, horizontal=False):
    """막대 그림. 분류 기준 1개면 단일 막대, 2개면 묶음 막대."""
    d = _check(res, (1, 2))
    x = res.by[0]
    cats = list(pd.unique(d[x]))
    ser = [None] if len(res.by) == 1 else list(pd.unique(d[res.by[1]]))
    if sort and len(res.by) == 1:
        cats = list(d.sort_values('값', ascending=False, na_position='last')[x])
    fig, ax = plt.subplots(figsize=(9, max(4.2, 0.36 * len(cats) * max(1, len(ser) / 2) + 1.6) if horizontal else 4.6))
    values = values and (horizontal or len(cats) * len(ser) <= 20)       # 막대가 많으면 값 표기가 겹치므로 생략(값은 표로 확인)
    w = 0.8 / len(ser)
    for j, s in enumerate(ser):
        sub = d if s is None else d[d[res.by[1]] == s]
        v = sub.set_index(x)['값'].reindex(cats).values
        pos = np.arange(len(cats)) + (j - (len(ser) - 1) / 2) * w
        (ax.barh if horizontal else ax.bar)(pos, np.nan_to_num(v), w * 0.92, color=COLORS[j % len(COLORS)], label=None if s is None else str(s))
        for p, val in zip(pos, v):
            t = ('억제' if values else '×') if np.isnan(val) else (_fmt(val, res.unit) if values else '')      # 막대가 많을 때 억제 칸은 ×로 표기
            if horizontal:
                ax.text(0 if np.isnan(val) else val, p, ' ' + t, va='center', fontsize=8, color='#8A8983' if np.isnan(val) else '#1C1C1A')
            else:
                ax.text(p, 0 if np.isnan(val) else val, t, ha='center', va='bottom', fontsize=8, color='#8A8983' if np.isnan(val) else '#1C1C1A')
    (ax.margins(x=0.12) if horizontal else ax.margins(y=0.12))        # 값 표기가 그림 밖으로 나가지 않도록 여백을 둠
    if horizontal:
        ax.set_yticks(np.arange(len(cats))); ax.set_yticklabels(cats); ax.invert_yaxis(); ax.set_xlabel(res.unit)
    else:
        ax.set_xticks(np.arange(len(cats))); ax.set_xticklabels(cats, rotation=35 if len(cats) > 8 else 0, ha='right' if len(cats) > 8 else 'center'); ax.set_ylabel(res.unit)
    if len(ser) > 1:
        ax.legend(title=res.by[1], frameon=False, fontsize=9)
    return _finish(fig, ax, res, title)


def hbar(res, title=None, sort=True, values=True):
    """가로 막대 그림(항목이 많을 때)."""
    return bar(res, title=title, sort=sort, values=values, horizontal=True)


def line(res, title=None, values=False):
    """선 그림. 분류 기준 1개면 선 1개, 2개면 둘째 기준별 선."""
    d = _check(res, (1, 2))
    x = res.by[0]; cats = list(pd.unique(d[x]))
    ser = [None] if len(res.by) == 1 else list(pd.unique(d[res.by[1]]))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for j, s in enumerate(ser):
        sub = d if s is None else d[d[res.by[1]] == s]
        v = sub.set_index(x)['값'].reindex(cats).values
        ax.plot(np.arange(len(cats)), v, marker='o', color=COLORS[j % len(COLORS)], label=None if s is None else str(s))
        if values:
            for i, val in enumerate(v):
                if not np.isnan(val):
                    ax.text(i, val, _fmt(val, res.unit), ha='center', va='bottom', fontsize=8)
    ax.set_xticks(np.arange(len(cats))); ax.set_xticklabels(cats, rotation=35 if len(cats) > 8 else 0, ha='right' if len(cats) > 8 else 'center')
    ax.set_ylabel(res.unit); ax.grid(axis='y', color='#E4E3DE'); ax.margins(y=0.12)
    if len(ser) > 1:
        ax.legend(title=res.by[1], frameon=False, fontsize=9)
    return _finish(fig, ax, res, title)


def heatmap(res, title=None, cmap='Blues'):
    """분류 기준 2개의 교차표를 색 농도로 그린다."""
    _check(res, (2,))
    p = res.pivot()
    fig, ax = plt.subplots(figsize=(1.6 + 1.25 * p.shape[1], 1.4 + 0.5 * p.shape[0]))
    a = p.values.astype(float)
    im = ax.imshow(np.ma.masked_invalid(a), cmap=cmap, aspect='auto')
    mid = np.nanmean(a) if np.isfinite(a).any() else 0
    for i in range(a.shape[0]):
        for j in range(a.shape[1]):
            v = a[i, j]
            ax.text(j, i, '억제' if np.isnan(v) else _fmt(v, res.unit), ha='center', va='center', fontsize=9, color='#8A8983' if np.isnan(v) else ('#fff' if v > mid else '#1C1C1A'))
    ax.set_xticks(range(p.shape[1])); ax.set_xticklabels(p.columns); ax.set_yticks(range(p.shape[0])); ax.set_yticklabels(p.index)
    ax.set_xlabel(res.by[1]); ax.set_ylabel(res.by[0])
    fig.colorbar(im, ax=ax, shrink=0.8, label=res.unit)
    return _finish(fig, ax, res, title)


def map_sido(res, title=None, cmap='Blues', k=5):
    """시도 단계구분도(분류 기준이 시도 1개인 결과). 분위수 k단계."""
    d = _check(res, (1,))
    if res.by[0] != '시도':
        raise QueryError("map_sido()는 by='sido' 인 결과에 사용함")
    geo = json.loads((PKG / 'data' / 'sido_polygons.json').read_text(encoding='utf-8'))
    val = d.set_index('시도')['값']
    ok = val.dropna()
    br = np.quantile(ok.values, np.linspace(0, 1, k + 1)[1:-1]) if len(ok) >= k else []
    cm = matplotlib.colormaps[cmap]
    fig, ax = plt.subplots(figsize=(6.4, 7.4))
    for name, rings in geo['sido'].items():
        v = val.get(name, np.nan)
        col = '#EFEEE9' if np.isnan(v) else cm(0.15 + 0.8 * (np.searchsorted(br, v) / max(k - 1, 1)))
        for ring in rings:
            ax.add_patch(Polygon(ring, closed=True, facecolor=col, edgecolor='#55544F', linewidth=0.5, hatch='////' if np.isnan(v) else None))
        cx, cy = geo['center'][name]
        cx, cy = cx + LABEL_SHIFT.get(name, (0, 0))[0], cy + LABEL_SHIFT.get(name, (0, 0))[1]
        ax.text(cx, cy, '억제' if np.isnan(v) else _fmt(v, res.unit), ha='center', va='center', fontsize=8, fontweight='bold',
                color='#1C1C1A', bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.6))
    ax.set_xlim(geo['xlim']); ax.set_ylim(geo['ylim'][::-1]); ax.set_aspect('equal'); ax.axis('off')
    ax.set_title(title or res.label, fontsize=13, fontweight='bold', loc='left')
    fig.text(0.01, 0.01, f'단위: {res.unit} · 분위수 {k}단계 · 빗금: 최소 관측 수 미달로 표시하지 않음', fontsize=8, color='#63625C')
    return fig


_FIGLOG = []              # 이번 실행에서 저장한 그림의 점검 내역(실행기가 읽는다)


def _inspect(fig):
    """그림을 저장하기 전에 스스로 점검한다: 제목, 내용 유무, 항목 이름 겹침(겹치면 기울여 고침), 잘린 글자, 값 표기 겹침."""
    from matplotlib.text import Text
    issues, fixed = [], []
    if not fig.axes:
        return {'issues': ['그림에 내용이 없음'], 'fixed': [], 'marks': 0, 'title': '', 'suppressed': 0}
    ax = fig.axes[0]
    fig.canvas.draw(); r = fig.canvas.get_renderer()

    def overlap_x():
        labs = [t for t in ax.get_xticklabels() if t.get_visible() and t.get_text().strip()]
        if len(labs) < 2 or any(abs(t.get_rotation()) > 1 for t in labs):
            return False
        bb = [t.get_window_extent(r) for t in labs]
        return any(bb[i].x1 > bb[i + 1].x0 + 1 for i in range(len(bb) - 1))

    if overlap_x():
        for t in ax.get_xticklabels():
            t.set_rotation(35); t.set_ha('right')
        fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.canvas.draw(); r = fig.canvas.get_renderer()
        fixed.append('가로축 항목 이름이 겹쳐 기울여 표시함')
    W, H = fig.bbox.width, fig.bbox.height
    tt = ax.title if ax.title.get_text().strip() else ax._left_title
    if tt.get_text().strip():                                  # 제목이 그림 폭을 넘으면 줄을 나눔
        b = tt.get_window_extent(r)
        if b.x1 > W - 4 and b.width > 0:
            import textwrap
            n = max(8, int(len(tt.get_text()) * (W - b.x0 - 12) / b.width))
            tt.set_text('\n'.join(textwrap.wrap(tt.get_text(), n)))
            fig.tight_layout(rect=(0, 0.03, 1, 0.98)); fig.canvas.draw(); r = fig.canvas.get_renderer()
            fixed.append('제목이 길어 줄을 나누어 표시함')
    hidden = set()                                             # 축 범위 밖의 눈금 이름은 그려지지 않으므로 점검에서 뺌
    for a in fig.axes:
        for axis, (lo, hi) in ((a.xaxis, sorted(a.get_xlim())), (a.yaxis, sorted(a.get_ylim()))):
            for loc, lab in zip(axis.get_ticklocs(), axis.get_ticklabels()):
                if not (lo - 1e-9 <= loc <= hi + 1e-9):
                    hidden.add(id(lab))
    clipped = 0
    for t in fig.findobj(Text):
        if t.get_visible() and t.get_text().strip() and id(t) not in hidden:
            b = t.get_window_extent(r)
            if b.x0 < -2 or b.y0 < -2 or b.x1 > W + 2 or b.y1 > H + 2:
                clipped += 1
    if clipped:
        issues.append(f'그림 밖으로 잘린 글자 {clipped}곳')
    title = (ax.get_title(loc='left') or ax.get_title() or '').strip()
    if not title:
        issues.append('제목 없음')
    marks = len(ax.patches) + len(ax.lines) + len(ax.images) + len(ax.collections)
    if marks == 0:
        issues.append('그림에 표시된 값이 없음')
    tx = [t for t in ax.texts if t.get_visible() and t.get_text().strip()]
    bbs = [t.get_window_extent(r).shrunk(0.9, 0.8) for t in tx]
    n_ov = sum(1 for i in range(len(bbs)) for j in range(i + 1, len(bbs)) if bbs[i].overlaps(bbs[j]))
    if n_ov:
        issues.append(f'값 표기가 서로 겹친 곳 {n_ov}곳')
    return {'issues': issues, 'fixed': fixed, 'marks': marks, 'title': title, 'suppressed': sum(1 for t in tx if t.get_text().strip() == '억제')}


def save(fig, name):
    """그림을 점검한 뒤 반출 신청 폴더(SSDA_EXPORT)에 PNG로 저장한다."""
    out = Path(os.environ.get('SSDA_EXPORT', 'export')); out.mkdir(parents=True, exist_ok=True)
    name = str(name)
    name = name[:-4] if name.lower().endswith('.png') else name      # 이름에 확장자를 붙여 온 경우(.png.png 방지)
    p = out / f'{name}.png'
    info = _inspect(fig)
    fig.savefig(p, dpi=160, facecolor='white')
    plt.close(fig)
    _FIGLOG.append({'file': p.name, **info})
    return str(p)

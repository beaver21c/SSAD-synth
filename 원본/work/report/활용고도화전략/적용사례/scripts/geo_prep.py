#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계 자료 준비 — 시군구·시도 경계를 화면 좌표의 SVG 경로로 변환한다.

입력(사용자 깃허브 레포 kihasa-indicator 의 공개 경계 자료)
  public/data/sigungu.json          시군구 229개(GeoJSON, 일반구 통합, 5자리 코드)
  public/data/map/sido.topojson     시도 17개(TopoJSON)
출력
  data/geo.json   {"w","h","sgg":[{code,name,sido,d,cx,cy}], "sido":[{code,name,d,cx,cy}]}
"""
import json, math, sys
from pathlib import Path

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
W = 760.0
LON0, LAT0 = 124.6, 38.75           # 왼쪽 위 기준
KX = math.cos(math.radians(36.0))
SPAN = (131.0 - LON0) * KX           # 가로 범위(도, 보정 후) — 울릉도까지
S = W / SPAN


def proj(lon, lat):
    return ((lon - LON0) * KX * S, (LAT0 - lat) * S)


def dp(pts, tol):
    """Douglas–Peucker 단순화(반복 구현)."""
    if len(pts) < 5:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    st = [(0, len(pts) - 1)]
    while st:
        a, b = st.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        mx, mi = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            # 닫힌 고리는 처음과 끝이 같은 점이므로 그때는 점까지의 거리로 잰다
            d = abs((px - ax) * dy - (py - ay) * dx) / L if L > 1e-9 else math.hypot(px - ax, py - ay)
            if d > mx:
                mx, mi = d, i
        if mx > tol and mi > 0:
            keep[mi] = True
            st.append((a, mi)); st.append((mi, b))
    return [p for p, k in zip(pts, keep) if k]


def ring_path(ring, tol):
    pts = dp([proj(x, y) for x, y in ring], tol)
    if len(pts) < 4:
        return '', 0.0, 0.0, 0.0
    # 넓이·무게중심(신발끈 공식)
    A = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        c = x0 * y1 - x1 * y0
        A += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
    A *= 0.5
    if abs(A) < 0.15:                 # 화면에서 보이지 않는 작은 섬은 생략
        return '', 0.0, 0.0, 0.0
    cx /= (6 * A); cy /= (6 * A)
    d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts[:-1]) + 'Z'
    return d, abs(A), cx, cy


def geom_path(geom, tol):
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    ds, best = [], (0.0, 0.0, 0.0)
    for poly in polys:
        for k, ring in enumerate(poly):
            d, a, cx, cy = ring_path(ring, tol)
            if not d:
                continue
            ds.append(d)
            if k == 0 and a > best[0]:
                best = (a, cx, cy)
    return ''.join(ds), round(best[1], 1), round(best[2], 1)


def topo_features(topo):
    tr = topo.get('transform')
    arcs = []
    for arc in topo['arcs']:
        x = y = 0; pts = []
        for p in arc:
            if tr:
                x += p[0]; y += p[1]
                pts.append((x * tr['scale'][0] + tr['translate'][0], y * tr['scale'][1] + tr['translate'][1]))
            else:
                pts.append((p[0], p[1]))
        arcs.append(pts)

    def ring(ix):
        out = []
        for i in ix:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out += a if not out else a[1:]
        return out
    feats = []
    for name, obj in topo['objects'].items():
        for g in obj['geometries']:
            if g['type'] == 'Polygon':
                coords = [[ring(r) for r in g['arcs']]]
            elif g['type'] == 'MultiPolygon':
                coords = [[ring(r) for r in poly] for poly in g['arcs']]
            else:
                continue
            feats.append({'properties': g.get('properties', {}), 'geometry': {'type': 'MultiPolygon', 'coordinates': coords}})
    return feats


def main():
    sgg = json.load(open(SRC / 'sigungu.json', encoding='utf-8'))
    out = {'w': W, 'h': 0, 'sgg': [], 'sido': [], 'source': sgg.get('source', '')}
    for f in sgg['features']:
        d, cx, cy = geom_path(f['geometry'], 0.35)
        p = f['properties']
        out['sgg'].append({'code': p['code'], 'name': p['name'], 'sido': p['sido'], 'd': d, 'cx': cx, 'cy': cy})
    topo = json.load(open(SRC / 'map' / 'sido.topojson', encoding='utf-8'))
    feats = topo_features(topo)
    print('sido props sample:', feats[0]['properties'])
    for f in feats:
        d, cx, cy = geom_path(f['geometry'], 0.45)
        out['sido'].append({'props': f['properties'], 'd': d, 'cx': cx, 'cy': cy})
    ys = [float(t.split(',')[1]) for it in out['sgg'] for t in it['d'].replace('Z', 'L').replace('M', 'L').split('L') if ',' in t]
    out['h'] = round(max(ys) + 8, 1)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('sgg', len(out['sgg']), 'sido', len(out['sido']), 'h', out['h'], 'bytes', OUT.stat().st_size)


if __name__ == '__main__':
    main()

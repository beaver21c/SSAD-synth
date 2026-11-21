#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대시보드 조립 — 화면 틀(dashboard/template.html)에 집계 저장소·경계·모의실험 결과를 넣어 단일 HTML 을 만든다.
외부 자원(서체·스크립트·지도 타일)을 불러오지 않으므로 폐쇄망에서 파일 1개로 동작한다.

실행  python3 scripts/04_build_dashboard.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tpl = (ROOT / 'dashboard' / 'template.html').read_text(encoding='utf-8')
store = (ROOT / 'data' / 'store.json').read_text(encoding='utf-8')
geo = json.loads((ROOT / 'data' / 'geo.json').read_text(encoding='utf-8'))
sim = (ROOT / 'data' / 'sim.json').read_text(encoding='utf-8')
for g in geo['sgg']:                               # 화면에서 쓰지 않는 항목 제거
    g.pop('cx', None); g.pop('cy', None)
out = (tpl.replace('/*__STORE__*/null', store)
          .replace('/*__GEO__*/null', json.dumps(geo, ensure_ascii=False, separators=(',', ':')))
          .replace('/*__SIM__*/null', sim))
assert '/*__' not in out, '자리표시자 잔존'
dst = ROOT / '사회보장행정데이터_대시보드.html'
dst.write_text(out, encoding='utf-8')
print(f'{dst.name}: {dst.stat().st_size / 1e6:.2f} MB')

# 국민용 요약 화면: 공개용 집계표(전국·시도·연령대, 최소 30건)와 시도 경계만 넣는다.
pub = (ROOT / 'data' / 'store_public.json').read_text(encoding='utf-8')
geo_pub = dict(geo, sgg=[])
out2 = (tpl.replace('/*__STORE__*/null', pub)
           .replace('/*__GEO__*/null', json.dumps(geo_pub, ensure_ascii=False, separators=(',', ':')))
           .replace('/*__SIM__*/null', 'null'))
d2 = ROOT / '사례3_국민' / '한눈에_보는_사회보장.html'
d2.parent.mkdir(exist_ok=True)
d2.write_text(out2, encoding='utf-8')
print(f'{d2.name}: {d2.stat().st_size / 1e6:.2f} MB')

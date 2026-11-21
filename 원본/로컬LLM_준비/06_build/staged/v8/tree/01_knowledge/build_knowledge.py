#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지식 자료 생성 — 코드북·생성 규칙·경계 자료에서 AI 분석 지원이 참조할 자료를 만든다.

입력  work/registry/codebook.json(변수 993개), work/registry/blocks.json(블록 29개),
      work/tools/consistency.py(정합성·자격 규칙 25개), 개발용 대역 자료(값 유무 확인),
      적용사례/data/geo.json(시도 경계)
출력  variables.jsonl          변수 사전(기계 판독): 변수명·한글명·사업·단위·코드값·추출 대상·등급·값 유무
      variable_cards.jsonl     검색용 변수 카드(변수 1개 = 문서 1개)
      program_cards.jsonl      사업별 카드(사업 1개 = 문서 1개, 소속 변수와 접미어 뜻)
      rules.jsonl              제도 자격·정합성 규칙
      ../02_library/ssda/data/variables.jsonl, sido_polygons.json   분석 함수 묶음이 읽는 사본

개인 단위 값은 어느 산출물에도 넣지 않는다(값 유무만 확인).
실행  .venv/bin/python 01_knowledge/build_knowledge.py
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = Path('/mnt/share/행정데이터_set/work')
DATA = WORK / 'report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
GEO = WORK / 'report/활용고도화전략/적용사례/data/geo.json'
LIB = ROOT / '02_library' / 'ssda' / 'data'

S1 = ('dis', 'disp', 'disvou', 'ltcare', 'nhi', 'aid_medi', 'nbls_medi', 'oldcare')
S2 = ('p', 'h', 'inc', 'labinc', 'dainc', 'binc', 'ybinc', 'fainc', 'othinc', 'pripen', 'pubpen', 'ptax', 'or', 'ee', 'nbls', 'bp', 'itc',
      'evou', 'culvou', 'aid', 'single', 'kua', 'oldwork', 'self', 'rm', 'frm', 'pubedu', 'vetbn')
IDS = {'pid', 'hid'}
SUFFIX = [('_yn1', '연간(1.1.~12.31.) 수급·가입 여부. 해당하면 1, 아니면 결측'), ('_yn2', '12월 기준 수급·가입 여부. 해당하면 1, 아니면 결측'),
          ('_yn', '여부. 해당하면 1, 아니면 결측'), ('_dur', '연간 수급·가입 개월 수(1~12) 또는 일수'), ('_amt', '연간 금액(원)'),
          ('_type', '유형 코드'), ('_cnt', '횟수'), ('_fee', '본인부담금(원)'), ('_subsidy', '공단부담금(원)')]


def grade(v):
    if v in IDS:
        return '제외'
    if v == 'nhi_type':
        return '가'
    pre = v.split('_')[0]
    if any(v.startswith(x + '_') or v == x for x in S1) or pre in S1:
        return '다'
    if pre in S2 or v.endswith('_amt') or 'amt' in v or v.endswith('_fee'):
        return '나'
    return '가'


def clean(s):
    return re.sub(r'\s+', ' ', str(s or '').replace('\n', ' ')).strip()


def main():
    cb = json.loads((WORK / 'registry' / 'codebook.json').read_text(encoding='utf-8'))
    blocks = json.loads((WORK / 'registry' / 'blocks.json').read_text(encoding='utf-8'))
    blk = {v: (b['block'], b['title']) for b in blocks for v in b['vars']}
    df = pd.read_parquet(DATA)
    has = {c: bool(df[c].notna().any()) for c in df.columns}
    nun = {c: int(df[c].nunique()) for c in df.columns if has[c]}

    variables, cards = [], []
    for r in cb:
        v = r['var']
        avail = has.get(v, False)
        rec = {'var': v, 'name_ko': clean(r.get('name_ko')), 'program': clean(r.get('program')), 'org': clean(r.get('org')), 'unit': clean(r.get('unit')),
               'content': clean(r.get('content')), 'scope': clean(r.get('scope')), 'note': clean(r.get('note')), 'labels': r.get('labels') or {},
               'dtype': r.get('dtype', ''), 'grade': grade(v), 'block': blk.get(v, ('', ''))[0], 'block_title': blk.get(v, ('', ''))[1],
               'available': avail, 'n_category': nun.get(v) if avail and nun.get(v, 99) <= 15 else None}
        variables.append(rec)
        suf = next((d for s, d in SUFFIX if v.endswith(s)), '')
        text = (f"변수명: {v}\n한글 이름: {rec['name_ko']}\n사업: {rec['program']} (보유기관: {rec['org']})\n단위: {rec['unit'] or '없음'}\n"
                f"내용: {rec['content']}\n추출 대상·기준 시점: {rec['scope']}\n"
                + (f"코드값: {', '.join(f'{k}={x}' for k, x in rec['labels'].items())}\n" if rec['labels'] else '')
                + (f"접미어 뜻: {suf}\n" if suf else '')
                + f"민감도 등급: {rec['grade']}\n자료에 값이 있는지: {'있음' if avail else '없음(전량 결측 또는 미제공)'}")
        cards.append({'id': 'var:' + v, 'kind': 'variable', 'title': f"{rec['name_ko']} ({v})", 'text': text})

    prog = {}
    for r in variables:
        prog.setdefault(r['program'] or '기타', []).append(r)
    pcards = []
    for name, rs in prog.items():
        av = [r for r in rs if r['available']]
        lines = [f"{r['var']}: {r['name_ko']}" + (f" [{r['unit']}]" if r['unit'] else '') + ('' if r['available'] else ' (값 없음)') for r in rs]
        pcards.append({'id': 'prog:' + name, 'kind': 'program', 'title': f'사업: {name}',
                       'text': f"사업: {name}\n보유기관: {rs[0]['org']}\n변수 {len(rs)}개(값 있는 변수 {len(av)}개)\n" + '\n'.join(lines)})

    spec = importlib.util.spec_from_file_location('consistency', WORK / 'tools' / 'consistency.py')
    sys.path.insert(0, str(WORK / 'tools'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rules = [{'id': 'rule:' + r['id'], 'kind': 'rule', 'title': f"규칙 {r['id']} ({r['area']})", 'text': f"영역: {r['area']}\n규칙: {r['desc']}"} for r in mod.RULES]

    # 문서 카드: docs/*.md 를 「## 」 절 단위로 나눈다(함수 설명서·통제 규칙·분석 요령·그림 기준·자료 규약)
    dcards = []
    for md in sorted((HERE / 'docs').glob('*.md')):
        txt = md.read_text(encoding='utf-8')
        top = re.match(r'#\s+(.*)', txt).group(1).strip()
        for i, sec in enumerate(re.split(r'\n(?=## )', txt)[1:]):
            head, _, body = sec.partition('\n')
            dcards.append({'id': f'doc:{md.stem}:{i + 1}', 'kind': 'doc', 'title': f"{top} — {head.replace('## ', '').strip()}", 'text': body.strip()})

    for path, rows in ((HERE / 'variables.jsonl', variables), (HERE / 'variable_cards.jsonl', cards), (HERE / 'program_cards.jsonl', pcards), (HERE / 'rules.jsonl', rules), (HERE / 'doc_cards.jsonl', dcards)):
        path.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows) + '\n', encoding='utf-8')
    LIB.mkdir(parents=True, exist_ok=True)
    (LIB / 'variables.jsonl').write_text((HERE / 'variables.jsonl').read_text(encoding='utf-8'), encoding='utf-8')

    # 시도 경계(그림용): SVG 경로 → 다각형 좌표
    geo = json.loads(GEO.read_text(encoding='utf-8'))
    short = {'서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천', '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산',
             '세종특별자치시': '세종', '경기도': '경기', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남', '전북특별자치도': '전북', '전라남도': '전남',
             '경상북도': '경북', '경상남도': '경남', '제주특별자치도': '제주'}
    polys, center = {}, {}
    for g in geo['sido']:
        nm = short[g['props']['sidonm']]
        rings = []
        for part in g['d'].split('Z'):
            pts = [tuple(float(a) for a in t.split(',')) for t in part.replace('M', '').split('L') if ',' in t]
            if len(pts) >= 3:
                rings.append(pts)
        polys[nm] = rings; center[nm] = [g['cx'], g['cy']]
    (LIB / 'sido_polygons.json').write_text(json.dumps({'sido': polys, 'center': center, 'xlim': [60, geo['w']], 'ylim': [0, geo['h']], 'source': geo.get('source', '')},
                                                       ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    g = pd.Series([r['grade'] for r in variables]).value_counts().to_dict()
    print(f'변수 {len(variables)}개(값 있음 {sum(r["available"] for r in variables)}개) · 등급 {g} · 사업 카드 {len(pcards)}개 · 규칙 {len(rules)}개 · 문서 카드 {len(dcards)}개')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""코드북 파서: 993개 변수를 구조화 JSON으로. 값 레이블·단위·추출대상 파싱 포함."""
import openpyxl, json, re, os, sys

XLSX = "/mnt/share/행정데이터_set/작업안내/(코드북) 3기_사회보장행정데이터_V3.1_코드북_결합데이터셋(2022년 기준, 260206).xlsx"

def norm(s):
    return re.sub(r'[ \t]+', ' ', (s or '').replace('\xa0', ' ')).strip()

LABEL_RE = re.compile(r'^\s*(.+?)\s*[:：]\s*(-?\d+)\s*$')

def parse_labels(content):
    """'- 남성: 1 / 여성: 2' 형태의 값 레이블을 {code: label} 로. 줄 단위 → '/' 분할."""
    out = {}
    if not content: return out
    for line in str(content).split('\n'):
        line = norm(line)
        line = re.sub(r'^[\-\u25b7\u25b6\u25cf\u25cb\u00b7\u203b\s]+', '', line)
        if not line: continue
        for sep in ('/', ','):
            parts = [x for x in line.split(sep) if x.strip()]
            if len(parts) > 1: break
        hits = []
        for part in parts:
            m = LABEL_RE.match(part.strip())
            if m:
                lab = m.group(1).strip()
                lab = re.sub(r'^[\-\u25b7\u25b6\u25cf\u25cb\u00b7\u203b\s]+', '', lab).strip()
                if lab and len(lab) <= 80:
                    hits.append((int(m.group(2)), lab))
        # 레이블 줄로 인정: 분할 조각의 과반이 'label: code' 형태
        if hits and len(hits) >= max(1, len(parts) * 0.6):
            for code, lab in hits:
                out.setdefault(code, lab)
    return out

def parse_unnumbered(content):
    """코드 없이 '/'로 나열된 범주 (예: 가족반대 / 건강악화 / ...) → 순번 코드 부여용 목록."""
    if not content: return []
    best = []
    for line in str(content).split('\n'):
        line = norm(line)
        line = re.sub(r'^[\-\u25b7\u25b6\u25cf\u25cb\u00b7\u203b\s]+', '', line)
        if ':' in line or '：' in line: continue
        parts = [x.strip() for x in line.split('/') if x.strip()]
        if len(parts) >= 3 and all(0 < len(x) <= 40 for x in parts):
            if len(parts) > len(best): best = parts
    return best


def infer_type(v):
    unit, content, name = v['unit'], v['content'], v['var']
    if v['labels'] or v.get('categories_unnumbered'):
        return 'categorical'
    if unit in ('원',): return 'amount'
    if unit in ('개월', '일', '회', '명', '년', '세', '건', '시간', '점'): return 'count'
    if re.search(r'(_yn\d?|_yn$)', name): return 'binary'
    if re.search(r'_(amt|fee|subsidy|sum|inc|tax|balance|amount|total|bal|score|size|deposit|rent)\d?', name): return 'amount'
    if re.search(r'_(dur|freq|num|cnt|day|hmember|n)\d?', name): return 'count'
    if re.search(r'_(type|reason|status|grade|law|code)\d?', name): return 'categorical'
    return 'numeric'

def load():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb['코드북']
    rows = list(ws.iter_rows(values_only=True))
    hdr = [norm(str(c or '')) for c in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    out = []
    for r in rows[1:]:
        if r is None: continue
        g = lambda k: norm(str(r[idx[k]])) if idx.get(k) is not None and r[idx[k]] is not None else ''
        var = g('변수명(영문)')
        if not var: continue
        raw_content = str(r[idx['변수 내용']]) if r[idx['변수 내용']] is not None else ''
        rec = {
            'var': var,
            'org': g('정보보유기관'),
            'program': g('사업명'),
            'name_ko': g('변수명(한글)'),
            'unit': g('단위'),
            'content': raw_content,
            'scope': str(r[idx['추출대상 및 기준시점']]) if r[idx['추출대상 및 기준시점']] is not None else '',
            'note': g('비고'),
        }
        rec['labels'] = parse_labels(raw_content)
        rec['categories_unnumbered'] = [] if rec['labels'] else parse_unnumbered(raw_content)
        rec['dtype'] = infer_type(rec)
        out.append(rec)
    # 붙임 시트
    attach = {}
    for sh in wb.sheetnames:
        if sh.startswith('(붙임)'):
            a = [[('' if c is None else str(c)) for c in row] for row in wb[sh].iter_rows(values_only=True)]
            attach[sh] = a
    return out, attach

if __name__ == '__main__':
    vs, at = load()
    os.makedirs('registry', exist_ok=True)
    json.dump(vs, open('registry/codebook.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(at, open('registry/codebook_attach.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    from collections import Counter
    print('vars', len(vs), Counter(v['dtype'] for v in vs))
    print('with labels', sum(1 for v in vs if v['labels']))
    print('attach sheets', {k: len(v) for k, v in at.items()})

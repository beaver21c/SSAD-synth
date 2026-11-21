# -*- coding: utf-8 -*-
"""한국 통계 PDF 표 추출 도우미 (pymupdf).
- find_pages(pdf, pattern): 표제목/표번호로 페이지 찾기
- page_text(pdf, i): 레이아웃 보존 텍스트
- page_words_grid(pdf, i): 단어 좌표 → 행/열 클러스터링으로 표 복원
- tables_native(pdf, i): pymupdf 내장 표 검출
"""
import re, sys, json
import pymupdf as fitz

def open_doc(p): return fitz.open(p)

def find_pages(pdf, pattern, flags=re.I, limit=None):
    d = pdf if hasattr(pdf, 'page_count') else fitz.open(pdf)
    rx = re.compile(pattern, flags); hits = []
    for i in range(d.page_count):
        t = d[i].get_text()
        if rx.search(t):
            hits.append({'page': i, 'page_1based': i + 1,
                         'snippet': re.sub(r'\s+', ' ', t)[:200]})
            if limit and len(hits) >= limit: break
    return hits

def page_text(pdf, i, mode='text'):
    d = pdf if hasattr(pdf, 'page_count') else fitz.open(pdf)
    return d[i].get_text(mode)

def tables_native(pdf, i):
    d = pdf if hasattr(pdf, 'page_count') else fitz.open(pdf)
    try:
        tf = d[i].find_tables()
    except Exception:
        return []
    return [t.extract() for t in tf.tables]

def page_words_grid(pdf, i, ytol=3.0, xgap=6.0):
    """단어 좌표 기반 표 복원. 반환: list[list[str]] (행 × 열)"""
    d = pdf if hasattr(pdf, 'page_count') else fitz.open(pdf)
    ws = d[i].get_text('words')  # x0,y0,x1,y1,word,block,line,wordno
    if not ws: return []
    ws.sort(key=lambda w: (round(w[1] / ytol), w[0]))
    rows, cur, cy = [], [], None
    for w in ws:
        if cy is None or abs(w[1] - cy) <= ytol:
            cur.append(w); cy = w[1] if cy is None else cy
        else:
            rows.append(cur); cur = [w]; cy = w[1]
    if cur: rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda w: w[0])
        cells, buf, lastx1 = [], [], None
        for w in r:
            if lastx1 is not None and w[0] - lastx1 > xgap:
                cells.append(' '.join(buf)); buf = []
            buf.append(w[4]); lastx1 = w[2]
        if buf: cells.append(' '.join(buf))
        out.append(cells)
    return out

NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?$')
def tonum(s):
    s = (s or '').strip().replace(',', '').replace('−', '-')
    if s in ('-', '–', '', '·', 'X', 'x'): return None
    try: return float(s) if '.' in s else int(s)
    except ValueError: return None

def toc(pdf, max_pages=40, pattern=r'(표|Table)\s*[\dⅠ-ⅩIVX]+[\s\-–.]'):
    """앞부분에서 표 목차 라인 수집."""
    d = pdf if hasattr(pdf, 'page_count') else fitz.open(pdf)
    rx = re.compile(pattern); out = []
    for i in range(min(max_pages, d.page_count)):
        for ln in d[i].get_text().split('\n'):
            ln = ln.strip()
            if rx.search(ln) and len(ln) < 200: out.append({'page': i + 1, 'line': ln})
    return out

if __name__ == '__main__':
    p = sys.argv[1]; d = fitz.open(p)
    if len(sys.argv) > 2 and sys.argv[2] == 'toc':
        for r in toc(d, int(sys.argv[3]) if len(sys.argv) > 3 else 40): print(r['page'], r['line'])
    elif len(sys.argv) > 3 and sys.argv[2] == 'find':
        for r in find_pages(d, sys.argv[3]): print(r['page_1based'], r['snippet'][:150])
    elif len(sys.argv) > 3 and sys.argv[2] == 'page':
        print(page_text(d, int(sys.argv[3]) - 1))
    else:
        print('pages', d.page_count)

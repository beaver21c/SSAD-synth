"""좌표 기반 PDF 표 전사 유틸 (지방세통계연감 등 시도별 표)."""
import re, pymupdf

def numrows(page, y0, y1, x0=0, x1=10000):
    ws = [w for w in page.get_text('words')
          if y0 < (w[1]+w[3])/2 < y1 and x0 <= w[2] <= x1
          and re.fullmatch(r'[\d,]+(\.\d+)?', w[4]) and any(c.isdigit() for c in w[4])]
    ws.sort(key=lambda w: ((w[1]+w[3])/2, w[0]))
    rows = []
    for w in ws:
        yc = (w[1]+w[3])/2
        if rows and abs(yc - rows[-1][0]) < 4.0:
            rows[-1][1].append(w); rows[-1][0] = (rows[-1][0]*(len(rows[-1][1])-1)+yc)/len(rows[-1][1])
        else:
            rows.append([yc, [w]])
    return [(y, sorted(r, key=lambda w: w[2])) for y, r in rows]

def to_grid(rows, tol=8.0):
    """열 중심을 오른쪽 정렬 x1 기준으로 군집화 → 행×열 격자."""
    xs = sorted(w[2] for _, r in rows for w in r)
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] < tol: cols[-1].append(x)
        else: cols.append([x])
    centers = [sum(c)/len(c) for c in cols]
    grid = []
    for y, r in rows:
        cells = [''] * len(centers)
        for w in r:
            j = min(range(len(centers)), key=lambda k: abs(centers[k]-w[2]))
            cells[j] = (cells[j] + w[4]) if cells[j] else w[4]
        grid.append(cells)
    return centers, grid

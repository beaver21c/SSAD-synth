"""가계금융복지조사 통계표 xlsx → tidy CSV"""
import openpyxl, csv, re, sys

def filled(ws, nrow, ncol):
    """merged range 값을 전 셀에 채운 2차원 배열 반환"""
    g = [[ws.cell(r, c).value for c in range(1, ncol+1)] for r in range(1, nrow+1)]
    for mr in ws.merged_cells.ranges:
        v = ws.cell(mr.min_row, mr.min_col).value
        for r in range(mr.min_row, mr.max_row+1):
            for c in range(mr.min_col, mr.max_col+1):
                if r <= nrow and c <= ncol:
                    g[r-1][c-1] = v
    return g

def clean(v):
    if v is None: return ''
    s = str(v).replace('\n', ' ').strip()
    return re.sub(r'\s+', ' ', s)

def run(path, sheet, hdr_rows, data_rows, label_cols, first_data_col, out, value_name='값'):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet]
    g = filled(ws, ws.max_row, ws.max_column)
    rows = []
    for r in data_rows:
        labels = [clean(g[r-1][c-1]) for c in label_cols]
        if not any(labels): continue
        for c in range(first_data_col, ws.max_column+1):
            v = g[r-1][c-1]
            if v is None or clean(v) == '': continue
            hdr = [clean(g[hr-1][c-1]) for hr in hdr_rows]
            hdr = [h for h in hdr if h]
            ded = []
            for h in hdr:
                if not ded or ded[-1] != h: ded.append(h)
            tbl = ded[0] if ded and re.match(r'^\d+\.', ded[0]) else ''
            if tbl: ded = ded[1:]
            rows.append(labels + [tbl, '|'.join(ded), clean(v)])
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['구분1', '구분2'][:len(label_cols)] + ['표', '항목', value_name])
        w.writerows(rows)
    return len(rows)

if __name__ == '__main__':
    P = 'params/raw/PROP_가계금융복지조사2022_통계표.xlsx'
    n = run(P, '통계표1~10', [1,4,5,6,7,8,9], range(10,48), [1,2], 3,
            'params/raw/PROP_GFS2022_표1-10_가구특성별자산부채소득.csv')
    print('표1~10', n)
    n = run(P, '통계표 11', [1,3,4,5], range(6,48), [1,2], 3,
            'params/raw/PROP_GFS2022_표11_소득원천별가구소득.csv')
    print('표11', n)
    n = run(P, '통계표 12', [1,2,3], range(4,31), [1,2], 3,
            'params/raw/PROP_GFS2022_표12_순자산가구소득분위.csv')
    print('표12', n)
    n = run(P, "통계표13", [1,3,4,5,6], range(6,51), [1,2], 3,
            'params/raw/PROP_GFS2022_표13_소득분배지표.csv')
    print('표13', n)

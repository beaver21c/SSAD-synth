"""EIS 고용보험통계표 xlsx -> tidy long CSV (전사 전용, 값 가공 없음)."""
import openpyxl, csv, re, os, sys

def grid(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    g = []
    for r in ws.iter_rows(values_only=True):
        g.append(['' if x is None else (x if isinstance(x,(int,float)) else str(x).strip()) for x in r])
    wb.close()
    return g

def clean(s):
    return re.sub(r'\s+', ' ', str(s)).strip()

def flat(path, sheet, hdr_rows, idx_cols, data_row0, out, idx_names, val_names,
         sub_hdr=None, ncols=None, ffill_cols=None, stop_on_blank=True):
    """hdr_rows: list of 0-based row idx for column headers (merged handled by ffill).
       idx_cols: number of leading label columns.
       val_names: names for the header levels, len == len(hdr_rows)."""
    g = grid(path, sheet)
    W = max(len(r) for r in g)
    for r in g: r.extend([''] * (W - len(r)))
    if ncols is None: ncols = W
    # forward-fill header rows horizontally
    heads = []
    for hr in hdr_rows:
        row = list(g[hr]); last = ''
        for j in range(len(row)):
            v = clean(row[j])
            if v: last = v
            row[j] = last
        heads.append(row)
    rows = []
    ffill_cols = ffill_cols if ffill_cols is not None else list(range(idx_cols))
    carry = {c: '' for c in ffill_cols}
    for i in range(data_row0, len(g)):
        rr = g[i]
        labs = []
        for c in range(idx_cols):
            v = clean(rr[c]) if c < len(rr) else ''
            if c in carry:
                if v: carry[c] = v
                v = carry[c]
            labs.append(v)
        if all(l == '' for l in labs):
            continue
        anyval = False
        for j in range(idx_cols, ncols):
            v = rr[j]
            if v == '' or v is None: continue
            if not isinstance(v, (int, float)):
                continue
            anyval = True
            rec = dict(zip(idx_names, labs))
            for k, hn in enumerate(val_names):
                rec[hn] = clean(heads[k][j])
            rec['value'] = v
            rows.append(rec)
        if not anyval and stop_on_blank and all(not clean(x) for x in rr[idx_cols:ncols]):
            continue
    cols = list(idx_names) + list(val_names) + ['value']
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows: w.writerow(r)
    return len(rows)

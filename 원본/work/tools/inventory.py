# -*- coding: utf-8 -*-
"""params/raw 인벤토리: 파일별 형식·크기·행수·컬럼/페이지수 요약 → registry/raw_inventory.csv"""
import os, csv, zipfile, json, sys, re
ROOT='params/raw'
def sniff(p):
    ext=os.path.splitext(p)[1].lower().lstrip('.')
    sz=os.path.getsize(p); info={'ext':ext,'bytes':sz,'rows':'','cols':'','note':''}
    try:
        if ext=='csv':
            for enc in ('utf-8-sig','cp949','utf-8'):
                try:
                    with open(p,encoding=enc) as f:
                        rd=csv.reader(f); hdr=next(rd,[]); n=sum(1 for _ in rd)
                    info.update(rows=n, cols='|'.join(hdr[:12]), note=f'enc={enc}'); break
                except Exception: continue
        elif ext in ('xlsx','xls','xlsm'):
            import openpyxl
            wb=openpyxl.load_workbook(p, read_only=True); 
            info.update(rows=sum(ws.max_row or 0 for ws in wb.worksheets),
                        cols='|'.join(wb.sheetnames[:12]), note=f'{len(wb.sheetnames)} sheets')
        elif ext=='pdf':
            import pymupdf as fitz
            d=fitz.open(p); txt=len(d[0].get_text() or '')+len(d[min(5,d.page_count-1)].get_text() or '')
            info.update(rows=d.page_count, note=f'textlayer={"Y" if txt>50 else "N"}')
        elif ext=='zip':
            z=zipfile.ZipFile(p); nm=z.namelist()
            info.update(rows=len(nm), cols='|'.join(nm[:8]))
        elif ext in ('hwpx','hwp'):
            info.update(note='hwp(x)')
        elif ext=='json':
            j=json.load(open(p,encoding='utf-8'))
            info.update(rows=len(j) if isinstance(j,(list,dict)) else '')
    except Exception as e:
        info['note']=f'ERR {type(e).__name__}: {str(e)[:60]}'
    # HTML 오류 페이지 위장 검사
    try:
        with open(p,'rb') as f: head=f.read(400)
        if b'<!DOCTYPE' in head or b'<html' in head.lower():
            info['note']=(info['note']+' | **HTML(오류페이지 의심)**').strip(' |')
    except Exception: pass
    return info

def main():
    rows=[]
    for dp,_,fns in os.walk(ROOT):
        for fn in sorted(fns):
            p=os.path.join(dp,fn)
            r={'path':p,'name':fn}; r.update(sniff(p)); rows.append(r)
    os.makedirs('registry',exist_ok=True)
    with open('registry/raw_inventory.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['path','name','ext','bytes','rows','cols','note']); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(len(rows),'files', dict(Counter(r['ext'] for r in rows)))
    bad=[r for r in rows if 'HTML' in r['note'] or r['note'].startswith('ERR')]
    print('suspect:',len(bad))
    for r in bad[:20]: print('  ',r['name'][:70],'|',r['note'][:60])
main()

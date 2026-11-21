import openpyxl,sys
f,sh=sys.argv[1],sys.argv[2]
r0=int(sys.argv[3]) if len(sys.argv)>3 else 1
r1=int(sys.argv[4]) if len(sys.argv)>4 else 40
c1=int(sys.argv[5]) if len(sys.argv)>5 else 30
wb=openpyxl.load_workbook(f,data_only=True)
ws=wb[sh]
print('dims',ws.max_row,ws.max_column)
for i,row in enumerate(ws.iter_rows(min_row=r0,max_row=min(r1,ws.max_row),max_col=c1,values_only=True),start=r0):
    cells=[]
    for j,v in enumerate(row,start=1):
        if v is None: continue
        s=str(v).strip().replace('\n',' ')
        if s: cells.append(f'{j}:{s[:26]}')
    print(i,'||',' | '.join(cells))

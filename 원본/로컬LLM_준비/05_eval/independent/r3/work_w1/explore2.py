import pandas as pd, numpy as np, sys
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
cb=pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv',sep='\t')
pd.set_option('display.width',250); pd.set_option('display.max_rows',600)
rows=[]
for v,dt,pr in zip(cb['var'],cb['dtype'],cb['priority']):
    s=df[v]
    if s.dtype==object or str(s.dtype) in('str','string'):
        rows.append((v,dt,pr,s.notna().sum(),'str',s.nunique(),'','','','')); continue
    nn=s.notna().sum(); n1=(s==1).sum(); n0=(s==0).sum(); npos=(s>0).sum(); nneg=(s<0).sum()
    q=s[s>0].quantile([.1,.5,.9]).round(0).tolist() if npos>0 else ['','','']
    rows.append((v,dt,pr if isinstance(pr,str) else '',nn,n1,n0,npos,nneg,s.nunique(),q))
out=pd.DataFrame(rows,columns=['var','dtype','P','notna','eq1','eq0','pos','neg','nuniq','q10_50_90_pos'])
print(out.to_string())

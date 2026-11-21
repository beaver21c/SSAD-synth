import os, json, sys, traceback
sys.path.insert(0, os.path.dirname(__file__))
from dgk import DGK
TARGETS = [
 ("R07","15009571","2022"), ("R08a","15009570","2022"), ("R08b","15062447","2022"),
 ("R09","3084474","2022"),  ("R10","15066574","2022"), ("R11","15122295","2022"),
 ("R12","15113453","2022"), ("R13","15103019","2022"), ("R15","15005662","2022"),
 ("R16a","15052969","2022"),("R16b","15054094","2022"),("R16c","15110984","2022"),
]
g = DGK(); out=[]
os.makedirs("params/raw", exist_ok=True)
for code, pk, yr in TARGETS:
    rec={"code":code,"pk":pk}
    try:
        r=g.get_year(pk, yr, "params/raw")
        rec.update(r)
        if not r["saved"]:
            # fall back to latest available file
            try:
                d=g.detail(pk)
                if d["atchFileId"]:
                    p=f"params/raw/{pk}_latest.csv"
                    n=g.download(d["atchFileId"], d["fileDetailSn"], p, referer=d["url"])
                    rec["saved"]=[{"path":p,"bytes":n,"name":d["title"],"ext":"?","fallback":"latest"}]
            except Exception as e: rec["fallback_err"]=str(e)
    except Exception as e:
        rec["error"]=f"{type(e).__name__}: {e}"
    out.append(rec)
    print(json.dumps(rec, ensure_ascii=False)[:600], flush=True)
json.dump(out, open("registry/dgk_fetch.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)

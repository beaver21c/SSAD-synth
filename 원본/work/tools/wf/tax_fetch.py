import sys, os, json, csv, time
sys.path.insert(0, '/mnt/share/행정데이터_set/work/tools')
from tasis import TASIS, tidy

RAW = '/mnt/share/행정데이터_set/work/params/raw'
SCR = '/tmp/claude-1000/-mnt-share-------set/997344f3-c3c8-45c7-83b6-719b8a3d1d3b/scratchpad'
os.makedirs(RAW, exist_ok=True)

# (표번호, 설명slug, STTS_MTA_INFR_ID, 발행연도)
TARGETS = [
 ("4-2-3",  "근로소득연말정산III_성연령",        "20230103D01202347655", 2023),
 ("4-2-4",  "근로소득연말정산IV_과세대상근로소득구간","20230103D01202347656", 2023),
 ("4-2-5",  "근로소득연말정산V_근로소득금액",     "20230103D01202347657", 2023),
 ("3-2-2",  "성별종합소득규모별주요항목",         "20230103C01202348027", 2023),
 ("3-2-3",  "소득종류별종합소득금액",            "20230103C01202348028", 2023),
 ("3-1-3",  "종합소득총수입금액에서납부세액I_신고유형주소지성연령","20230103C01202348003", 2023),
 ("3-1-4",  "종합소득총수입금액에서납부세액II_종합소득과세표준","20230103C01202348004", 2023),
 ("3-3-2",  "주소지별종합소득세확정신고인원",      "20230103C01202348061", 2023),
 ("3-1-5",  "금융소득종합과세신고자_종합소득금액", "20230103C01202348005", 2023),
 ("14-3-1", "근로자녀장려금지급_성가구유형연령자녀수","20230103N01202347779", 2023),
 ("14-3-16","연령별근로장려금지급_총급여액지급규모","20230103N01202347798", 2023),
 ("14-3-32","가구유형별근로장려금지급III_연령주소지","20230103N01202347820", 2023),
 ("14-3-33","가구유형별자녀장려금지급III_연령주소지","20230103N01202347821", 2023),
 ("4-4-6",  "거주자사업소득원천징수신고",         "20230103D01202347679", 2023),
 ("4-4-8",  "거주자기타소득원천징수신고",         "20230103D01202347681", 2023),
 ("4-4-9",  "일용근로소득지급명세서제출",         "20230103D01202327682", 2023),
 ("4-4-10", "일용근로소득자별지급명세서제출",      "20230103D01202327683", 2023),
 ("4-3-1",  "사업소득연말정산I_총괄",            "20230103D01202347670", 2023),
 ("4-3-2",  "사업소득연말정산II_원천징수지성연령", "20230103D01202347671", 2023),
]

t = TASIS()
report = []
for num, slug, mid, yr in TARGETS:
    base = f"NTS_{num}_{slug}"
    jp = os.path.join(RAW, base + ".json")
    cp = os.path.join(RAW, base + ".csv")
    try:
        doc = t.table(yr, mid)
        if doc.get("result") != "S" or not doc.get("dc_annRptList"):
            report.append({"num": num, "ok": False, "err": f"result={doc.get('result')} rows=0", "mta": mid, "yr": yr})
            print("FAIL", num, doc.get("result"), doc.get("message")); continue
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        meta, cols, rows = tidy(doc)
        with open(cp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
        yrs = sorted({str(r.get("COL6","")) for r in doc["dc_annRptList"] if r.get("COL6")})
        report.append({"num": num, "ok": True, "mta": mid, "pbl_yr": yr, "title": meta["sttsSbj"],
                       "unit": meta["unit"], "n": len(rows), "rowCnt": meta["rowCnt"], "colCnt": meta["colCnt"],
                       "attr_yrs": yrs, "json": jp, "csv": cp,
                       "json_bytes": os.path.getsize(jp), "csv_bytes": os.path.getsize(cp)})
        print("OK", num, meta["sttsSbj"], "| rows", len(rows), "| 귀속", yrs, "| unit", meta["unit"])
    except Exception as e:
        report.append({"num": num, "ok": False, "err": repr(e), "mta": mid, "yr": yr})
        print("ERR", num, repr(e))
    time.sleep(0.6)

json.dump({"report": report, "http_log": t.log}, open(os.path.join(SCR, "tax_fetch_report.json"), "w"), ensure_ascii=False, indent=1)

"""TASIS(국세통계포털) 내부 JSON API 클라이언트.
목록: /wqAction.do?actionId=ATWEPEAA001R01  (dc_search: STT_PBL_YR, STTS_PBL_TYPE_CD)
표  : /wqAction.do?actionId=ATWEPEAA001R02  (dc_search: STT_PBL_YR, STTS_MTA_INFR_ID, MENU_ID, LANG)
"""
import json, os, re, time
import requests

BASE = "https://tasis.nts.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Content-Type": "application/json; charset=UTF-8",
      "Referer": BASE + "/websquare/websquare.html?w2xPath=/cm/index.xml",
      "Accept-Language": "ko-KR,ko;q=0.9"}
YEAR_TYPES = "F,S,Q,U,N,C,1,2,3,4"

class TASIS:
    def __init__(self):
        self.s = requests.Session(); self.s.headers.update(UA)
        self.log = []

    def _post(self, actionId, payload, timeout=180):
        url = f"{BASE}/wqAction.do?actionId={actionId}"
        r = self.s.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=timeout)
        self.log.append({"url": url, "payload": payload, "http": r.status_code, "bytes": len(r.content)})
        r.raise_for_status()
        return r.json()

    def catalog(self, pbl_yr):
        d = self._post("ATWEPEAA001R01", {"dc_search": {"STT_PBL_YR": str(pbl_yr),
                                                        "STTS_PBL_TYPE_CD": YEAR_TYPES}})
        return d.get("dc_annRptCtlList", [])

    def table(self, pbl_yr, mta_id, menu_id="43"):
        return self._post("ATWEPEAA001R02", {"dc_search": {
            "STT_PBL_YR": str(pbl_yr), "STTS_MTA_INFR_ID": mta_id, "MENU_ID": menu_id,
            "LANG": "KOR", "STT_ITRF_RTN": [], "STT_ITRF_DCS": [], "STT_ITRF_DCS_RSSM": []}})

def tidy(doc):
    """dc_annRptList -> tidy long rows. ROW*/COL* 라벨 + VAL1 값."""
    res = doc.get("dc_result", {})
    rows_keys = [k for k in str(res.get("rows", "")).split(",") if k]
    rows2_keys = [k for k in str(res.get("rows2", "")).split(",") if k]
    cols_keys = [k for k in str(res.get("cols", "")).split(",") if k]
    lst = doc.get("dc_annRptList", [])
    order = []
    for k in ("ROW1","ROW2","ROW3","ROW4","ROW5","ROW6","ROW7","ROW8","ROW9"):
        if any(str(r.get(k,"") or "") != "" for r in lst): order.append(k)
    for k in ("COL6","COL5","COL4","COL3","COL2","COL1"):
        if any(str(r.get(k,"") or "") != "" for r in lst): order.append(k)
    out = []
    for r in lst:
        rec = {k: r.get(k, "") for k in order}
        rec["VAL"] = r.get("VAL1", "")
        out.append(rec)
    meta = {"sttsSbj": res.get("sttsSbj"), "unit": res.get("STT_UNIT_NM"),
            "rowCnt": res.get("rowCnt"), "colCnt": res.get("colCnt"),
            "cmnt": res.get("sttsCmnt"), "dsc": res.get("sttsDsc"),
            "dept": res.get("STT_PRDC_DPRT_NM"), "cols": cols_keys, "rows": rows_keys+rows2_keys}
    return meta, order + ["VAL"], out

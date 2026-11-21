"""data.go.kr 파일데이터 다운로더 (로그인 불필요).
과거연도 파일: fileData.do -> selectHistAndCsvData.do -> selectDpkDetailInfo.do -> fileDownload.do
"""
import re, sys, os, json, time, html as H
import requests

BASE = "https://www.data.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}

class DGK:
    def __init__(self):
        self.s = requests.Session(); self.s.headers.update(UA)

    def detail(self, pk):
        url = f"{BASE}/data/{pk}/fileData.do"
        r = self.s.get(url, timeout=60); r.raise_for_status()
        h = r.text
        title = re.search(r'<title>(.*?)</title>', h, re.S)
        m = re.search(r"fileDetailObj\.fn_fileDataDown\('(\d+)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", h)
        return {"pk": pk, "url": url, "title": H.unescape(title.group(1)).strip() if title else "",
                "detailPk": m.group(2) if m else None, "atchFileId": m.group(3) if m else None,
                "fileDetailSn": m.group(4) if m else None, "html": h}

    def hist(self, pk, detailPk):
        r = self.s.post(f"{BASE}/tcs/dss/selectHistAndCsvData.do",
                        data={"publicDataPk": pk, "publicDataDetailPk": detailPk},
                        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/data/{pk}/fileData.do"},
                        timeout=60)
        out = []
        for m in re.finditer(r'<a[^>]*openFileDetailPopup[^>]*>(.*?)</a>', r.text, re.S):
            tag, nm = m.group(0), re.sub(r'<[^>]+>', '', m.group(1)).strip()
            p = re.search(r'data-public-pk="([^"]*)"', tag); s = re.search(r'data-public-detail-sn="([^"]*)"', tag)
            if p: out.append({"name": H.unescape(nm), "detailPk": p.group(1), "histSn": s.group(1) if s else "1"})
        return out

    def dpk_files(self, detailPk, histSn):
        r = self.s.post(f"{BASE}/tcs/dss/selectDpkDetailInfo.do",
                        data={"publicDataDetailPk": detailPk, "publicDataHistSn": histSn},
                        headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
        return [{"pk": a, "detailPk": b, "atchFileId": c, "fileDetailSn": d, "ext": e}
                for a, b, c, d, e in re.findall(r"fn_fileDataDown\('([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", r.text)]

    def download(self, atchFileId, fileDetailSn, dest, referer=None):
        r = self.s.get(f"{BASE}/cmm/cmm/fileDownload.do",
                       params={"atchFileId": atchFileId, "fileDetailSn": fileDetailSn, "dataNm": "d"},
                       headers={"Referer": referer or BASE}, timeout=300, stream=True)
        r.raise_for_status()
        n = 0
        with open(dest, "wb") as f:
            for ch in r.iter_content(1 << 16):
                f.write(ch); n += len(ch)
        return n

    def get_year(self, pk, year_token, dest_dir, prefer_ext=("csv", "xlsx", "xls", "zip")):
        """year_token e.g. '2022' or '20221231'. Returns list of saved paths."""
        d = self.detail(pk)
        cands = []
        if d["detailPk"]:
            cands = self.hist(pk, d["detailPk"])
        saved = []
        target = [c for c in cands if year_token in c["name"]]
        if not target and year_token in d["title"]:
            files = [{"atchFileId": d["atchFileId"], "fileDetailSn": d["fileDetailSn"], "ext": "csv", "name": d["title"]}]
            target = [{"name": d["title"], "_files": files}]
        for t in target:
            files = t.get("_files") or self.dpk_files(t["detailPk"], t["histSn"])
            byext = {f["ext"].lower(): f for f in files}
            for ex in prefer_ext:
                if ex in byext:
                    f = byext[ex]
                    safe = re.sub(r'[^\w가-힣.-]+', '_', t["name"])[:120]
                    p = os.path.join(dest_dir, f"{pk}_{safe}.{ex}")
                    n = self.download(f["atchFileId"], f["fileDetailSn"], p, referer=d["url"])
                    saved.append({"path": p, "bytes": n, "name": t["name"], "ext": ex,
                                  "atchFileId": f["atchFileId"], "fileDetailSn": f["fileDetailSn"]})
                    break
        return {"pk": pk, "title": d["title"], "hist": [c["name"] for c in cands], "saved": saved}

if __name__ == "__main__":
    g = DGK(); pk = sys.argv[1]; yr = sys.argv[2] if len(sys.argv) > 2 else "2022"
    out = sys.argv[3] if len(sys.argv) > 3 else "params/raw"
    os.makedirs(out, exist_ok=True)
    print(json.dumps(g.get_year(pk, yr, out), ensure_ascii=False, indent=1))

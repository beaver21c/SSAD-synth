# -*- coding: utf-8 -*-
"""§9 산출물 통합: report/attempts.md · report/assumptions.md · registry/access_check.csv

- attempts.md   : 각 에이전트의 registry/acq_*·ext_*·integrate_*·audit_*·verify_*.md 를 통합
                  (작업지시서 §1.3 "변수 축약·대체는 시도기록 후에만" 요건의 증빙)
- assumptions.md: params/*.yaml 중 [가정]·[미확인]·[논리적추론] 지위 파라미터 대장 + 전량 NULL 변수 부록
- access_check.csv: registry/access_check_*.csv 를 헤더 기준으로 합친 소스 접근 결과 전량
"""
import os, sys, glob, csv, io, json, yaml, re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AC_HDR = ['id', '등급', '기관', '자료', 'url', '접근결과', '형식', '크기', '오류', '확인일']


def _p(*a): return os.path.join(ROOT, *a)


# ──────────────────────────────────────────────────────────── access_check.csv
def access_check():
    """헤더 이름 기준으로 병합한다 (파일마다 열 순서가 달라도 안전)."""
    fs = sorted(glob.glob(_p('registry/access_check_*.csv')))
    rows = []
    for f in fs:
        with open(f, encoding='utf-8') as fh:
            rd = csv.DictReader(fh)
            for r in rd:
                if not any(str(v or '').strip() for v in r.values()): continue
                out = {k: str(r.get(k, '') or '').strip() for k in AC_HDR}
                for k, v in r.items():                       # 규약 밖 열은 오류란에 흡수
                    if k in AC_HDR: continue
                    txt = ' '.join(x for x in v if x) if isinstance(v, list) else str(v or '')
                    if txt.strip():
                        out['오류'] = (out['오류'] + f' | {k or "extra"}={txt.strip()}').strip(' |')
                out['출처파일'] = os.path.basename(f)
                rows.append(out)
    outp = _p('registry/access_check.csv')
    with open(outp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=AC_HDR + ['출처파일'])
        w.writeheader(); w.writerows(rows)
    return outp, len(rows), rows


def _ac_summary(rows):
    """접근결과·등급별 요약 (attempts.md 머리말에 넣는다)."""
    def norm(s):
        s = (s or '').strip()
        if not s: return '(미기재)'
        for k in ('성공', 'OK', '200'):
            if k in s: return '성공'
        for k in ('실패', '404', '403', '로그인', 'JS', '미공개', '인증', 'err', 'ERR', '차단', '없음'):
            if k in s: return '실패'
        return s[:20]
    by_res = Counter(norm(r['접근결과']) for r in rows)
    by_gr = Counter((r['등급'] or '(미기재)').strip() for r in rows)
    by_org = Counter((r['기관'] or '(미기재)').strip() for r in rows)
    return by_res, by_gr, by_org


# ──────────────────────────────────────────────────────────────── attempts.md
SECTIONS = (('registry/acq_*.md', 'A. 소스 확보 시도 (Stage 1)'),
            ('registry/ext_*.md', 'B. 표 전사 시도 (Stage 2)'),
            ('registry/integrate_*.md', 'C. 통합·수정 기록 (Stage 3)'),
            ('registry/audit_*.md', 'D. 적대적 감사'),
            ('registry/verify_*.md', 'E. 전사 검증'))


def attempts():
    _, n_ac, ac = access_check()
    by_res, by_gr, by_org = _ac_summary(ac)
    P = ['# 시도 기록 (attempts.md)\n\n',
         '작업지시서 §1.3 — “변수 축약·대체는 시도기록 후에만” 요건을 충족하기 위한 소스 접근 시도 전량 기록.\n',
         '각 에이전트가 남긴 `registry/acq_*.md` · `ext_*.md` · `integrate_*.md` · `audit_*.md` · `verify_*.md` 를 통합했다.\n',
         '기계 판독용 요약은 `registry/access_check.csv` (총 ', str(n_ac), '행) 에 있다.\n\n']
    P.append('## 0. 접근 시도 요약\n\n')
    P.append(f'- 총 시도 **{n_ac}건** · 기록 파일 {len(set(r["출처파일"] for r in ac))}개\n')
    P.append('- 접근결과: ' + ', '.join(f'{k} {v}건' for k, v in by_res.most_common()) + '\n')
    P.append('- 소스 등급: ' + ', '.join(f'{k} {v}건' for k, v in by_gr.most_common()) + '\n')
    P.append('- 상위 기관: ' + ', '.join(f'{k} {v}' for k, v in by_org.most_common(12)) + '\n\n')
    P.append('> KOSIS OpenAPI 는 인증키 미확보(`err=11`)로 사용하지 못했고, 동일 원천의 **원기관 공표자료(S1)** 로\n'
             '> 대체했다. 등급상 **상향** 대체이므로 §1.1 사다리 규칙 위반이 아니다.\n\n')

    files = {t: sorted(glob.glob(_p(pat))) for pat, t in SECTIONS}
    P.append('## 0-1. 수록 문서\n\n')
    for t, fs in files.items():
        if fs:
            P.append(f'- **{t}** — ' + ', '.join(f'`{os.path.basename(f)}`' for f in fs) + '\n')
    P.append('\n---\n')
    n_doc = 0
    for t, fs in files.items():
        if not fs: continue
        P.append(f'\n## {t}\n')
        for f in fs:
            n_doc += 1
            P.append(f'\n<details><summary><b>{os.path.basename(f)}</b> '
                     f'({os.path.getsize(f):,} bytes)</summary>\n\n')
            P.append(open(f, encoding='utf-8').read())
            P.append('\n</details>\n')
    os.makedirs(_p('report'), exist_ok=True)
    open(_p('report/attempts.md'), 'w', encoding='utf-8').write(''.join(P))
    return _p('report/attempts.md'), n_doc, n_ac


# ───────────────────────────────────────────────────────────── assumptions.md
def _rowtext(v):
    return str(v).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def assumptions():
    rows = []
    for f in sorted(glob.glob(_p('params/*.yaml'))):
        d = yaml.safe_load(open(f, encoding='utf-8')) or {}
        meta = d.get('meta') or {}
        blk = meta.get('block', os.path.basename(f))
        for var, p in (d.get('params') or {}).items():
            p = p or {}
            st = str(p.get('status', ''))
            note = str(p.get('note', '') or '')
            ids = re.findall(r'\[가정\s*([A-Za-z0-9\-]+)\]', note)
            if p.get('assumption_id'): ids = [str(p['assumption_id'])] + ids
            if st in ('가정', '미확인', '논리적추론') or ids:
                rows.append({'블록': blk, '변수': var, '지위': st or '(미기재)',
                             '가정번호': ','.join(dict.fromkeys(ids)),
                             '분포': str((p.get('dist') or {}).get('type', '')),
                             '근거·한계': note[:600]})
    c = Counter(r['지위'] for r in rows)
    byblk = Counter(r['블록'] for r in rows)

    o = io.StringIO()
    o.write('# 가정 대장 (assumptions.md)\n\n')
    o.write('작업지시서 §5 규약 — **지위 없는 수치 사용 금지**. `[미확인]`·`[논리적추론]`·`[가정]` 지위의 '
            '파라미터 전량과 그 근거·한계를 적는다. `[1차확인]`(원문·표번호·수치를 직접 열람) 파라미터는 '
            '`final/codebook_synthetic.xlsx` 의 `소스` 열에서 확인할 수 있다.\n\n')
    o.write(f'총 **{len(rows)}건** — ' + ', '.join(f'{k} {v}건' for k, v in c.most_common()) + '\n\n')
    o.write('## 0. 블록별 건수\n\n| 블록 | 건수 |\n|---|---:|\n')
    for k, v in sorted(byblk.items()):
        o.write(f'| {k} | {v} |\n')
    o.write('\n## 1. 파라미터별 근거·한계\n\n')
    o.write('| 블록 | 변수 | 지위 | 가정번호 | 분포 | 근거·한계 |\n|---|---|---|---|---|---|\n')
    for r in rows:
        o.write('| ' + ' | '.join(_rowtext(r[k]) for k in
                                  ('블록', '변수', '지위', '가정번호', '분포', '근거·한계')) + ' |\n')

    # 부록: 컬럼은 만들었으나 값이 전량 NULL 인 변수 (표본 규모 미달 / 파라미터 미확정)
    app = _allnull_appendix()
    if app: o.write(app)
    os.makedirs(_p('report'), exist_ok=True)
    open(_p('report/assumptions.md'), 'w', encoding='utf-8').write(o.getvalue())
    return _p('report/assumptions.md'), len(rows)


def _allnull_appendix(data=None):
    try:
        import pandas as pd
        src = data or _p('data/stage_all.parquet')
        if not os.path.exists(src): return ''
        df = pd.read_parquet(src)
    except Exception:
        return ''
    cols = [c for c in df.columns if not c.startswith('_') and df[c].isna().all()]
    if not cols: return ''
    P = {}
    for f in sorted(glob.glob(_p('params/*.yaml'))):
        d = yaml.safe_load(open(f, encoding='utf-8')) or {}
        blk = (d.get('meta') or {}).get('block', os.path.basename(f))
        for var, p in (d.get('params') or {}).items():
            P[var] = (blk, str((p or {}).get('status', '')), str((p or {}).get('note', '') or ''))
    o = io.StringIO()
    o.write(f'\n## 2. 부록 — 컬럼은 생성했으나 값이 전량 NULL 인 변수 ({len(cols)}개)\n\n')
    o.write('표본 9,535명 규모에서 기대 수급자가 1명 미만이거나(§4 규모 미달), 단가·인원 파라미터를 '
            '확보하지 못한 변수다. 코드북 구조를 유지하기 위해 컬럼은 남기고 값은 결측으로 두었다.\n\n')
    o.write('| 변수 | 블록 | 지위 | 사유(params note) |\n|---|---|---|---|\n')
    for c in cols:
        blk, st, note = P.get(c, ('', '', ''))
        o.write(f'| {c} | {blk} | {st} | {_rowtext(note[:300])} |\n')
    return o.getvalue()


if __name__ == '__main__':
    a, ndoc, nac = attempts()
    b, nrow = assumptions()
    c, n2, _ = access_check()
    print(json.dumps({'attempts': {'out': a, 'docs': ndoc, 'access_rows': nac,
                                   'bytes': os.path.getsize(a)},
                      'assumptions': {'out': b, 'rows': nrow, 'bytes': os.path.getsize(b)},
                      'access_check': {'out': c, 'rows': n2, 'bytes': os.path.getsize(c)}},
                     ensure_ascii=False, indent=1))

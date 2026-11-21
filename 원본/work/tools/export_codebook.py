# -*- coding: utf-8 -*-
"""final/codebook_synthetic.xlsx (§9 산출물)

원 코드북 993행(8열) 을 그대로 두고 오른쪽에 생성 정보를 덧붙인다.
  생성여부 · 담당블록 · 분포(dist) · 소스 · 주장지위 · 생성조건 · 가정번호 ·
  표본 관측수 · NULL% · 요약통계 · 비고(생성)
시트 2 '생성요약' 에 블록별 커버리지·주장지위 분포를, 시트 3 '주의사항' 에 사용 시 유의점을 넣는다.
"""
import openpyxl, json, os, sys, yaml, glob
import numpy as np, pandas as pd
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX_IN = "/mnt/share/행정데이터_set/작업안내/(코드북) 3기_사회보장행정데이터_V3.1_코드북_결합데이터셋(2022년 기준, 260206).xlsx"
OUT = os.path.join(ROOT, "final/codebook_synthetic.xlsx")
DATA = os.path.join(ROOT, "data/stage_all.parquet")

ADD = ['생성여부', '담당블록', '분포(dist)', '소스', '주장지위', '생성조건', '가정번호',
       '표본 관측수', 'NULL%', '요약통계(생성값)', '비고(생성)']
WIDTH = [22, 9, 40, 40, 11, 32, 10, 11, 8, 34, 34]

CAVEATS = [
    ('1. 가중치 없이 쓰지 말 것',
     '표본은 가구수 비례(PPS) 추출이다. 모수 추정에는 indwgt(개인) 또는 hhwgt(가구, head==1 행)를 반드시 적용한다.'),
    ('2. 시군구 단위 분석 불가',
     '표본 가구가 5개 이하인 시군구가 다수다. 분석 가능한 지역 단위는 sido(17개)까지다. city 는 조건부 생성에만 썼다.'),
    ('3. 시설거주 수급자 제외',
     '원 사회보장행정데이터가 등록센서스 일반가구 표본이라 시설거주자가 빠진다. 생계·의료급여·기초연금 등 '
     '자산조사형 급여의 수급률이 정부 공표 총량보다 낮은 것이 정상이다 (R02 <표 2-20>: 생계급여 수급자 비율 '
     '행정데이터 2.53% vs 정부공표 2.88%, 2021년).'),
    ('4. S0 기준연도가 본 데이터와 다르다',
     '캘리브레이션에 쓴 KIHASA 기초분석 보고서는 R01 = 2020년(1기), R02 = 2021년(2기) 기준이다. '
     '3기(2022년) 기초분석은 미발간이라 1~2년의 연도차가 구조적으로 존재한다. 조건부 구조는 S0 에, '
     '총량·단가는 2022년 원기관 집계(S1)에 맞췄다. 근거: registry/s0_basis_finding.md'),
    ('5. 변수마다 근거 수준이 다르다',
     '이 시트의 [주장지위] 열을 확인할 것. 1차확인 = 원문·표번호·수치 직접 열람 / 논리적추론 = 제도 구조에서 도출 / '
     '가정 = 자료 부재로 명시적 가정(report/assumptions.md) / 미확인 = 자료 미확보.'),
]


def load_params():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'params/*.yaml'))):
        d = yaml.safe_load(open(f, encoding='utf-8')) or {}
        meta = d.get('meta', {}) or {}
        for var, p in (d.get('params') or {}).items():
            out[var] = {'block': meta.get('block'), 'agent': meta.get('agent'),
                        'cond_block': meta.get('conditional_rules', ''), **(p or {})}
    return out


def fmt_dist(p):
    d = p.get('dist') or {}
    if not d.get('type'): return ''
    parts = [str(d['type'])]
    for k, v in d.items():
        if k == 'type': continue
        s = json.dumps(v, ensure_ascii=False)
        parts.append(f"{k}={s if len(s) < 120 else s[:117] + '…'}")
    return '; '.join(parts)


def fmt_src(p):
    s = p.get('source') or {}
    return '; '.join(f"{k}={v}" for k, v in s.items() if v not in (None, '', []))


def fmt_stats(s):
    """생성값 요약: 수치형이면 평균·중앙값·최소·최대, 범주형이면 상위 값."""
    q = s.dropna()
    if not len(q): return ''
    if pd.api.types.is_numeric_dtype(q):
        u = q.nunique()
        if u <= 8:
            vc = q.value_counts().sort_index()
            return ' / '.join(f'{int(k) if float(k).is_integer() else k}:{v}' for k, v in vc.items())
        return (f'평균 {float(q.mean()):,.4g} · 중앙 {float(q.median()):,.4g} · '
                f'최소 {float(q.min()):,.4g} · 최대 {float(q.max()):,.4g} · 고유값 {u}')
    vc = q.astype(str).value_counts().head(5)
    return ' / '.join(f'{k}:{v}' for k, v in vc.items()) + (f' … (고유값 {q.nunique()})' if q.nunique() > 5 else '')


def build(df=None):
    if df is None:
        df = pd.read_parquet(DATA) if os.path.exists(DATA) else pd.DataFrame()
    P = load_params()
    tier12 = set()
    blocks = json.load(open(os.path.join(ROOT, 'registry/blocks.json'), encoding='utf-8'))
    for b in blocks:
        tier12 |= set(b['vars'])

    wb = openpyxl.load_workbook(XLSX_IN)
    ws = wb['코드북']
    hdr = [c.value for c in ws[1]]
    ncol = len(hdr)
    thin = Side(style='thin', color='D9D9D9')
    for i, h in enumerate(ADD):
        c = ws.cell(row=1, column=ncol + 1 + i, value=h)
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
        c.fill = PatternFill('solid', fgColor='DDEBF7')
        c.border = Border(bottom=thin)
    fill_gen = PatternFill('solid', fgColor='E8F3E8')   # 생성(값 있음)
    fill_nul = PatternFill('solid', fgColor='FFF4E0')   # 생성 컬럼이나 전량 NULL
    fill_no = PatternFill('solid', fgColor='F5F5F5')    # 미생성
    vi = hdr.index('변수명(영문)')

    n_gen = n_null = n_t12_miss = n_t3 = 0
    for r in range(2, ws.max_row + 1):
        var = ws.cell(row=r, column=vi + 1).value
        if not var: continue
        var = str(var).strip()
        p = P.get(var) or {}
        in_df = var in df.columns
        s = df[var] if in_df else None
        allnull = bool(in_df and s.isna().all())
        nn = int(s.notna().sum()) if in_df else 0
        pn = round(float(s.isna().mean() * 100), 2) if in_df else 100.0
        if in_df and not allnull:
            gen_txt, f = '생성', fill_gen; n_gen += 1
        elif in_df and allnull:
            gen_txt, f = '생성 컬럼(전량 NULL — 표본 규모 미달/파라미터 미확정)', fill_nul; n_null += 1
        elif var in tier12:
            gen_txt, f = '미생성(Tier1+2, 파라미터 미확정)', fill_no; n_t12_miss += 1
        else:
            gen_txt, f = '미생성(Tier3 — 작업지시서 §8 후속 단계)', fill_no; n_t3 += 1
        vals = [gen_txt, p.get('block', ''), fmt_dist(p), fmt_src(p), p.get('status', '') or ('미확인' if var in tier12 else ''),
                (p.get('condition') or p.get('cond_block') or ''), p.get('assumption_id', ''),
                nn if in_df else '', pn if in_df else '',
                fmt_stats(s) if in_df else '', p.get('note', '')]
        for i, v in enumerate(vals):
            c = ws.cell(row=r, column=ncol + 1 + i, value=v)
            c.fill = f
            c.alignment = Alignment(wrap_text=True, vertical='top')
    for i in range(len(ADD)):
        ws.column_dimensions[get_column_letter(ncol + 1 + i)].width = WIDTH[i]
    ws.freeze_panes = 'D2'

    # ── 시트 2: 생성요약 ────────────────────────────────────────────────────
    if '생성요약' in wb.sheetnames: del wb['생성요약']
    s2 = wb.create_sheet('생성요약', 1)
    stat = {v: str((p or {}).get('status', '미확인')) for v, p in P.items()}
    head = ['블록', '담당', 'order', '제목', '선언변수', '생성(값 있음)', '전량 NULL', '미생성',
            '1차확인', '논리적추론', '가정', '미확인', '미생성 변수']
    s2.append(head)
    for c in s2[1]:
        c.font = Font(bold=True); c.fill = PatternFill('solid', fgColor='DDEBF7')
        c.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
    tot = dict.fromkeys(head[4:12], 0)
    for b in sorted(blocks, key=lambda x: (x['order'], x['agent'], x['block'])):
        vs = b['vars']
        have = [v for v in vs if v in df.columns]
        nulls = [v for v in have if df[v].isna().all()]
        good = [v for v in have if v not in nulls]
        miss = [v for v in vs if v not in df.columns]
        cnt = pd.Series([stat.get(v, '미기재') for v in good]).value_counts().to_dict()
        row = [b['block'], b['agent'], b['order'], b['title'][:40], len(vs), len(good), len(nulls), len(miss),
               cnt.get('1차확인', 0), cnt.get('논리적추론', 0), cnt.get('가정', 0), cnt.get('미확인', 0),
               ', '.join(miss)[:200]]
        s2.append(row)
        for k, v in zip(head[4:12], row[4:12]): tot[k] += v
    s2.append(['합계', '', '', f'Tier1+2 {len(tier12)}변수 / 코드북 전체 {ws.max_row-1}변수'] +
              [tot[k] for k in head[4:12]] + [''])
    for c in s2[s2.max_row]: c.font = Font(bold=True)
    for i, w in enumerate([8, 7, 7, 40, 10, 13, 11, 9, 10, 12, 8, 9, 60], start=1):
        s2.column_dimensions[get_column_letter(i)].width = w
    s2.freeze_panes = 'A2'

    # ── 시트 3: 주의사항 ────────────────────────────────────────────────────
    if '주의사항' in wb.sheetnames: del wb['주의사항']
    s3 = wb.create_sheet('주의사항', 2)
    s3.append(['이 가상데이터를 쓰기 전에 반드시 알아야 할 5가지'])
    s3['A1'].font = Font(bold=True, size=13)
    s3.append([])
    for t, b in CAVEATS:
        s3.append([t, b])
        s3.cell(row=s3.max_row, column=1).font = Font(bold=True)
        s3.cell(row=s3.max_row, column=1).alignment = Alignment(vertical='top', wrap_text=True)
        s3.cell(row=s3.max_row, column=2).alignment = Alignment(vertical='top', wrap_text=True)
    s3.append([])
    s3.append(['소스 등급', 'S0 사회보장행정데이터 기초분석(R01=2020·R02=2021) > S1 원기관 행정집계(2022) > '
                          'S2 KOSIS 승인통계 > S3 패널 > S4 법령 단가. 상위 등급이 있으면 하위로 대체하지 않았다.'])
    s3.append(['난수 seed', 'numpy PCG64, seed = 20220000 + 블록번호. 동일 seed 2회 생성 결과가 완전히 같음을 실행 확인했다.'])
    s3.append(['함께 볼 것', 'report/validation.html · report/assumptions.md · report/attempts.md · '
                          'registry/s0_basis_finding.md · registry/access_check.csv'])
    s3.column_dimensions['A'].width = 30
    s3.column_dimensions['B'].width = 130

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # ── 저장된 스크롤 위치 초기화 ────────────────────────────────────────────
    # 원본 코드북이 sheetView.topLeftCell='G1' 로 저장돼 있어, 그대로 두면 엑셀에서
    # 열자마자 G열부터 보이고 A~F(정보보유기관·사업명·변수명 등)가 화면 밖으로 밀린다.
    from openpyxl.worksheet.views import Selection
    for _ws in wb.worksheets:
        _sv = _ws.sheet_view
        _sv.topLeftCell = 'A1'
        _first = (_ws.title == '코드북')
        _tl, _pane = ('D2', 'bottomRight') if _first else ('A2', 'bottomLeft')
        _ws.freeze_panes = _tl
        if _sv.pane is not None:
            _sv.pane.topLeftCell = _tl
            _sv.pane.activePane = _pane
        _sv.selection = [Selection(pane=_pane, activeCell=_tl, sqref=_tl)]
    wb.active = 0

    wb.save(OUT)
    return {'out': OUT, '생성': n_gen, '전량NULL': n_null,
            'Tier1+2 미생성': n_t12_miss, 'Tier3': n_t3, '코드북 행': ws.max_row - 1}


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else DATA
    print(build(pd.read_parquet(src) if os.path.exists(src) else None))

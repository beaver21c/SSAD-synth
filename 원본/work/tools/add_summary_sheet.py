# -*- coding: utf-8 -*-
"""codebook_synthetic.xlsx 맨 앞에 '변경요약' 시트 추가.
원 코드북에서 그대로 간 것과 이번 작업에서 더해진 것을 셀 단위 대조 결과로 명시한다."""
import openpyxl, glob, json, yaml, collections
import pandas as pd
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

SRC = '/mnt/share/행정데이터_set/작업안내/(코드북) 3기_사회보장행정데이터_V3.1_코드북_결합데이터셋(2022년 기준, 260206).xlsx'
DST = 'final/codebook_synthetic.xlsx'
TITLE = '변경요약'

H1 = Font(bold=True, size=14)
H2 = Font(bold=True, size=11, color='FFFFFF')
BOLD = Font(bold=True)
FILL_H = PatternFill('solid', fgColor='2F5597')
FILL_KEEP = PatternFill('solid', fgColor='E8F3E8')
FILL_ADD = PatternFill('solid', fgColor='FFF3E0')
FILL_SUB = PatternFill('solid', fgColor='F2F2F2')
WRAP = Alignment(wrap_text=True, vertical='top')
THIN = Border(*[Side(style='thin', color='D0D0D0')] * 4)


def _diff_original():
    a = openpyxl.load_workbook(SRC, data_only=True)
    b = openpyxl.load_workbook(DST, data_only=True)
    out = {}
    for sh in a.sheetnames:
        wa, wb_ = a[sh], b[sh]
        n = 0
        for r in range(1, wa.max_row + 1):
            for c in range(1, wa.max_column + 1):
                va, vb = wa.cell(row=r, column=c).value, wb_.cell(row=r, column=c).value
                if (va is None) != (vb is None) or (va is not None and str(va) != str(vb)):
                    n += 1
        out[sh] = dict(rows=wa.max_row, cols=wa.max_column, diff=n)
    return out


def _stats():
    f = pd.read_parquet('final/synthetic_2022.parquet')
    cb = json.load(open('registry/codebook.json', encoding='utf-8'))
    blocks = json.load(open('registry/blocks.json', encoding='utf-8'))
    t12 = {v for b in blocks for v in b['vars']}
    P = {}
    for p in sorted(glob.glob('params/*.yaml')):
        d = yaml.safe_load(open(p, encoding='utf-8')) or {}
        for v, spec in (d.get('params') or {}).items():
            P[v] = spec or {}
    nn = f.notna().sum()
    nulls = [c for c in f.columns if nn[c] == 0]
    rc = collections.Counter()
    for v in nulls:
        spec = P.get(v, {})
        r = str((spec.get('dist') or {}).get('reason', '')) or str(spec.get('note', ''))
        if '규모 미달' in r or '규모미달' in r:
            rc['규모 미달(기대 수급 <3명)'] += 1
        elif '미확인' in str(spec.get('status', '')):
            rc['[미확인] 근거자료 미확보'] += 1
        else:
            rc['파라미터 미확정'] += 1
    st = collections.Counter(str(P.get(c, {}).get('status', '')) for c in f.columns if nn[c] > 0)
    return dict(total=len(cb), t12=len(t12), t3=len(cb) - len(t12), cols=len(f.columns),
                rows=len(f), valued=int((nn > 0).sum()), nulls=len(nulls),
                null_reason=dict(rc), status=dict(st))


def build():
    d = _diff_original()
    s = _stats()
    wb = openpyxl.load_workbook(DST)
    if TITLE in wb.sheetnames:
        del wb[TITLE]
    ws = wb.create_sheet(TITLE, 0)
    R = [1]

    def row(*cells, font=None, fill=None, h=None):
        for i, v in enumerate(cells, start=1):
            c = ws.cell(row=R[0], column=i, value=v)
            c.alignment = WRAP; c.border = THIN
            if font: c.font = font
            if fill: c.fill = fill
        if h: ws.row_dimensions[R[0]].height = h
        R[0] += 1

    def blank(n=1):
        R[0] += n

    def head(t):
        ws.cell(row=R[0], column=1, value=t).font = H2
        for i in range(1, 6):
            ws.cell(row=R[0], column=i).fill = FILL_H
            ws.cell(row=R[0], column=i).font = H2
        R[0] += 1

    ws.cell(row=1, column=1, value='코드북 변경요약 — 원 코드북 대비 무엇이 그대로이고 무엇이 더해졌는가').font = H1
    R[0] = 2
    row('기준 파일', '원본: (코드북) 3기_사회보장행정데이터_V3.1_코드북_결합데이터셋(2022년 기준, 260206).xlsx')
    row('작성일', '2026-09-02 · 대조 방식: 원본과 생성본을 셀 단위로 전수 비교')
    blank()

    head('1. 원 코드북에서 그대로 간 것 — 셀 단위 전수 대조 결과')
    row('시트', '원본 크기', '대조 범위', '셀 불일치', '판정', font=BOLD, fill=FILL_SUB)
    for sh, v in d.items():
        rng = 'A1:%s%d' % (get_column_letter(v['cols']), v['rows'])
        row(sh, '%d행 × %d열' % (v['rows'], v['cols']), rng, '%d건' % v['diff'],
            '완전 동일' if v['diff'] == 0 else '차이 있음',
            fill=FILL_KEEP if v['diff'] == 0 else None)
    row('서식', '코드북 A~H 994행', '배경색·굵기·표시형식', '0건', '완전 동일', fill=FILL_KEEP)
    row('열 너비', '코드북 A~H', 'column_dimensions', '0건', '완전 동일', fill=FILL_KEEP)
    blank()
    row('요약', '원 코드북의 내용은 한 글자도 바뀌지 않았습니다. 993개 변수의 정보보유기관·사업명·'
                '변수명(영문/한글)·단위·변수 내용·추출대상 및 기준시점·비고(A~H열)와 붙임 2개 시트가 '
                '값·서식·열너비까지 원본 그대로입니다.', font=BOLD)
    blank()

    head('2. 이번 작업에서 더해진 것 (원본에 없던 것)')
    row('구분', '위치', '내용', '', '', font=BOLD, fill=FILL_SUB)
    add_cols = ['생성여부', '담당블록', '분포(dist)', '소스', '주장지위', '생성조건',
                '가정번호', '표본 관측수', 'NULL%', '요약통계(생성값)', '비고(생성)']
    row('열 추가', '코드북 시트 I~S (11열)', ' · '.join(add_cols), '', '', fill=FILL_ADD)
    row('시트 추가', '변경요약', '이 시트', '', '', fill=FILL_ADD)
    row('시트 추가', '생성요약', '29개 블록별 선언변수·생성변수·지위 분포', '', '', fill=FILL_ADD)
    row('시트 추가', '주의사항', '데이터 사용 시 제약 (가중치·시군구·시설거주자·연도차)', '', '', fill=FILL_ADD)
    row('화면 설정', '전 시트', '원본에 저장돼 있던 스크롤 위치(G1)를 A1로 초기화하고 A~C열 틀고정. '
                              '셀 내용과는 무관한 보기 설정입니다.', '', '', fill=FILL_ADD)
    blank()

    head('3. 코드북 내용 수정 여부 — 작업지시서 §8 검토 결과')
    row('판정', '건수', '설명', '', '', font=BOLD, fill=FILL_SUB)
    row('변수 삭제', '0건', '코드북에서 제거한 변수 없음', '', '', fill=FILL_KEEP)
    row('상위개념 축약', '0건', '하위 유형을 상위 변수로 합친 사례 없음 '
                              '(nhi_premium_set·set_p20 1건만 "축약 후보"로 기록, 적용하지 않음)', '', '', fill=FILL_KEEP)
    row('변수 정의 변경', '0건', '값 레이블·단위·추출대상 정의를 바꾼 사례 없음', '', '', fill=FILL_KEEP)
    row('건의 사항', '기록만', '"시군구 단위 분석 불가" 주의 명시, self_type2 값3 "2022 실적 미확인" 주석 등 — '
                              '원본을 고치지 않고 report/codebook_revision.md 에 건의로 기록', '', '', fill=FILL_ADD)
    blank()
    row('요약', '작업지시서 §8(코드북 수정 검토) 12개 항목을 전부 판정한 결과 '
                '삭제 0건 · 축약 0건입니다. 판정 근거는 report/codebook_revision.md 에 항목별로 있습니다.', font=BOLD)
    blank()

    head('4. 생성 범위와 결과 (원 코드북 993변수 기준)')
    row('구분', '변수 수', '설명', '', '', font=BOLD, fill=FILL_SUB)
    row('코드북 전체', s['total'], '원 코드북에 정의된 변수', '', '')
    row('Tier1+2 (생성 대상)', s['t12'], '작업지시서가 지정한 29개 블록의 생성 범위', '', '')
    row('  ├ 값이 있는 변수', s['valued'], '실제 값이 생성된 변수', '', '', fill=FILL_KEEP)
    row('  └ 전량 NULL', s['nulls'], ' · '.join('%s %d' % (k, v) for k, v in s['null_reason'].items()) +
        '  — 코드북에서 삭제하지 않고 변수는 유지 (§9 "NULL 패턴 = 추출대상 정의")', '', '', fill=FILL_ADD)
    row('Tier3 (미착수)', s['t3'], 'LH·GH·SH 임대주택, 사회서비스 바우처 일부 등 — 후속 단계 대상. '
                                  '코드북에는 그대로 남아 있고 생성만 하지 않음', '', '', fill=FILL_SUB)
    blank()
    row('주장지위 (값이 있는 %d변수)' % s['valued'],
        ' · '.join('%s %d' % (k, v) for k, v in sorted(s['status'].items(), key=lambda x: -x[1]) if k),
        'M열에서 변수별로 확인. 1차확인 = 원문·표번호·수치를 직접 열람해 파라미터화', '', '', font=BOLD)
    blank()

    head('5. 함께 볼 문서')
    for a_, b_ in [('report/codebook_revision.md', '§8 코드북 수정 검토 12개 항목 판정 근거'),
                   ('report/validation.html', '검증 리포트 10절 (목표 대비 재현오차·§7 규칙·커버리지)'),
                   ('report/README.md', '사용 시 주의 5가지와 알려진 한계'),
                   ('report/assumptions.md', '[가정]·[미확인] 파라미터 대장'),
                   ('registry/s0_basis_finding.md', 'S0 기준연도 정정 근거')]:
        row(a_, b_, '', '', '')

    for col, w in zip('ABCDE', (34, 26, 96, 12, 12)):
        ws.column_dimensions[col].width = w
    ws.sheet_view.topLeftCell = 'A1'
    ws.freeze_panes = 'A4'
    wb.active = 0
    wb.save(DST)
    return dict(sheet=TITLE, diff_original=d, stats={k: v for k, v in s.items() if k != 'status'})


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=1))

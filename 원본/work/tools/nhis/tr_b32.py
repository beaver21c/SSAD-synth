# -*- coding: utf-8 -*-
"""B32 전사: 2022 건강보험통계연보 제3편 Ⅲ-9(연령·성·종별 평균 수진횟수),
Ⅲ-11/Ⅲ-12(연령별 연간진료비 크기별 실인원·진료비, 입원/외래).
계산·추정 없이 셀 값만 옮긴다. 출력 = params/tab/*.csv + .meta.json"""
import json, os, sys, datetime
import openpyxl

ROOT = '/mnt/share/행정데이터_set/work'
SRC = os.path.join(ROOT, 'params/raw/_ext/r10/03-1(건강공단) 2022년_제3편 건강보험 진료현황.xlsx')
TAB = os.path.join(ROOT, 'params/tab')
DATE = '2026-09-02'

AGES = ['계','0세','1~4세','5~9세','10~14세','15~19세','20~24세','25~29세','30~34세','35~39세',
        '40~44세','45~49세','50~54세','55~59세','60~64세','65~69세','70~74세','75~79세','80~84세','85세이상']
SEXES = ['계','남자','여자']


def num(v):
    if v is None: return None
    if isinstance(v, str):
        s = v.strip().replace(',', '')
        if s in ('-', '', '·'): return None
        try: return float(s)
        except ValueError: return None
    return float(v)


def tr_39(wb):
    """Ⅲ-9: 연령×성×요양기관종별 평균 수진횟수 (단위: 일/1,000명, 연간).
    3-9(1) 열: 총계(C~E) 의료기관소계(F~H) 종합병원(I~K, 상급종합포함) 병원(L~N, 요양·정신 포함)
                치과병원(O~Q) 한방병원(R~T)
    3-9(2) 열: 의원(C~E) 치과의원(F~H) 한의원(I~K) 보건기관(L~N) 조산원(O) 약국(P~R)"""
    rows = []
    blocks1 = [('총계', 3), ('의료기관소계', 6), ('종합병원', 9), ('병원', 12), ('치과병원', 15), ('한방병원', 18)]
    blocks2 = [('의원', 3), ('치과의원', 6), ('한의원', 9), ('보건기관', 12)]
    for sheet, blocks in (('3-9(1)', blocks1), ('3-9(2)', blocks2)):
        ws = wb[sheet]
        r = 8
        for ai, age in enumerate(AGES):
            base = 8 + ai * 4
            for si, sex in enumerate(SEXES):
                rr = base + si
                for inst, c0 in blocks:
                    for ci, form in enumerate(['계', '입원', '외래']):
                        v = num(ws.cell(rr, c0 + ci).value)
                        rows.append({'표번호': 'Ⅲ-9', '연령군': age, '성별': sex, '요양기관종별': inst,
                                     '진료형태': form, '지표': '평균수진횟수_일당1000명', '값': v})
    return rows


def tr_size(wb, sheet_prefix, tbl, form):
    """Ⅲ-11(입원)/Ⅲ-12(외래): 연령별 연간진료비 크기별 실인원·진료비.
    (1),(2) 두 시트에 연령대가 나뉘어 있고, 각 연령대는 (진료실인원수, 진료비) 2열."""
    rows = []
    for suf in ('(1)', '(2)'):
        sn = sheet_prefix + suf
        if sn not in wb.sheetnames: continue
        ws = wb[sn]
        # 연령 헤더: 5행. 각 연령은 2열 병합.
        ages = {}
        c = 1
        while c <= ws.max_column:
            v = ws.cell(5, c).value
            if v and isinstance(v, str) and v.strip():
                lab = ' '.join(v.split())
                if lab not in ('진료비구간(원) Amount Class(Won)',):
                    ages[c] = lab
            c += 1
        for r in range(8, ws.max_row + 1):
            a, b, cc = ws.cell(r, 1).value, ws.cell(r, 2).value, ws.cell(r, 3).value
            if a is None and b is None: continue
            if isinstance(a, str) and ('계' in a and 'Total' in a):
                band = '계'
            elif isinstance(a, str) and '이하' in a:
                band = a.split()[0]
            elif isinstance(a, str) and '초과' in a:
                band = ' '.join(a.split())
            elif a is not None and b == '~':
                band = f'{int(a)}~{int(cc)}' if cc is not None else f'{int(a)}~'
            elif isinstance(a, str) and a.strip():
                band = ' '.join(a.split())
            else:
                continue
            for c0, lab in ages.items():
                n = num(ws.cell(r, c0).value); amt = num(ws.cell(r, c0 + 1).value)
                if n is None and amt is None: continue
                rows.append({'표번호': tbl, '진료형태': form, '연령군': lab, '진료비구간_원': band,
                             '진료실인원수_명': n, '진료비_천원': amt})
    return rows


def write(rows, name, cols, meta):
    import csv
    p = os.path.join(TAB, name + '.csv')
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow(r)
    json.dump(meta, open(os.path.join(TAB, name + '.meta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(name, len(rows))


if __name__ == '__main__':
    wb = openpyxl.load_workbook(SRC, data_only=True)
    base_meta = {
        'source_grade': 'S1',
        'source_name': '2022 건강보험통계연보 제3편 건강보험 진료현황 (국민건강보험공단)',
        'source_file': 'params/raw/_ext/r10/03-1(건강공단) 2022년_제3편 건강보험 진료현황.xlsx',
        'origin_url': 'https://www.nhis.or.kr/nhis/together/wbhaec06300m01.do?mode=download&articleNo=10838804&attachNo=357498',
        'extract_date': DATE, 'status': '1차확인', 'coverage': '건강보험(직장+지역), 2022년, 의료급여 제외',
    }
    r39 = tr_39(wb)
    m = dict(base_meta); m.update({'table_no': 'Ⅲ-9', 'sheets': ['3-9(1)', '3-9(2)'],
        'unit': '일/1,000명(연간, 진료일 기준)',
        'note': '원주3) (종합병원)=상급종합병원 포함, (병원)=요양병원·정신병원 포함. 분모는 건강보험 적용인구.'})
    write(r39, 'R10_3-9_연령성별_요양기관종별_평균수진횟수',
          ['표번호', '연령군', '성별', '요양기관종별', '진료형태', '지표', '값'], m)

    r11 = tr_size(wb, '3-11', 'Ⅲ-11', '입원')
    m = dict(base_meta); m.update({'table_no': 'Ⅲ-11', 'sheets': ['3-11(1)', '3-11(2)'],
        'unit': '실인원=명, 진료비=천원', 'note': '연령별 연간진료비 크기별 실인원 및 진료비(입원)'})
    write(r11, 'R10_3-11_연령별_연간진료비크기별_입원',
          ['표번호', '진료형태', '연령군', '진료비구간_원', '진료실인원수_명', '진료비_천원'], m)

    r12 = tr_size(wb, '3-12', 'Ⅲ-12', '외래')
    m = dict(base_meta); m.update({'table_no': 'Ⅲ-12', 'sheets': ['3-12(1)', '3-12(2)'],
        'unit': '실인원=명, 진료비=천원', 'note': '연령별 연간진료비 크기별 실인원 및 진료비(외래)'})
    write(r12, 'R10_3-12_연령별_연간진료비크기별_외래',
          ['표번호', '진료형태', '연령군', '진료비구간_원', '진료실인원수_명', '진료비_천원'], m)


# ── 추가: Ⅳ-6-1/Ⅳ-6-2 내원일당 진료비 크기별 심사실적 (심평원 제4편) ──────────
def tr_46():
    import openpyxl, re, csv, json
    SRC4 = os.path.join(ROOT, 'params/raw/_ext/r10/04-(심평원) 2022년_제4편 건강보험 심사실적.xlsx')
    wb = openpyxl.load_workbook(SRC4, data_only=True)
    rows = []
    for sn, form, tbl in (('Ⅳ-6-1', '입원', 'Ⅳ-6-1'), ('Ⅳ-6-2', '외래', 'Ⅳ-6-2')):
        ws = wb[sn]
        for r in range(8, ws.max_row + 1):
            a = ws.cell(r, 1).value
            if not a or not isinstance(a, str) or a.startswith('주 :'):
                continue
            lab = ' '.join(a.split())
            cl, vis, amt = ws.cell(r, 4).value, ws.cell(r, 5).value, ws.cell(r, 9).value
            if cl is None:
                continue
            rows.append({'표번호': tbl, '진료형태': form, '내원일당진료비구간': lab,
                         '청구건수': num(cl), '입내원일수_일': num(vis), '진료비_천원': num(amt)})
    write(rows, 'R10_4-6_내원일당진료비크기별_심사실적',
          ['표번호', '진료형태', '내원일당진료비구간', '청구건수', '입내원일수_일', '진료비_천원'],
          {'source_grade': 'S1',
           'source_name': '2022 건강보험통계연보 제4편 건강보험 심사실적 (건강보험심사평가원)',
           'source_file': 'params/raw/_ext/r10/04-(심평원) 2022년_제4편 건강보험 심사실적.xlsx',
           'origin_url': 'https://www.nhis.or.kr/nhis/together/wbhaec06300m01.do?mode=download&articleNo=10838804&attachNo=357498',
           'table_no': 'Ⅳ-6-1(입원) / Ⅳ-6-2(외래) 내원일당 진료비 크기별 심사실적 — 계(전체 요양기관) 열',
           'extract_date': DATE, 'status': '1차확인',
           'unit': '청구건수=건, 입내원일수=일, 진료비=천원',
           'note': '심사일 기준. "기타"는 내원일수가 0인 건. 청구건 단위의 내원일당 진료비 분포 → '
                   'B32 1일당 진료비 로그정규의 산포 검증에 사용.'})

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사례별 산출물 생성 — 대시보드 화면에서 그림을 저장하고, 집계 저장소의 값으로 사례 보고 자료와 사례집을 만든다.

  입력  사회보장행정데이터_대시보드.html, 사례3_국민/한눈에_보는_사회보장.html, data/store.json, data/sim.json, data/store_public.json
  출력  사례1_사업담당공무원/  기초연금_수급현황_점검자료.html, 그림/*.png, 표/*.csv
        사례2_연구자/          정책모의실험_결과요약.html, 그림/*.png, 표/*.csv
        사례3_국민/            공개용_집계표.csv, 그림/*.png
        적용사례집.html
  개인 단위 자료는 읽지 않는다(집계 저장소와 모의실험 결과만 사용).

실행  python3 scripts/03_case_outputs.py
"""
import base64
import csv
import html as H
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HEAD = (ROOT.parent / 'build' / 'src' / 'head.html').read_text(encoding='utf-8')
S = json.loads((ROOT / 'data' / 'store.json').read_text(encoding='utf-8'))
SIM = json.loads((ROOT / 'data' / 'sim.json').read_text(encoding='utf-8'))
PUB = json.loads((ROOT / 'data' / 'store_public.json').read_text(encoding='utf-8'))
DASH = ROOT / '사회보장행정데이터_대시보드.html'
PUBP = ROOT / '사례3_국민' / '한눈에_보는_사회보장.html'
C1, C2, C3 = ROOT / '사례1_사업담당공무원', ROOT / '사례2_연구자', ROOT / '사례3_국민'
BOOK = ROOT / '사례집_그림'
for d in (C1 / '그림', C1 / '표', C2 / '그림', C2 / '표', C3 / '그림', BOOK):
    d.mkdir(parents=True, exist_ok=True)

IND = {d['id']: d for d in S['inds']}
SIDO = S['dims']['sido']['cats']
ORDER = S['order']


def f(v, dec=1):
    return '–' if v is None else f'{v:,.{dec}f}'


def tot(i):
    t = S['tabs'][i]['']
    return None if t['st'][0] else t['v'][0]


def tab(i, key):
    return S['tabs'][i][key]


def group_value(i, cond):
    """대상 집단 값: 조건 {차원: [항목 번호]}에 해당하는 칸의 가중 인원을 더해 계산한다(대시보드와 같은 방식)."""
    dims = [d for d in ORDER if d in cond]
    t = S['tabs'][i].get('|'.join(dims))
    if t is None:
        return None
    sizes = [len(S['dims'][d]['cats']) for d in dims]
    wn = wd = s = 0.0
    any_ = False

    def rec(k, idx):
        nonlocal wn, wd, s, any_
        if k == len(dims):
            st = t['st'][idx]
            if st == 3:
                return True
            if st:
                return False
            any_ = True
            wn += t['wn'][idx]; wd += t['wd'][idx]
            if 's' in t:
                s += t['s'][idx]
            return True
        for c in cond[dims[k]]:
            if not rec(k + 1, idx * sizes[k] + c):
                return False
        return True
    if not rec(0, 0) or not any_:
        return None
    kd = IND[i]['kind']
    return round(100 * wn / wd, 1) if kd == 'rate' else (s / wn if kd == 'mean_r' else s / wd)


# ───────────────────────── 그림 저장(대시보드 화면) ─────────────────────────
def capture():
    shots = [
        # (파일, 페이지, 해시, 선택자, 사전 동작)
        (C1 / '그림' / '그림1_시도별_수급률_지도.png', DASH, 't=map&i=bp&lv=sido&pal=Blues&k=5&lab=value', '#map', None),
        (C1 / '그림' / '그림2_시군구별_수급률_구간_지도.png', DASH, 't=map&i=bp&lv=city&pal=Blues', '#map', None),
        (C1 / '그림' / '그림3_소득분위별_수급률.png', DASH, 't=chart&i=bp&d1=inc&ct=bar', '#ch', None),
        (C1 / '그림' / '그림4_가구원수별_수급률.png', DASH, 't=chart&i=bp&d1=hs&d2=sex&ct=bar', '#ch', None),
        (C1 / '그림' / '그림5_시도별_빈곤노인_비수급비율.png', DASH, 't=chart&i=bpgap&d1=sido&ct=hbar&so=1', '#ch', None),
        (C1 / '그림' / '그림6_노인1인가구_제도별현황.png', DASH, 't=group&g=age:4.5;hs:0&gt=hbar', '#ch', None),
        (C1 / '그림' / '그림7_이용자정의지표_지도.png', DASH, 't=builder&bn=bpgap:wn&bd=pop65&bf=1000&bnm=65세 이상 천 명당 기초연금 비수급 빈곤 노인 수&bu=명', '#map', '#tomap'),
        (C2 / '그림' / '그림1_기초연금_분위별_급여변화.png', DASH, 't=sim&sp=bp&a=70&b=10&sc=bar', '#c1', None),
        (C2 / '그림' / '그림2_기초연금_인상액별_빈곤율.png', DASH, 't=sim&sp=bp&a=70&b=10', '#c3', None),
        (C2 / '그림' / '그림3_기초연금_시도별_추가소요액.png', DASH, 't=sim&sp=bp&a=70&b=10&sc=hbar', '#c2', None),
        (C2 / '그림' / '그림4_아동수당_분위별_급여변화.png', DASH, 't=sim&sp=child&a=13&b=10&sc=bar', '#c1', None),
        (C2 / '그림' / '그림5_아동수당_지급액별_빈곤율.png', DASH, 't=sim&sp=child&a=13&b=10', '#c3', None),
        (C3 / '그림' / '그림1_한눈에_보기.png', PUBP, 't=home', 'main', None),
        (C3 / '그림' / '그림2_지역별_지도.png', PUBP, 't=map&pi=bp', 'main', None),
        (C3 / '그림' / '그림3_연령대별_보기.png', PUBP, 't=age&pa=4', 'main', None),
        (BOOK / '화면_개요.png', DASH, 't=home', None, None),
        (BOOK / '화면_지표지도.png', DASH, 't=map&i=age65&lv=city&pal=YlOrRd&cls=jenks&k=6', None, None),
        (BOOK / '화면_그래프.png', DASH, 't=chart&i=bp&d1=inc&d2=hs&ct=bar', None, None),
        (BOOK / '화면_교차분석.png', DASH, 't=cross&i=poor&r=age&c=hs', None, None),
        (BOOK / '화면_대상별현황.png', DASH, 't=group&g=age:4.5;hs:0', None, None),
        (BOOK / '화면_지표만들기.png', DASH, 't=builder&bn=live:wn,house:wn&bd=pop&bf=1000&bnm=인구 천 명당 생계·주거급여 수급자&bu=명', None, None),
        (BOOK / '화면_변수탐색.png', DASH, 't=vars&vs=bp_amt', None, None),
        (BOOK / '화면_정책모의실험.png', DASH, 't=sim&sp=bp&a=70&b=10', None, None),
    ]
    errs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=2)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        for path, page, h, selq, pre in shots:
            pg.goto('about:blank'); pg.goto('file://' + str(page) + '#' + h); pg.wait_for_timeout(300)
            if pre:
                pg.click(pre); pg.wait_for_timeout(300)
            if selq:
                pg.locator(selq).first.screenshot(path=str(path))
            else:
                pg.screenshot(path=str(path), full_page=False)
        b.close()
    if errs:
        raise SystemExit('화면 오류: ' + '; '.join(errs[:3]))
    print('그림', len(shots), '건 저장')


# ───────────────────────── HTML 도구 ─────────────────────────
def img(path, width='100%'):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img alt="" style="width:{width}" src="data:image/png;base64,{b64}">'


def fig(path, cap, note='', width='100%'):
    return (f'<figure><figcaption>〔그림〕 {H.escape(cap)}</figcaption>{img(path, width)}'
            f'<p class="fig-src">자료: 대시보드 화면에서 저장한 그림(가상데이터 집계값). {note}</p></figure>')


def table(head, rows, widths=None, src='자료: 집계 저장소의 집계값(가상데이터).', cap=''):
    o = [f'<p class="tbl-cap">〈표〉 {H.escape(cap)}</p><div class="tbl-wrap"><table><thead><tr>']
    for i, h in enumerate(head):
        o.append(f'<th{f" style=\"width:{widths[i]}\"" if widths else ""}>{h}</th>')
    o.append('</tr></thead><tbody>')
    for r in rows:
        o.append('<tr>' + ''.join(f'<th>{c}</th>' if i == 0 else f'<td class="{"n" if re.match(r"^[\d,.\-–+%]+$", str(c)) else ""}">{c}</td>' for i, c in enumerate(r)) + '</tr>')
    o.append(f'</tbody></table></div><p class="tbl-src">{src}</p>')
    return ''.join(o)


def lv(items):
    """[(수준, 문장)] → 개조식 목록."""
    return '<ul class="lv">' + ''.join(f'<li class="L{k}">{t}</li>' for k, t in items) + '</ul>'


def number(body, ch='1'):
    ct = [0, 0]

    def rt(_):
        ct[0] += 1
        return f'〈표 {ct[0]}〉'

    def rf(_):
        ct[1] += 1
        return f'〔그림 {ct[1]}〕'
    return re.sub(r'〔그림〕', rf, re.sub(r'〈표〉', rt, body))


def page(title, kicker, subtitle, meta, body, brk=False):
    head = HEAD.replace('<title>사회보장행정데이터의 활용 고도화 전략</title>', f'<title>{H.escape(title)}</title>')
    if not brk:                                   # 짧은 보고 자료는 장마다 쪽을 나누지 않는다
        head = head.replace('</style>', '  @media print { h2 { break-before: auto; margin-top: 18px; } }\n</style>', 1)
    cover = (f'<div class="cover"><div class="kicker">{H.escape(kicker)}</div><h1>{H.escape(title)}</h1>'
             f'<p class="subtitle">{H.escape(subtitle)}</p><div class="meta">{H.escape(meta)}</div></div>')
    return head + cover + number(body) + '\n</div>\n</body>\n</html>\n'


def write_csv(path, head, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as fp:
        w = csv.writer(fp); w.writerow(head); w.writerows(rows)


WARN = '이 자료의 수치는 코드북과 같은 변수 구조로 생성한 가상데이터의 집계값이며 실제 현황이 아님.'


# ───────────────────────── 사례 1: 사업 담당 공무원 ─────────────────────────
def case1():
    bp, amt, gap = tab('bp', 'sido'), tab('bp_amt', 'sido'), tab('bpgap', 'sido')
    rows, crow = [], []
    for i, n in enumerate(SIDO):
        r = [n, f(bp['v'][i]) if not bp['st'][i] else '억제', f'{bp["wn"][i]:,}' if not bp['st'][i] else '억제',
             f(amt['v'][i], 0) if not amt['st'][i] else '억제', f(gap['v'][i]) if not gap['st'][i] else '억제']
        rows.append(r); crow.append(r)
    t0 = S['tabs']['bp']['']
    rows.append(['<b>전국</b>', f(tot('bp')), f'{t0["wn"][0]:,}', f(tot('bp_amt'), 0), f(tot('bpgap'))])
    write_csv(C1 / '표' / '표1_시도별_기초연금_현황.csv', ['시도', '수급률(%)', '수급자 수(명, 가중)', '평균 연 수급액(만원)', '빈곤 노인 중 비수급 비율(%)'], crow)
    inc = tab('bp', 'inc'); hs = tab('bp', 'hs')
    okv = [(bp['v'][i], SIDO[i]) for i in range(17) if not bp['st'][i]]
    hi, lo = max(okv), min(okv)
    gv = [(gap['v'][i], SIDO[i]) for i in range(17) if not gap['st'][i]]
    ghi = max(gv)
    cond = {'age': [4, 5], 'hs': [0]}
    grp = [(IND[i]['name'], group_value(i, cond), tot(i), IND[i]['unit']) for i in ('bp', 'nppen', 'live', 'house', 'medi', 'poor65', 'oldwork')]
    write_csv(C1 / '표' / '표2_65세이상_1인가구_제도별_현황.csv', ['지표', '65세 이상 1인 가구', '전체', '단위'], [[a, b, c, d] for a, b, c, d in grp])
    body = '<h2 class="first" data-ch="1">1. 점검 개요</h2>' + lv([
        (2, '점검 목적은 기초연금 수급률의 지역·소득 계층별 분포와 빈곤 노인 중 비수급자 규모를 확인하는 것임'),
        (2, '자료는 대시보드의 지표 지도, 그래프, 대상별 현황, 지표 만들기 화면에서 조회한 집계값이며 개인 단위 자료를 사용하지 않음'),
        (2, f'기초연금 지표는 민감도 등급 나에 해당하여 관측 {S["meta"]["thr"]["나"]}건 미만 칸을 억제하고, 시군구 단위는 5개 구간으로만 제공함'),
        (2, WARN)]) + \
        '<h2 data-ch="1">2. 주요 결과</h2>' + lv([
            (1, '전국 수준'),
            (2, f'65세 이상 인구의 기초연금 수급률은 {f(tot("bp"))}%이며 수급자는 약 {t0["wn"][0] / 1e4:,.0f}만 명, 수급자 1인당 평균 연 수급액은 {f(tot("bp_amt"), 0)}만원임'),
            (2, f'65세 이상 빈곤 인구 중 기초연금을 받지 않는 비율은 {f(tot("bpgap"))}%임'),
            (1, '지역별 분포'),
            (2, f'시도별 수급률은 {hi[1]} {f(hi[0])}%에서 {lo[1]} {f(lo[0])}%까지 분포함'),
            (2, f'빈곤 노인 중 비수급 비율은 {ghi[1]}이 {f(ghi[0])}%로 가장 높음'),
            (1, '소득 계층·가구 형태별 분포'),
            (2, '소득 5분위별 수급률은 ' + ', '.join(f'{k + 1}분위 {f(inc["v"][k])}%' for k in range(5) if not inc['st'][k]) + '임'),
            (2, '가구원수별 수급률은 ' + ', '.join(f'{S["dims"]["hs"]["cats"][k]} {f(hs["v"][k])}%' for k in range(4) if not hs['st'][k]) + '임'),
            (2, f'65세 이상 1인 가구의 수급률은 {f(grp[0][1])}%, 생계급여 수급률은 {f(grp[2][1])}%, 상대 빈곤율은 {f(grp[5][1])}%임')]) + \
        table(['시도', '수급률(%)', '수급자 수(명)', '평균 연 수급액(만원)', '빈곤 노인 중 비수급 비율(%)'], rows, ['16%', '18%', '22%', '22%', '22%'], cap='시도별 기초연금 수급 현황',
              src='자료: 집계 저장소의 집계값(가상데이터). 주: 수급자 수는 가중 인원을 유효숫자 3자리로 반올림한 값임.') + \
        fig(C1 / '그림' / '그림1_시도별_수급률_지도.png', '시도별 기초연금 수급률', '분위수 5단계.', '60%') + \
        fig(C1 / '그림' / '그림2_시군구별_수급률_구간_지도.png', '시군구별 기초연금 수급률 구간', '등급 나 지표의 시군구 단위는 5개 구간으로만 제공함. 빗금은 억제 지역임.', '60%') + \
        fig(C1 / '그림' / '그림3_소득분위별_수급률.png', '소득 5분위별 기초연금 수급률', '', '78%') + \
        fig(C1 / '그림' / '그림5_시도별_빈곤노인_비수급비율.png', '시도별 빈곤 노인 중 기초연금 비수급 비율', '', '78%') + \
        table(['지표', '65세 이상 1인 가구', '전체', '단위'], [[a, f(b, 0 if d == '만원' else 1), f(c, 0 if d == '만원' else 1), d] for a, b, c, d in grp], ['46%', '22%', '16%', '16%'],
              cap='65세 이상 1인 가구의 제도별 현황', src='자료: 대상별 현황 화면의 조회 결과(가상데이터). 주: 전체는 각 지표의 대상 인구 전체 기준임.') + \
        fig(C1 / '그림' / '그림7_이용자정의지표_지도.png', '이용자 정의 지표: 65세 이상 천 명당 기초연금 비수급 빈곤 노인 수', '지표 만들기 화면에서 「비수급 빈곤 노인 수 ÷ 65세 이상 인구 × 1,000」으로 산출함.', '60%') + \
        '<h2 data-ch="1">3. 유의 사항</h2>' + lv([
            (2, '시군구 단위 수급률의 수치가 필요한 경우 대시보드로는 제공되지 않으므로 운영기관에 원자료 분석을 요청함'),
            (2, '이용자 정의 지표는 공식 지표가 아니므로 인용 시 산식을 함께 적음'),
            (2, WARN)])
    out = C1 / '기초연금_수급현황_점검자료.html'
    out.write_text(page('기초연금 수급 현황 점검 자료', '적용 사례 1 · 사업 담당 공무원', '대시보드 조회 결과를 이용한 사업 현황 보고 예시',
                        f'작성 기준 {S["meta"]["built"]} · 자료: 사회보장행정데이터 대시보드(가상데이터 시연)', body), encoding='utf-8')
    return {'rate': tot('bp'), 'hi': hi, 'lo': lo, 'gap': tot('bpgap'), 'grp': grp, 'inc': inc['v'], 'rec': t0['wn'][0], 'amt': tot('bp_amt')}


# ───────────────────────── 사례 2: 연구자 ─────────────────────────
def case2():
    B, C = SIM['bp'], SIM['child']
    b0, c0 = B['grid'][B['base']], C['grid'][C['base']]
    pick_b = [('70|0', '현행'), ('70|10', '월 10만원 인상'), ('70|20', '월 20만원 인상'), ('50|10', '범위 50%로 축소 + 월 10만원 인상'), ('80|0', '범위 80%로 확대'), ('100|0', '65세 이상 전체로 확대')]
    pick_c = [('8|10', '현행'), ('13|10', '13세 미만으로 확대'), ('18|10', '18세 미만으로 확대'), ('8|20', '월 20만원으로 인상'), ('13|20', '13세 미만 + 월 20만원')]
    rb = [[lab, f'{B["grid"][k]["rec"] / 1e4:,.0f}', f(B['grid'][k]['rate']), f(B['grid'][k]['cost'], 2), f'{B["grid"][k]["dcost"]:+,.2f}', f(B['grid'][k]['pov65'], 2), f(B['grid'][k]['pov'], 2)] for k, lab in pick_b]
    rc = [[lab, f'{C["grid"][k]["rec"] / 1e4:,.0f}', f(C['grid'][k]['rate']), f(C['grid'][k]['cost'], 2), f'{C["grid"][k]["dcost"]:+,.2f}', f(C['grid'][k]['povkid'], 2), f(C['grid'][k]['pov'], 2)] for k, lab in pick_c]
    head = ['시나리오', '수급자(만 명)', '수급률(%)', '연 소요액(조원)', '추가 소요액(조원)', '대상 집단 빈곤율(%)', '전체 빈곤율(%)']
    write_csv(C2 / '표' / '표1_기초연금_주요_시나리오.csv', head, rb); write_csv(C2 / '표' / '표2_아동수당_주요_시나리오.csv', head, rc)
    g10, g100, c13 = B['grid']['70|10'], B['grid']['100|0'], C['grid']['13|10']
    eff = lambda g, k, base: (base[k] - g[k]) / g['dcost'] if g['dcost'] else None
    body = '<h2 class="first" data-ch="1">1. 분석 개요</h2>' + lv([
        (2, '분석 질문은 기초연금의 수급 범위·급여액과 아동수당의 대상 연령·지급액을 조정할 때의 수급자 규모, 소요 재정, 빈곤율 변화임'),
        (2, '분석 절차는 분석 코드 작성, 폐쇄망 자료에서의 실행, 출력 통제 적용, 결과 반출의 순서이며, 이 자료는 가상데이터를 폐쇄망 자료로 간주하고 수행한 결과임'),
        (2, f'빈곤선은 현행 균등화 가처분소득 중위값의 50%(연 {SIM["poverty_line"]:,}만원)로 고정함'),
        (2, WARN)]) + \
        '<h2 data-ch="1">2. 방법</h2>' + lv([
            (1, '모형'),
            (2, '개인별 급여액에 제도 변경분을 더하고 가구 가처분소득과 균등화 소득을 다시 계산하는 정태적 산술 모형임'),
            (2, '노동 공급이나 신청률의 변화, 다른 급여와의 연동은 반영하지 않음'),
            (1, '기초연금 시나리오'),
        ] + [(2, H.escape(n)) for n in B['notes']] + [(1, '아동수당 시나리오')] + [(2, H.escape(n)) for n in C['notes']] + [
            (1, '출력 통제'),
            (2, '산출 단위는 전국, 소득 5분위, 시도이며 관측 30건 미만 칸은 산출하지 않음'),
            (2, '가중 인원과 금액은 유효숫자 3자리로 반올림함')]) + \
        '<h2 data-ch="1">3. 결과</h2>' + lv([
            (1, '기초연금'),
            (2, f'현행 수급자는 약 {b0["rec"] / 1e4:,.0f}만 명, 연 소요액은 {f(b0["cost"], 2)}조원이며 65세 이상 빈곤율은 {f(b0["pov65"], 2)}%임'),
            (2, f'월 10만원 인상 시 추가 소요액은 {f(g10["dcost"], 2)}조원이고 65세 이상 빈곤율은 {f(g10["pov65"], 2)}%로 {b0["pov65"] - g10["pov65"]:.2f}%p 낮아짐'),
            (2, f'수급 범위를 65세 이상 전체로 확대하면 추가 소요액은 {f(g100["dcost"], 2)}조원이고 65세 이상 빈곤율은 {f(g100["pov65"], 2)}%로 {b0["pov65"] - g100["pov65"]:.2f}%p 낮아짐'),
            (2, f'추가 소요액 1조원당 65세 이상 빈곤율 감소 폭은 급여 인상이 {eff(g10, "pov65", b0):.2f}%p, 범위 확대가 {eff(g100, "pov65", b0):.2f}%p임'),
            (1, '아동수당'),
            (2, f'현행 수급 아동은 약 {c0["rec"] / 1e4:,.0f}만 명, 연 소요액은 {f(c0["cost"], 2)}조원이며 18세 미만 빈곤율은 {f(c0["povkid"], 2)}%임'),
            (2, f'대상을 13세 미만으로 확대하면 추가 소요액은 {f(c13["dcost"], 2)}조원이고 18세 미만 빈곤율은 {f(c13["povkid"], 2)}%로 {c0["povkid"] - c13["povkid"]:.2f}%p 낮아짐')]) + \
        table(head, rb, ['28%', '11%', '10%', '12%', '13%', '13%', '13%'], cap='기초연금 주요 시나리오의 결과', src='자료: 모의실험 결과(가상데이터). 주: 대상 집단은 65세 이상임.') + \
        fig(C2 / '그림' / '그림1_기초연금_분위별_급여변화.png', '소득 분위별 65세 이상 1인당 연 급여 변화(월 10만원 인상)', '', '86%') + \
        fig(C2 / '그림' / '그림2_기초연금_인상액별_빈곤율.png', '월 인상액별 65세 이상 빈곤율', '', '86%') + \
        fig(C2 / '그림' / '그림3_기초연금_시도별_추가소요액.png', '시도별 추가 소요액(월 10만원 인상)', '', '86%') + \
        table(head, rc, ['28%', '11%', '10%', '12%', '13%', '13%', '13%'], cap='아동수당 주요 시나리오의 결과', src='자료: 모의실험 결과(가상데이터). 주: 대상 집단은 18세 미만임.') + \
        fig(C2 / '그림' / '그림4_아동수당_분위별_급여변화.png', '가구 소득 분위별 18세 미만 1인당 연 급여 변화(13세 미만으로 확대)', '', '86%') + \
        fig(C2 / '그림' / '그림5_아동수당_지급액별_빈곤율.png', '월 지급액별 18세 미만 빈곤율', '', '86%') + \
        '<h2 data-ch="1">4. 한계와 재현 방법</h2>' + lv([
            (2, '결과는 가상데이터에 정태적 가정을 적용한 값이므로 실제 제도 효과의 추정치로 사용할 수 없음'),
            (2, '분석 코드는 <code>scripts/02_simulate.py</code>이며, 시나리오 전체 결과는 <code>data/모의실험_결과표.csv</code>와 대시보드의 정책 모의실험 화면에서 조회할 수 있음'),
            (2, '실제 적용에서는 반출용 합성데이터로 코드를 작성·시험한 뒤 운영기관이 폐쇄망 원자료에서 같은 코드를 실행하고 출력 통제를 거쳐 결과를 회신하는 절차를 따름')])
    out = C2 / '정책모의실험_결과요약.html'
    out.write_text(page('정책 변화 모의실험 결과 요약', '적용 사례 2 · 정책 변화를 모의실험하는 연구자', '기초연금·아동수당 제도 변경 시나리오의 재정·빈곤 효과',
                        f'작성 기준 {S["meta"]["built"]} · 자료: 가상데이터(확대 생성본)에 대한 정태적 산술 모형', body), encoding='utf-8')
    return {'b0': b0, 'g10': g10, 'g100': g100, 'c0': c0, 'c13': c13}


# ───────────────────────── 사례 3: 국민 ─────────────────────────
def case3():
    rows = []
    for d in PUB['inds']:
        T = PUB['tabs'][d['id']]
        rows.append([d['who'], d['easy'], '전국', '', T['']['v'][0] if not T['']['st'][0] else '표시하지 않음'])
        for k, n in enumerate(PUB['dims']['sido']['cats']):
            rows.append([d['who'], d['easy'], '시도', n, T['sido']['v'][k] if not T['sido']['st'][k] else ('해당 없음' if T['sido']['st'][k] == 3 else '표시하지 않음')])
        for k, n in enumerate(PUB['dims']['age']['cats']):
            rows.append([d['who'], d['easy'], '연령대', n, T['age']['v'][k] if not T['age']['st'][k] else ('해당 없음' if T['age']['st'][k] == 3 else '표시하지 않음')])
    write_csv(C3 / '공개용_집계표.csv', ['대상', '항목', '구분', '지역·연령대', '100명 중(명)'], rows)
    return {'n_rows': len(rows), 'n_ind': len(PUB['inds'])}


# ───────────────────────── 사례집 ─────────────────────────
def book(r1, r2, r3):
    with open(ROOT / 'data' / 'store_출력통제_요약.csv', encoding='utf-8-sig') as fp:
        sm = list(csv.DictReader(fp))
    G = {k: {'n': 0, 'shown': 0, 'sup': 0, 'comp': 0} for k in ('가', '나', '다')}
    for r in sm:
        e = G[r['grade']]
        e['n'] += 1; e['shown'] += int(r['cells_shown']); e['sup'] += int(r['suppressed']); e['comp'] += int(r['complementary'])
    TT = {k: sum(e[k] for e in G.values()) for k in ('n', 'shown', 'sup', 'comp')}
    pct = lambda e: f"{100 * (e['sup'] + e['comp']) / (e['shown'] + e['sup'] + e['comp']):.1f}"
    ctl_rows = [[k, e['n'], f"{e['shown']:,}", f"{e['sup']:,}", f"{e['comp']:,}", pct(e)] for k, e in G.items()]
    ctl_rows.append(['<b>계</b>', TT['n'], f"{TT['shown']:,}", f"{TT['sup']:,}", f"{TT['comp']:,}", pct(TT)])
    city_ok = [int(float(r['city_shown'])) for r in sm if r['grade'] == '가' and r['city_shown'] not in ('', 'nan')]
    M = S['meta']
    step = lambda rows: table(['단계', '수행 내용', '사용 화면·도구', '산출물', '적용된 통제'], rows, ['6%', '30%', '20%', '22%', '22%'], src='자료: 저자 작성.')
    body = '<h2 class="first" data-ch="1">Ⅰ. 개요</h2>' + lv([
        (1, '목적과 구성'),
        (2, '「사회보장행정데이터의 활용 고도화 전략」의 세부과제가 실제 업무에서 어떻게 쓰이는지를 가상데이터로 구현한 적용 사례를 제시함'),
        (2, '사례는 사업 담당 공무원, 정책 변화를 모의실험하는 연구자, 국민의 3개이며, 사례마다 자료 산출에서 부가 자료 생산까지의 과정을 실제로 수행함'),
        (2, '대시보드는 파일 1개로 동작하는 화면으로 구현하였고, 지도·그래프 전환·지표 생산 기능은 이용자 깃허브 레포(kihasa-indicator, rcssp_map)의 기능을 참고함'),
        (1, '자료'),
        (2, f'대시보드와 모의실험의 원천은 가상데이터 확대 생성본(개인 {M["n_person"]:,}명, 가구 {M["n_hh"]:,}개, 변수 595개)임'),
        (2, '확대 생성본은 기존 가상데이터 생성 체계를 가구 수만 4,200에서 42,000으로 늘려 실행한 것이며, 정합성 규칙 25개의 위반은 0건임'),
        (2, '기존 가상데이터(9,535명)는 시군구당 관측 수 중앙값이 29명이어서 시군구 지도의 대부분이 억제되므로 확대 생성본을 사용함'),
        (2, WARN)]) + \
        table(['구분', '기존 가상데이터', '확대 생성본'], [['개인(명)', '9,535', f'{M["n_person"]:,}'], ['가구(개)', '4,200', f'{M["n_hh"]:,}'], ['시군구 수', '227', '229'],
                                         ['시군구당 관측 수 중앙값(명)', '29', '278'], ['65세 이상 기초연금 수급률(%)', '67.5', f(tot('bp'))], ['정합성 규칙 위반(건)', '0', '0']],
              ['40%', '30%', '30%'], cap='기존 가상데이터와 확대 생성본', src='자료: 가상데이터 재계산. 주: 두 자료 모두 가중치 합계는 주민등록 인구(5,145만 명)임.') + \
        '<h2 data-ch="2">Ⅱ. 자료 산출 과정</h2>' + lv([
            (1, '처리 흐름'),
            (2, '가상데이터 확대 생성, 집계 저장소 산출, 대시보드 조립, 사례별 산출물 생성의 4단계로 처리함'),
            (2, '집계 저장소에는 집계값만 저장하고 개인 단위 값은 저장하지 않으며, 등급별 최소 관측 수 미만 칸은 저장 단계에서 억제함'),
            (2, '대시보드와 사례 산출물은 집계 저장소와 모의실험 결과만 읽음')]) + \
        table(['순서', '처리', '스크립트', '산출물'], [
            ['1', '가상데이터 확대 생성과 정합성 점검', '<code>scripts/00_generate_expanded.py</code>', '<code>data/가상데이터_확대본_n42000.parquet</code>'],
            ['2', '행정 경계를 화면 좌표로 변환', '<code>scripts/geo_prep.py</code>', '<code>data/geo.json</code>'],
            ['3', '지표·교차표·변수 요약 집계와 출력 통제', '<code>scripts/01_build_store.py</code>', '<code>data/store.json</code>, <code>data/store_public.json</code>'],
            ['4', '정책 모의실험', '<code>scripts/02_simulate.py</code>', '<code>data/sim.json</code>, <code>data/모의실험_결과표.csv</code>'],
            ['5', '대시보드와 국민용 화면 조립', '<code>scripts/04_build_dashboard.py</code>', '<code>사회보장행정데이터_대시보드.html</code>, <code>사례3_국민/한눈에_보는_사회보장.html</code>'],
            ['6', '사례별 그림·표·보고 자료 생성', '<code>scripts/03_case_outputs.py</code>', '사례 폴더의 그림, 표, 보고 자료와 이 사례집']],
            ['7%', '33%', '28%', '32%'], cap='처리 단계와 산출물', src='자료: 저자 작성.') + lv([
                (1, '출력 통제 적용 결과'),
                (2, f'지표 {len(S["inds"])}개의 전국·1차원·2차원·3차원 표에서 표시 칸은 {TT["shown"]:,}개, 억제 칸은 {TT["sup"]:,}개, 보충 억제 칸은 {TT["comp"]:,}개임'),
                (2, f'등급 가 지표의 시군구 표시 지역 수는 지표에 따라 {min(city_ok)}~{max(city_ok)}개(전체 229개)임'),
                (2, '등급 나 지표의 시군구 단위는 5개 구간으로만, 등급 다 지표는 시도 단위까지만 제공함')]) + \
        table(['등급', '지표 수', '표시 칸', '억제 칸', '보충 억제 칸', '억제 비율(%)'], ctl_rows, ['14%', '14%', '18%', '18%', '18%', '18%'], cap='등급별 출력 통제 적용 결과',
              src=f'자료: 집계 저장소 산출 기록. 주: 최소 관측 수는 등급 가 {M["thr"]["가"]}건, 나 {M["thr"]["나"]}건, 다 {M["thr"]["다"]}건임. 3차원 표의 시도 교차 칸에서 억제가 집중됨.') + \
        '<h2 data-ch="3">Ⅲ. 대시보드 구성</h2>' + lv([
            (1, '화면'),
            (2, f'화면은 개요, 지표 지도, 그래프, 교차분석, 대상별 현황, 지표 만들기, 변수 탐색, 정책 모의실험, 이용 안내의 9개이며 지표 {len(S["inds"])}개와 변수 {M["n_var"]}개를 제공함'),
            (2, '외부 서체·스크립트·지도 배경을 불러오지 않으므로 폐쇄망에서 파일 1개로 동작하고, 화면 상태는 주소의 # 뒤에 저장되어 같은 화면을 다시 열 수 있음'),
            (2, '모든 화면에 그림 저장, 표 저장(집계값), PDF 저장 기능을 두었으며 개인 단위 자료의 조회·내려받기 기능은 없음')]) + \
        table(['참고한 레포 기능', '대시보드 구현', '화면'], [
            ['지표 단계구분도: 색상, 분류 3종, 계급 수, 색 반전, 라벨, 지역 강조, 순위, 그림 저장', '색상 6종, 분위수·등간격·자연단절, 계급 3~7단계, 색 반전, 라벨 3종, 지역 강조, 순위표, PNG 저장', '지표 지도'],
            ['전국 시군구 지도(일반구 통합 229개), 시도 단위', '시도 17개와 시군구 229개 경계 사용. 등급에 따라 시군구 값·구간·미제공을 구분', '지표 지도'],
            ['추이 그래프의 선·막대 전환, 값 표시, 평균 기준선, 수치표', '세로 막대·가로 막대·선·점·표 전환, 값 표시, 정렬, 전체 값 기준선', '그래프'],
            ['지표 만들기: 분자(복수 합산) ÷ 분모 × 계수, 평균·중앙값·결측 표시, 지도 연동, 산식 링크 공유', '같은 산식 구조, 전국 값·평균·중앙값·결측 수 표시, 지표 지도 연동, 주소로 산식 공유', '지표 만들기'],
            ['폐쇄망용 단일 HTML', '외부 자원 없는 단일 HTML(2.2MB)', '전체'],
            ['엑셀 업로드·직접 입력, 읍면동 지도, 자연어 지표 생성', '구현하지 않음(대시보드는 집계 저장소의 자료만 사용)', '–']],
            ['36%', '48%', '16%'], cap='참고한 레포 기능과 대시보드 구현의 대응', src='자료: 저자 작성. 주: 행정 경계는 kihasa-indicator 레포의 시군구·시도 경계 자료를 화면 좌표로 변환해 사용함.') + \
        fig(BOOK / '화면_지표지도.png', '지표 지도 화면(65세 이상 인구 비율, 시군구, 자연단절 6단계)') + \
        fig(BOOK / '화면_그래프.png', '그래프 화면(기초연금 수급률, 소득 5분위 × 가구원수)') + \
        fig(BOOK / '화면_교차분석.png', '교차분석 화면(상대 빈곤율, 연령대 × 가구원수)') + \
        fig(BOOK / '화면_지표만들기.png', '지표 만들기 화면(인구 천 명당 생계·주거급여 수급자)') + \
        fig(BOOK / '화면_변수탐색.png', '변수 탐색 화면(기초연금 급여액)') + \
        '<h2 data-ch="4">Ⅳ. 사례 1: 사업 담당 공무원</h2>' + lv([
            (1, '상황'),
            (2, '기초연금 사업 담당자가 수급률의 지역·소득 계층별 분포와 빈곤 노인 중 비수급자 규모를 확인해 사업 현황 보고 자료를 작성함'),
            (2, '담당자는 분석 도구를 사용하지 않고 대시보드 화면만으로 조회·저장·보고 자료 작성을 수행함')]) + \
        step([['1', '시도별 수급률 확인', '지표 지도(시도)', '지도 그림, 순위표', '등급 나: 최소 20건'],
              ['2', '시군구별 수준 확인', '지표 지도(시군구)', '5개 구간 지도', '값 대신 구간만 제공'],
              ['3', '소득 분위·가구원수별 수급률 확인', '그래프(세로 막대)', '그래프 그림, 집계표', '억제·보충 억제 표시'],
              ['4', '65세 이상 1인 가구의 제도별 현황 확인', '대상별 현황', '제도별 비교표·그림', '조건 3개 분류까지'],
              ['5', '비수급 빈곤 노인 지표 작성', '지표 만들기 → 지표 지도', '이용자 정의 지표 지도', '집계값만 사용, 산식 표기'],
              ['6', '보고 자료 작성', '저장한 그림·표', '점검 자료(HTML·PDF)', '가상데이터 표기']]).replace('〈표〉 ', '〈표〉 사례 1의 수행 단계') + lv([
                  (1, '산출 결과'),
                  (2, f'65세 이상 기초연금 수급률은 {f(r1["rate"])}%, 수급자는 약 {r1["rec"] / 1e4:,.0f}만 명, 평균 연 수급액은 {f(r1["amt"], 0)}만원으로 산출됨'),
                  (2, f'시도별 수급률은 {r1["hi"][1]} {f(r1["hi"][0])}%에서 {r1["lo"][1]} {f(r1["lo"][0])}%까지 분포하고, 빈곤 노인 중 비수급 비율은 {f(r1["gap"])}%임'),
                  (2, f'65세 이상 1인 가구는 수급률 {f(r1["grp"][0][1])}%, 생계급여 수급률 {f(r1["grp"][2][1])}%로 산출됨'),
                  (1, '부가 자료'),
                  (2, '보고 자료 「기초연금 수급 현황 점검 자료」(HTML·PDF), 그림 7건, 표 2건(CSV)을 <code>사례1_사업담당공무원/</code>에 생성함')]) + \
        fig(C1 / '그림' / '그림1_시도별_수급률_지도.png', '사례 1의 지도 산출물(시도별 기초연금 수급률)', '', '72%') + \
        fig(C1 / '그림' / '그림6_노인1인가구_제도별현황.png', '사례 1의 대상별 현황 산출물(65세 이상 1인 가구)', '', '72%') + \
        '<h2 data-ch="5">Ⅴ. 사례 2: 정책 변화를 모의실험하는 연구자</h2>' + lv([
            (1, '상황'),
            (2, '연구자가 기초연금의 수급 범위·급여액과 아동수당의 대상 연령·지급액을 조정하는 시나리오의 재정·빈곤 효과를 산출함'),
            (2, '연구자는 분석 코드를 작성해 폐쇄망 자료에서 실행하고, 출력 통제를 거친 집계 결과만 반출함')]) + \
        step([['1', '시나리오와 산출 지표 정의', '분석 계획', '시나리오 54개(기초연금 30, 아동수당 24)', '–'],
              ['2', '분석 코드 작성·시험', '반출용 합성데이터(실제 적용 시)', '모의실험 코드', '합성데이터 이용 약정'],
              ['3', '폐쇄망 자료에서 실행', '<code>scripts/02_simulate.py</code>', '시나리오별 집계 결과', '최소 30건, 유효숫자 3자리'],
              ['4', '결과 반출 심사', '운영기관 심사(실제 적용 시)', '결과표(CSV), 결과 파일', '집계 단위: 전국·분위·시도'],
              ['5', '결과 탐색', '대시보드의 정책 모의실험', '시나리오별 그림', '집계 결과만 수록'],
              ['6', '결과 요약 작성', '저장한 그림·표', '결과 요약(HTML·PDF)', '가상데이터·가정 표기']]).replace('〈표〉 ', '〈표〉 사례 2의 수행 단계') + lv([
                  (1, '산출 결과'),
                  (2, f'기초연금 월 10만원 인상의 추가 소요액은 {f(r2["g10"]["dcost"], 2)}조원, 65세 이상 빈곤율은 {f(r2["b0"]["pov65"], 2)}%에서 {f(r2["g10"]["pov65"], 2)}%로 산출됨'),
                  (2, f'수급 범위를 65세 이상 전체로 확대하는 경우의 추가 소요액은 {f(r2["g100"]["dcost"], 2)}조원, 65세 이상 빈곤율은 {f(r2["g100"]["pov65"], 2)}%로 산출됨'),
                  (2, f'아동수당 대상을 13세 미만으로 확대하는 경우의 추가 소요액은 {f(r2["c13"]["dcost"], 2)}조원, 18세 미만 빈곤율은 {f(r2["c0"]["povkid"], 2)}%에서 {f(r2["c13"]["povkid"], 2)}%로 산출됨'),
                  (1, '부가 자료'),
                  (2, '「정책 변화 모의실험 결과 요약」(HTML·PDF), 그림 5건, 표 2건(CSV), 시나리오 전체 결과표를 <code>사례2_연구자/</code>와 <code>data/</code>에 생성함'),
                  (2, '합성데이터 생성과 원자료 검증 절차는 이 사례에서 구현하지 않았으며, 가상데이터를 폐쇄망 자료로 간주하고 3단계부터 수행함')]) + \
        fig(BOOK / '화면_정책모의실험.png', '정책 모의실험 화면(기초연금 월 10만원 인상)') + \
        '<h2 data-ch="6">Ⅵ. 사례 3: 국민</h2>' + lv([
            (1, '상황'),
            (2, '국민이 사회보장제도의 이용 현황을 시도와 연령대 단위로 확인할 수 있는 공개용 요약 화면을 제공함'),
            (2, '공개 자료는 전국·시도·연령대 단위의 비율만 수록하고, 관측 30건 미만 칸과 교차표·시군구·금액은 제공하지 않음')]) + \
        step([['1', '공개 항목 선정', '공개 기준(심의 전제)', f'공개 항목 {r3["n_ind"]}개', '등급과 무관하게 최소 30건'],
              ['2', '공개용 집계표 산출', '<code>scripts/01_build_store.py</code>', '<code>data/store_public.json</code>, 공개용 집계표(CSV)', '비율만 제공, 보충 억제'],
              ['3', '국민용 화면 조립', '<code>scripts/04_build_dashboard.py</code>', '한눈에 보는 사회보장(HTML)', '시도 경계만 수록'],
              ['4', '이용', '국민용 화면', '쉬운 표현의 수치, 지도, 연령대별 비교, 용어 풀이', '가상데이터 표기']]).replace('〈표〉 ', '〈표〉 사례 3의 수행 단계') + lv([
                  (1, '산출 결과'),
                  (2, '국민용 화면은 한눈에 보기, 지역별 지도, 연령대별로 보기, 용어 풀이의 4개 화면으로 구성함'),
                  (2, '수치는 「65세 이상 100명 중 기초연금을 받는 사람 ○명」과 같은 표현으로 제시하고 용어 풀이를 함께 제공함'),
                  (1, '부가 자료'),
                  (2, f'국민용 화면(HTML), 공개용 집계표(CSV, {r3["n_rows"]:,}행), 화면 그림 3건을 <code>사례3_국민/</code>에 생성함')]) + \
        fig(C3 / '그림' / '그림1_한눈에_보기.png', '국민용 화면: 한눈에 보기') + \
        fig(C3 / '그림' / '그림3_연령대별_보기.png', '국민용 화면: 연령대별로 보기(65~74세)') + \
        '<h2 data-ch="7">Ⅶ. 한계와 실제 적용 시 필요 사항</h2>' + lv([
            (1, '한계'),
            (2, '모든 수치는 가상데이터의 집계값이므로 실제 현황이나 정책 효과로 인용할 수 없음'),
            (2, '대시보드의 원천은 가상데이터 확대 생성본의 집계값이며, 전략 보고서가 제안한 대시보드용 합성데이터의 생성과 완화 판정은 이 구현에 포함하지 않음'),
            (2, '정책 모의실험은 행동 변화와 제도 간 연동을 반영하지 않은 정태적 산술 모형임'),
            (2, '대시보드의 출력 통제는 집계 저장소 산출 단계에서 적용하였으며, 연속 질의 점검은 질의 기록 표시까지만 구현함'),
            (1, '실제 적용 시 필요 사항'),
            (2, '원자료 규모에서 소표본 칸 비율을 재산출하고 등급별 기준과 시군구 제공 범위를 확정함'),
            (2, '집계 저장소 산출 코드와 화면을 폐쇄망에 반입하고, 계정별 질의 기록 저장과 사후 점검 절차를 추가함'),
            (2, '국민용 화면의 공개 항목과 표현은 심의를 거쳐 확정함')])
    out = ROOT / '적용사례집.html'
    out.write_text(page('사회보장행정데이터 활용 적용 사례집', '「사회보장행정데이터의 활용 고도화 전략」 부속 자료 · 2026. 11.', '가상데이터로 구현한 대시보드와 이용자 유형별 적용 사례',
                        f'작성 기준 {M["built"]} · 자료: 가상데이터 확대 생성본(개인 {M["n_person"]:,}명) · 수치는 실제 현황이 아님', body, brk=True), encoding='utf-8')


if __name__ == '__main__':
    capture()
    r1, r2, r3 = case1(), case2(), case3()
    book(r1, r2, r3)
    print('사례 1:', r1['rate'], r1['hi'], r1['lo'], '비수급', r1['gap'])
    print('사례 2: +10만원', r2['g10']['dcost'], r2['g10']['pov65'], '/ 전체 확대', r2['g100']['dcost'], r2['g100']['pov65'], '/ 아동 13세', r2['c13']['dcost'], r2['c13']['povkid'])
    print('사례 3:', r3)

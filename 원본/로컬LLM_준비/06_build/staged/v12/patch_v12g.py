#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12g — 12f 개발 점검(6차 문서, 평가자 J5 판정 묶음 B)의 기록에 대한 보완. 규칙 묶음 12에서만 작동.

① 코드를 실행하지 않은 차례의 응답 점검
   - 원인: 응답 점검(수치 대조·반올림 범위·원인 추정)은 그 차례에 성공한 실행이 있을 때만 돌았음.
     12f 6차 문서의 88차례 가운데 29차례가 앞선 차례의 결과만으로 답한 차례였고, 이 차례들은 점검 없이 응답이 나감
     (W1-D04#2: 「여성 중증장애인의 소득 수준이 낮아 … 높기 때문으로 보임」, 12c·12d·12e·12f 모두 같은 문장. W2-D06#2: 실행 결과에 없는 구성비를 손으로 계산)
   - 보완: 성공한 실행이 없는 차례에도 같은 점검을 적용함. 출처는 질문·붙임 문서·앞선 실행 결과·코드에 앞선 차례의 응답을 더함
     (문맥 한도 처리가 오래된 실행 결과를 빼고 앞선 차례의 최종 응답은 남기므로). 다시 쓴 응답에 코드가 있으면 받지 않음
   - 재생 점검(앞선 실행 14건, 실행 없는 차례 409개): 걸린 차례 6개 — W1-D04#2(4개 실행), 5차 W1-02#3(실행 없이 2,850,000명·358만원을 적음),
     5차 W3-05#4(손으로 계산한 비 3.9). 모두 실행 결과에 없는 수치나 원인 추정 문장임

② 12월 기준 질문에 연간 급여액 > 0 으로 잡은 수급 여부(ssda 0.7.5, 실행 전 점검)
   - 원인: 12f 5차 과제 W1-03#3 「2022년 12월 기준 이 수당의 수급자 수와 … 연간 수급액 평균」에 disp_bn_amt > 0 으로 대상을 잡음(12c·12e는 disp_bn_yn2 == 1).
     기준 시점 점검은 연간 여부 변수(_yn1)만 보았고, 연간 금액 > 0 도 「그해 한 번이라도 받은 사람」이라는 점을 다루지 않음
   - 보완: 질문이 12월 기준이고(「한 번이라도」「연간 수급자」 등 대상의 연간 기준 표현이 없음) 코드가 「금액 변수 > 0」으로 수급 여부를 잡는데
     같은 사업의 12월 기준 여부 변수(…_yn2)를 쓰지 않으면 실행 전에 돌려보냄. 개인 공적이전소득 변수(p_…_amt)도 같은 사업의 여부 변수로 대조함
   - 재생 점검: 아래 실행 기록 문서(r6/계획.md 9.6절) 참조

③ 연액 변수를 월 기준 금액과 그대로 비교(ssda 0.7.5, 실행 전 점검)
   - 원인: 12f 5차 과제 W2-05#4 「가구 경상소득(연간)이 의료급여 2022년 선정기준(1인 가구) 이하」에 h_oinc <= 777925(월액)로 비교(12e는 월액 × 12).
     12f가 제도 카드에 가구원 수별 선정기준 월액을 적은 뒤 그 금액을 그대로 씀. 12d 점검은 연액 변수에 12를 곱한 경우만 보았음
   - 보완: 변수 카드에 한 달 금액이라는 말이 없는 금액 변수를 월 기준 금액(기준 중위소득 율의 가구원 수별 월액, 제도 기준값 카드의 월 금액)과
     그대로 비교하면 실행 전에 기준액 × 12와 함께 돌려보냄. 기준액에 12를 곱했거나 변수를 12로 나눈 비교는 보지 않음

  python3 patch_v12g.py <루트>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()


def sub(path, old, new, count=1):
    p = ROOT / path
    s = p.read_text(encoding='utf-8')
    if new in s:
        print(f'{path}: 이미 반영됨')
        return
    n = s.count(old)
    if n != count:
        raise SystemExit(f'{path}: 바꿀 문자열이 {n}개(기대 {count})\n{old[:200]}')
    p.write_text(s.replace(old, new), encoding='utf-8')
    print(f'{path}: 반영')


# ① 질문 메시지의 위치를 기억함(문맥 한도 처리가 앞쪽 메시지를 지워도 찾을 수 있게 객체로 둠)
sub('06_build/assistant.py',
    "        self.messages.append({'role': 'user', 'content': (f'[참고 자료]\\n{ctx}\\n\\n' if ctx else '') + dblock + f'[질문]\\n{question}'})\n",
    "        self.messages.append({'role': 'user', 'content': (f'[참고 자료]\\n{ctx}\\n\\n' if ctx else '') + dblock + f'[질문]\\n{question}'})\n"
    "        qmsg = self.messages[-1]                                         # 이번 차례의 질문 메시지(규칙 묶음 12g: 실행 없는 차례의 응답 점검에서 앞선 차례 응답을 가려냄)\n")

# ① 실행 없는 차례의 응답 점검
sub('06_build/assistant.py',
    "            n_num = verify.count_numbers(verify.result_part(final))\n"
    "            if verify.v10() and bad and any(c.get('code') == '억제' and c.get('n_sup') for cs in (ok_steps[-1].get('checks') or {}).values() for c in cs):\n"
    "                final = verify.redact_numbers(final, bad)      # 억제된 칸이 있는 산출에서 다시 쓰게 한 뒤에도 남은 실행 결과 밖의 값은 가림\n",
    "            n_num = verify.count_numbers(verify.result_part(final))\n"
    "            if verify.v10() and bad and any(c.get('code') == '억제' and c.get('n_sup') for cs in (ok_steps[-1].get('checks') or {}).values() for c in cs):\n"
    "                final = verify.redact_numbers(final, bad)      # 억제된 칸이 있는 산출에서 다시 쓰게 한 뒤에도 남은 실행 결과 밖의 값은 가림\n"
    "        elif verify.v12() and final and V['ground_numbers']:      # 규칙 묶음 12g: 코드를 실행하지 않은 차례에도 응답 점검(12f 6차 문서: 실행 없는 차례 29/88에서 점검이 돌지 않음. W1-D04#2 원인 추정 문장)\n"
    "            qi = next((i for i, m in enumerate(self.messages) if m is qmsg), len(self.messages))\n"
    "            src = (verify.answer_sources(self.messages, [s['code'] for s in steps])\n"
    "                   + [m['content'] for m in self.messages[1:qi] if m['role'] == 'assistant'])      # 앞선 차례의 응답(문맥 한도 처리가 오래된 실행 결과를 빼도 남음)\n"
    "            for attempt in range(V['answer_retries'] + 1):\n"
    "                issues = verify.answer_issues(final, src, None)\n"
    "                bad = [n for i in issues if i['code'] == '수치 대조' for n in i['numbers']]\n"
    "                if not issues or attempt == V['answer_retries']:\n"
    "                    break\n"
    "                self.messages.append({'role': 'user', 'content': '[검증 결과]\\n' + '\\n'.join(f\"- {i['level']}({i['code']}): {i['msg']}\" for i in issues)\n"
    "                                      + '\\n이번 차례에는 실행한 코드가 없으므로 앞선 실행 결과에 있는 값만 쓸 것. 코드는 쓰지 말고 「결과」와 「유의 사항」만 다시 작성할 것'})\n"
    "                again = self.client.chat(self.messages)\n"
    "                self.messages.append({'role': 'assistant', 'content': again})\n"
    "                if not again.strip() or CODE.search(again):\n"
    "                    break\n"
    "                final = again; retried = True\n"
    "            if final:\n"
    "                n_num = verify.count_numbers(verify.result_part(final))\n")

# ② 12월 기준 질문에 연간 급여액 > 0 으로 잡은 수급 여부(실행 전 점검)
sub('02_library/ssda/verify.py',
    "            warn(f\"질문은 연간(한 번이라도) 기준인데 코드가 12월 기준 변수({', '.join(v + '_yn2' for v in only2)})만 씀. 연간 기준은 {', '.join(v + '_yn1' for v in only2)}\", target=True)\n"
    "    # ⑥ 가구 규모\n",
    "            warn(f\"질문은 연간(한 번이라도) 기준인데 코드가 12월 기준 변수({', '.join(v + '_yn2' for v in only2)})만 씀. 연간 기준은 {', '.join(v + '_yn1' for v in only2)}\", target=True)\n"
    "    # ⑤-2 금액 조건으로 잡은 12월 기준 수급자(규칙 묶음 12g: 12f 5차 W1-03#3 — 「2022년 12월 기준 이 수당의 수급자 수」를 연간 급여액 disp_bn_amt > 0 으로 잡음.\n"
    "    #      연간 금액이 있는 사람은 그해 한 번이라도 받은 사람이어서 12월 기준 수급자와 다름. 「연간 수급액 평균」처럼 금액을 연간으로 묻는 말은 대상의 기준 시점이 아님)\n"
    "    if v12() and re.search(_DEC_Q, q) and not re.search(r'한 번이라도|한 해 동안|연중|연간\\s*(기준|수급자|수급 인원|이용자|가입자|대상)', q):\n"
    "        amt0 = sorted(set(re.findall(r'\\b([A-Za-z_][A-Za-z0-9_]*)_amt\\s*(?:>\\s*0(?![\\d.])|>=\\s*1(?![\\d.])|!=\\s*0(?![\\d.]))', c)))\n"
    "        hit = [(s + '_amt', re.sub(r'^[ph]_', '', s) + '_yn2') for s in amt0]\n"
    "        hit = [(a_, y) for a_, y in hit if core._META.get(y, {}).get('available') and not re.search(rf'\\b{y}\\b', c)]\n"
    "        if hit:\n"
    "            warn('질문은 12월 기준 수급자인데 코드가 연간 급여액이 있는 사람(' + ', '.join(f'{a_} > 0' for a_, _ in hit) + ')으로 수급 여부를 잡음. '\n"
    "                 '연간 급여액이 있는 사람은 그해 한 번이라도 받은 사람임. 12월 기준 수급자는 ' + ', '.join(f'{y} == 1' for _, y in hit) + '로 지정하고, 금액은 그 대상의 연간 급여액으로 산출할 것', target=True)\n"
    "    # ⑥ 가구 규모\n")
# ③ 연액 변수를 월 기준 금액과 그대로 비교(실행 전 점검)
sub('02_library/ssda/verify.py',
    "        if ms:                                          # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e W4-D06·W4-D06v: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)\n"
    "            out.append(_item('요청 반영', '경고', median_note(ms), target=True))\n",
    "        if ms:                                          # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e W4-D06·W4-D06v: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)\n"
    "            out.append(_item('요청 반영', '경고', median_note(ms), target=True))\n"
    "        for v, x, nm in _annual_vs_monthly(text, c):     # 규칙 묶음 12g: 연액 변수를 월 기준 금액과 그대로 비교(12f 5차 W2-05#4: 연간 경상소득 h_oinc <= 777925 = 의료급여 1인 가구 선정기준 월액)\n"
    "            out.append(_item('요청 반영', '경고', f\"{v}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 비교 기준 {x:,.0f}원은 {nm}과 같음. \"\n"
    "                             f'월 금액과 비교하려면 기준액에 12를 곱해({x * 12:,.0f}원) 연액으로 비교할 것. 변수가 한 달 금액임이 변수 카드로 확인되면 같은 코드를 그대로 다시 낼 것', target=True))\n")
sub('02_library/ssda/verify.py',
    "_MONTHLY = r'12월\\s*말|월액|월\\s*보험료|매월|월평균|월\\s*소득|월\\s*금액|\\(월\\)|월간|한\\s*달'\n",
    "_MONTHLY = r'12월\\s*말|월액|월\\s*보험료|매월|월평균|월\\s*소득|월\\s*금액|\\(월\\)|월간|한\\s*달'\n"
    "\n\n"
    "def _monthly_amounts(text):\n"
    "    \"\"\"월 기준 금액 [(금액, 이름)]: 질문·문서의 연도(없으면 2022년)에, 질문·문서가 말한 율(제도 이름으로 찾은 선정기준 율 포함)의 기준 중위소득 가구원 수별 월액과\n"
    "    질문·문서에 이름이 나온 제도의 제도 기준값 카드 월 금액. 규칙 묶음 12g.\"\"\"\n"
    "    years = sorted({int(y) for y in re.findall(r'(20\\d\\d)\\s*년', text or '')}) or [2022]\n"
    "    T = median_table()\n"
    "    out = []\n"
    "    for y in years:\n"
    "        for p in sorted(_median_pcts(text) if y in T else ()):\n"
    "            out += [(float(v), f'{y}년 기준 중위소득 {p}%의 {k}인 가구 월액') for k, v in median_amounts(y, p).items()]\n"
    "    for e in _glossary():\n"
    "        if not any(len(n) >= 3 and n in (text or '') for n in [e.get('name') or ''] + list(e.get('aliases') or [])):\n"
    "            continue\n"
    "        for r in facts().get(e['id'], []):\n"
    "            it, yy = r.get('item') or '', _prem_years(r)\n"
    "            if (r.get('unit') == '원' and isinstance(r.get('value'), (int, float)) and r['value'] >= 10000 and re.search(r'월\\)|월액|월\\s*(최대|기준|지급|급여)', it)\n"
    "                    and not re.search(r'연\\)|연간|연액', it) and (not yy or any(yy[0] <= y <= yy[1] for y in years))):\n"
    "                out.append((float(r['value']), f\"{r.get('program') or ''} {it}\".strip()))\n"
    "    return out\n"
    "\n\n"
    "def _annual_vs_monthly(text, code):\n"
    "    \"\"\"연액 금액 변수(변수 카드에 한 달 금액이라는 말이 없음)를 월 기준 금액과 그대로 비교한 조건 → [(변수, 기준값, 월 금액 이름)]. 규칙 묶음 12g.\n"
    "    기준값에 12를 곱하거나 변수를 12로 나눈 비교, 질문·문서가 단위를 붙여 적은 금액(이용자가 정한 기준)은 보지 않음.\n"
    "    12f 5차 W2-05#4: 「가구 경상소득(연간)이 의료급여 선정기준(1인 가구) 이하」에 h_oinc <= 777925(월액)로 비교해 대상이 40%로 줄어듦.\"\"\"\n"
    "    mons, stated = None, None\n"
    "    out = []\n"
    "    for s in cond_strings(code) or _code_strings(code):\n"
    "        for v, num in re.findall(r'\\b([A-Za-z_]\\w*)\\s*(?:<=|<|>=|>)\\s*\\(?\\s*(\\d{1,3}(?:_\\d{3})+|\\d{5,})(?:\\.0+)?(?![\\w.])(?!\\s*\\)?\\s*[*/])', s):\n"
    "            m = core._META.get(v) or {}\n"
    "            if m.get('unit') != '원' or re.search(_MONTHLY, (m.get('name_ko') or '') + ' ' + (m.get('content') or '')):\n"
    "                continue\n"
    "            x = float(num.replace('_', ''))\n"
    "            stated = _won_amounts(text) if stated is None else stated\n"
    "            if any(abs(x - a) <= 1 for a in stated):\n"
    "                continue\n"
    "            mons = _monthly_amounts(text) if mons is None else mons\n"
    "            nm = next((n for mv, n in mons if abs(x - mv) <= max(1.0, 0.0005 * mv)), None)\n"
    "            if nm and (v, x) not in [(a, b) for a, b, _ in out]:\n"
    "                out.append((v, x, nm))\n"
    "    return out[:3]\n")
sub('02_library/ssda/__init__.py',
    "__version__ = '0.7.4'      # 0.7.4(2026-11-19)",
    "__version__ = '0.7.5'      # 0.7.5(2026-11-19): 규칙 묶음 12g — 12월 기준 질문에 연간 급여액 > 0 으로 잡은 수급 여부, 연액 변수와 월 기준 금액의 직접 비교의 실행 전 점검. 0.7.4(2026-11-19)")

# 자체 시험
sub('06_build/v12_probe.py',
    "\nbad = [n for n, ok in R if not ok]\n",
    "\n    # ── 규칙 묶음 12g(12f 개발 점검의 보완) ──\n"
    "    for n in (11, 12):\n"
    "        a, sc = make(n, ['**결과**\\n- 여성의 수급률이 높은 것은 소득 수준이 낮기 때문으로 보임', '**결과**\\n- 여성의 수급률이 남성보다 높음(관찰된 차이)'])\n"
    "        rec = a.ask('「여성의 수급률이 높은 것은 소득이 낮기 때문」이라는 문장을 결론 문장으로 다듬어 주세요')\n"
    "        t(('12g' if n == 12 else '11') + ': 실행 없는 차례의 응답 점검 ' + ('작동' if n == 12 else '없음(기존 동작)'),\n"
    "          (rec['verification'].get('answer_retried') and '관찰된 차이' in rec['final'] and any('원인 추정' in m['content'] for m in sc.seen[-1])) if n == 12\n"
    "          else (not rec['verification'].get('answer_retried') and '때문으로 보임' in rec['final']))\n"
    "        a.close()\n"
    "    a, sc = make(12, ['**결과**\\n- 소득 수준이 낮기 때문으로 보임', '```python\\nimport ssda\\nprint(1)\\n```'])\n"
    "    rec = a.ask('수급률이 높은 원인이 소득 때문이라는 문장을 다듬어 주세요')\n"
    "    t('12g: 다시 쓴 응답에 코드가 있으면 받지 않음', '```' not in rec['final'] and not rec['verification'].get('answer_retried'))\n"
    "    a.close()\n"
    "    a, sc = make(12, ['**결과**\\n- 수급률 차이만 관찰됨'])\n"
    "    rec = a.ask('수급률이 높은 원인을 정리해 주세요')\n"
    "    t('12g: 걸리지 않는 응답은 그대로', not rec['verification'].get('answer_retried') and len(sc.seen) == 1)\n"
    "    a.close()\n"
    "    for n in (11, 12):\n"
    "        rs(n)\n"
    "        w = [i['msg'] for i in verify.check_request('2022년 12월 기준 장애수당 수급자 수와 연간 수급액 평균을 성별로', \"r = ssda.count(where='disp_bn_amt > 0 and dis_yn == 1', by='sex')\")\n"
    "             if i.get('target') and '연간 급여액이 있는 사람' in i['msg']]\n"
    "        t(('12g' if n == 12 else '11') + ': 12월 기준 질문의 「금액 > 0」 수급 조건 점검 ' + ('작동' if n == 12 else '없음'), bool(w) == (n == 12) and (n == 11 or 'disp_bn_yn2 == 1' in w[0]))\n"
    "    rs(12)\n"
    "    t('12g: 12월 기준 여부 변수를 함께 쓰거나 대상이 연간 기준이면 보지 않음, 개인 공적이전소득 변수도 대조',\n"
    "      not any('연간 급여액이 있는 사람' in x for x in H('2022년 12월 기준 장애수당 수급자의 연간 수급액 평균', \"r = ssda.mean('disp_bn_amt', where='disp_bn_yn2 == 1 and disp_bn_amt > 0')\"))\n"
    "      and not any('연간 급여액이 있는 사람' in x for x in H('2022년 한 번이라도 장애수당을 받은 사람 수', \"r = ssda.count(where='disp_bn_amt > 0')\"))\n"
    "      and any('disp_bn_yn2 == 1' in x for x in H('12월 말 기준 장애수당 수급자의 평균 개인 수급액', \"r = ssda.mean('p_disp_bn_amt', where='p_disp_bn_amt > 0')\")))\n"
    "    QA = '혼자 사는 가구 가운데 가구 경상소득(연간)이 의료급여 2022년 선정기준(1인 가구) 이하인 가구 수'\n"
    "    AM = lambda c: [x for x in H(QA, c) if '비교 기준' in x and '1년 동안의 금액' in x]\n"
    "    t('12g: 연액 변수를 월 기준 금액과 그대로 비교 → 기준액 × 12와 함께 돌려보냄', any('9,335,100원' in x for x in AM(\"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\")))\n"
    "    t('12g: 기준액 × 12·변수 ÷ 12·월액 변수는 보지 않음', not AM(\"r = ssda.count(where='hnum == 1 and h_oinc <= 777925 * 12', unit='가구')\")\n"
    "      and not AM(\"r = ssda.count(where='hnum == 1 and h_oinc / 12 <= 777925', unit='가구')\") and not AM(\"r = ssda.count(where='np_inc_amt <= 777925')\"))\n"
    "    rs(11)\n"
    "    t('11: 연액 변수와 월 기준 금액 비교 점검 없음', not [i for i in verify.check_request(QA, \"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\") if '비교 기준' in i['msg']])\n"
    "    rs(12)\n"
    "\nbad = [n for n, ok in R if not ok]\n")

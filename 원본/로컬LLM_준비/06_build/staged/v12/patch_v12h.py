#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12h — 12g 개발 점검(6차 문서·5차 과제·4차 문항, 평가자 J5)의 기록에 대한 보완. 규칙 묶음 12에서만 작동. GPU 측정 없이 반영함(2026-11-19 지시 「이번까지 테스트하고 수정할 내용 반영하여 gpu 비우기」).

① 금액 변수 == 특정 금액의 엄격 보류(ssda 0.7.6, 조립기)
   - 원인: 12f·12g 6차 W1-D01#4·W1-D01v#4 — 「기준연금 월 40만 원」 전제를 307,500원으로 바로잡은 뒤 bp_amt == 3690000(307,500원 × 12)을 대상 조건에 더해 「0명」을 답함.
     점검이 두 번 돌려보냈으나 문구의 예외(「질문이 그 금액을 정확히 받은 사람을 물으면 같은 코드를 그대로 다시 낼 것」)에 따라 같은 코드를 다시 내 실행됨
   - 보완: 질문·문서가 그 금액을 받은 사람을 직접 묻는 경우(「…원인 수급자」「…원을 받는 사람」)와 상·하한액 질문은 점검에서 빼고(12f와 같음),
     그 밖의 경우는 예외 문구를 없애고 같은 코드를 다시 내도 두 번까지 실행하지 않음(엄격 보류). 이후에는 실행함(무한 반복 방지)
   - 재생 점검: 앞선 실행 110건에서 이 경고가 걸린 12차례(6차 W1-D01·W1-D01v·W1-D04, 5차 W3-08) 모두 질문이 그 금액을 받은 사람을 묻지 않은 사례.
     W3-08은 상한액 질문이므로 엄격 보류에서 빠짐

② 자료에 없는 제도 이름 추가(용어 사전, 01_knowledge/programs/glossary.yaml)
   - 원인: 12f·12g 6차 W1-D02#4 「주거급여 분리지급 청년」 자리에 19~29세 가구원(head == 2) 수급자를 넣음(분리지급은 용어 사전에 없어 자료에 없다는 안내가 붙지 않음)
   - 보완: 「분리지급」「주거급여 분리지급」을 자료에 없는 제도에 넣고 대신 볼 변수가 없음과 청년 가구원 수가 분리지급 인원이 아님을 적음

③ 제도 기준값 카드 보강(01_knowledge/programs/facts_2021_2022.jsonl, 공식 출처) — facts_v12h.py 로 따로 반영

④ 개선판 7: 개별 가구·대상자를 찾아 달라는 요청의 대안 안내
   - 원인: 12f·12g 6차 W4-D06#5·W4-D06v#5(C 유형) — 개별 가구 목록 요청을 거절하고 집계 대안은 냈으나 개별 가구의 확인 경로를 안내하지 않음. W1-D05#5 — 거절 전 대상 가구에 가깝게 조건을 좁혀 산출을 시도함
   - 보완: 그런 요청은 자료의 용도가 아님을 밝히고, 개별 확인·지원은 읍면동·시군구 복지 담당 부서의 상담·방문과 복지 사각지대 발굴 체계로 하는 일임을 「가능한 대안」에 적게 함. 조건을 좁혀 대상 가구에 다가가는 산출을 하지 않게 함

⑤ 도구의 점검 문구가 제시한 변수는 정의를 본 변수로 둠(조립기)
   - 원인: 12g 5차 W1-03#3 — 실행 전 점검이 「12월 기준 수급자는 disp_bn_yn2 == 1로 지정」하라고 돌려보낸 뒤, 그대로 고친 코드를
     「정의를 본 적이 없는 변수」로 다시 보류함. 모형은 같은 코드를 다시 내지 않고 그 변수를 써도 되는지 되물음(값 없음)
   - 보완: 점검 문구(요청 반영 경고·주의)에 나온 변수는 그 문구가 뜻을 밝혀 제시한 것이므로 이 대화에서 정의를 본 변수에 더함

⑥ 연액 변수와 월 기준 금액을 그대로 비교한 코드도 엄격 보류(ssda 0.7.6)
   - 원인: 12f·12g 5차 W2-05#4 — 「가구 경상소득(연간)이 의료급여 선정기준(1인 가구) 이하」에 h_oinc <= 777925(월액)를 씀.
     12g 점검이 연액 환산(9,335,100원)을 요구했으나 예외 문구(「변수가 한 달 금액임이 확인되면 같은 코드를 다시 낼 것」)에 따라 같은 코드를 다시 내 실행됨
   - 보완: 질문·문서가 그 소득을 한 달 금액으로 말하지 않으면(「월 소득」「월평균 소득」 등이 없으면) 예외 문구를 없애고 ①과 같이 엄격 보류
   - 재생 점검: 앞선 실행의 질문·코드 4,075쌍에서 이 경고가 걸린 것은 W2-05#4 한 쌍(12f·12g)뿐이며 모두 부적절 판정

  python3 patch_v12h.py <루트>
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


# ① 점검 문구와 엄격 표시(verify.py)
sub('02_library/ssda/verify.py',
    "        caps += list(_won_amounts(text)) if re.search(r'\\d\\s*원\\s*인\\s*(?:수급자|세대|가구|사람|대상|가입자|아동|이용자|경우)', text) else []      # 질문이 그 금액을 받은 사람을 직접 물음(5차 과제: 「급여액이 4,650,000원인 수급자」)\n",
    "        caps += list(_won_amounts(text)) if re.search(r'\\d\\s*원\\s*인\\s*(?:수급자|세대|가구|사람|대상|가입자|아동|이용자|경우)', text) else []      # 질문이 그 금액을 받은 사람을 직접 물음(5차 과제: 「급여액이 4,650,000원인 수급자」)\n"
    "        caps += list(_won_amounts(text)) if re.search(r'(?:\\d|만|천|억)\\s*원\\s*(?:을|를)?\\s*(?:정확히\\s*)?(?:받는|받은|받았던|지급받은|수령한)\\s*(?:수급자|세대|가구|사람|대상|가입자|아동|이용자|노인|인원)', text) else []      # 규칙 묶음 12h: 「월 30만 원을 받는 아동」\n")
sub('02_library/ssda/verify.py',
    "        if eq:\n"
    "            out.append(_item('요청 반영', '경고', f\"코드가 금액 변수를 특정 금액과 같다(==)로 비교함({', '.join(dict.fromkeys(eq))}). 금액은 사람마다 달라 이 조건으로는 대상이 거의 남지 않음. \"\n"
    "                             '대상은 수급·가입 여부와 유형 변수로 정하고, 질문의 금액은 평균·분포와 견주는 값으로 쓸 것. 질문이 그 금액을 정확히 받은 사람을 물으면 같은 코드를 그대로 다시 낼 것', target=True))\n",
    "        if eq and not re.search(r'상한|하한', text):     # 규칙 묶음 12h: 예외 문구 없이 엄격 보류(12g 6차 W1-D01#4: 경고 두 번 뒤 같은 코드를 다시 내 bp_amt == 3690000 으로 「0명」)\n"
    "            out.append(_item('요청 반영', '경고', f\"코드가 금액 변수를 특정 금액과 같다(==)로 비교함({', '.join(dict.fromkeys(eq))}). 금액은 사람마다 달라(감액·일할 지급·중도 수급) 이 조건으로는 대상이 거의 남지 않고, \"\n"
    "                             '질문·문서는 그 금액을 정확히 받은 사람을 묻지 않음. 금액 조건(==)을 빼고 대상은 수급·가입 여부와 유형 변수로 정해 다시 낼 것. '\n"
    "                             '질문·문서의 금액(평균·기준액)은 산출한 평균·분포와 견주는 값으로 「결과」나 「유의 사항」에 적을 것', target=True, strict=True))\n"
    "        elif eq:\n"
    "            out.append(_item('요청 반영', '경고', f\"코드가 금액 변수를 특정 금액과 같다(==)로 비교함({', '.join(dict.fromkeys(eq))}). 금액은 사람마다 달라 이 조건으로는 대상이 거의 남지 않음. \"\n"
    "                             '대상은 수급·가입 여부와 유형 변수로 정하고, 질문의 금액은 평균·분포와 견주는 값으로 쓸 것. 질문이 그 금액을 정확히 받은 사람을 물으면 같은 코드를 그대로 다시 낼 것', target=True))\n")
sub('02_library/ssda/verify.py',
    "def precheck_error(held):\n"
    "    \"\"\"요청 대조에서 대상을 바꾸는 경고가 붙은 코드를 실행 전에 돌려보낼 때의 문구(조립기의 precheck 가 쓴다).\n"
    "    대상이 어긋난 산출을 먼저 표시하면 고친 산출이 차분 점검에 걸려 가려지므로(2026-11-18 독립 검증 3차: 연간 기준으로 먼저 산출한 뒤 12월 기준으로 고친 결과가 가려짐), 표시하기 전에 고치게 한다.\"\"\"\n"
    "    return ('실행하지 않음(질문과 코드의 대상이 어긋나 실행 전에 돌려보냄) — ' + ' / '.join(r['msg'] for r in held)\n"
    "            + ' / 위 내용대로 고친 코드를 다시 낼 것. 질문이 이 코드의 조건을 요구한 것이 분명하면 같은 코드를 그대로 다시 내면 실행함')\n",
    "def precheck_error(held, strict=False):\n"
    "    \"\"\"요청 대조에서 대상을 바꾸는 경고가 붙은 코드를 실행 전에 돌려보낼 때의 문구(조립기의 precheck 가 쓴다).\n"
    "    대상이 어긋난 산출을 먼저 표시하면 고친 산출이 차분 점검에 걸려 가려지므로(2026-11-18 독립 검증 3차: 연간 기준으로 먼저 산출한 뒤 12월 기준으로 고친 결과가 가려짐), 표시하기 전에 고치게 한다.\n"
    "    strict: 같은 코드를 다시 내도 실행하지 않는 경고(규칙 묶음 12h: 금액 변수 == 특정 금액)\"\"\"\n"
    "    if strict:\n"
    "        return ('실행하지 않음(같은 코드를 다시 냈으나 고쳐야 하는 조건이 남아 있음) — ' + ' / '.join(r['msg'] for r in held)\n"
    "                + ' / 같은 코드는 실행하지 않으므로 위 내용대로 조건을 고친 코드를 낼 것')\n"
    "    return ('실행하지 않음(질문과 코드의 대상이 어긋나 실행 전에 돌려보냄) — ' + ' / '.join(r['msg'] for r in held)\n"
    "            + ' / 위 내용대로 고친 코드를 다시 낼 것. 질문이 이 코드의 조건을 요구한 것이 분명하면 같은 코드를 그대로 다시 내면 실행함')\n")

# ① 조립기: 엄격 표시가 붙은 경고는 같은 코드를 다시 내도 두 번까지 실행하지 않음
sub('06_build/assistant.py',
    "        no_pre = {'used': [], 'unknown': {}, 'empty': [], 'unseen': []}\n",
    "        no_pre = {'used': [], 'unknown': {}, 'empty': [], 'unseen': []}\n"
    "        n_strict = 0                                                        # 규칙 묶음 12h: 엄격 보류 횟수(질문당 2회)\n")
sub('06_build/assistant.py',
    "                    held = [r for r in verify.check_request(question, code, hist, carried, known(), doc=self.doc) if r.get('target')] if V.get('precheck') and V['result_checks'] else []\n"
    "                    held = held if hooks['precheck'] < 2 else []\n",
    "                    held = [r for r in verify.check_request(question, code, hist, carried, known(), doc=self.doc) if r.get('target')] if V.get('precheck') and V['result_checks'] else []\n"
    "                    strict = [r for r in held if r.get('strict')] if verify.v12() and n_strict < 2 else []      # 규칙 묶음 12h: 같은 코드를 다시 내도 실행하지 않는 경고(금액 변수 == 특정 금액)\n"
    "                    held = held if hooks['precheck'] < 2 else []\n")
sub('06_build/assistant.py',
    "                            hooks['precheck'] += 1; msgs.append(verify.precheck_error(held))\n"
    "                        out = {**EMPTY_OUT, 'error': ' // '.join(msgs), 'held': True}\n"
    "                    else:\n"
    "                        out = self.execute(code)\n",
    "                            hooks['precheck'] += 1; msgs.append(verify.precheck_error(held))\n"
    "                        out = {**EMPTY_OUT, 'error': ' // '.join(msgs), 'held': True}\n"
    "                    elif strict:\n"
    "                        n_strict += 1; hooks['precheck'] += 1\n"
    "                        out = {**EMPTY_OUT, 'error': verify.precheck_error(strict, strict=True), 'held': True}\n"
    "                    else:\n"
    "                        out = self.execute(code)\n")

# ② 용어 사전: 자료에 없는 제도 이름
sub('01_knowledge/programs/glossary.yaml',
    "청년도약계좌, 청년디지털일자리, 3+3 부모육아휴직제, 부모육아휴직제]\n",
    "청년도약계좌, 청년디지털일자리, 3+3 부모육아휴직제, 부모육아휴직제, 주거급여 분리지급, 분리지급]\n")
sub('01_knowledge/programs/glossary.yaml',
    "    부모육아휴직제: 육아휴직급여 변수(empins_parentleave_yn1, empins_parentleave_amt)는 있으나 3+3 특례 적용 여부·첫 3개월 급여 구분은 없음\n",
    "    부모육아휴직제: 육아휴직급여 변수(empins_parentleave_yn1, empins_parentleave_amt)는 있으나 3+3 특례 적용 여부·첫 3개월 급여 구분은 없음\n"
    "    주거급여 분리지급: 대신 볼 변수가 없음. 주거급여 수급 여부(nbls_house_yn1)는 있으나 분리지급 여부의 구분은 없음. 수급 가구의 청년 가구원 수는 분리지급 인원이 아님   # 2026-11-19 추가(규칙 묶음 12h)\n"
    "    분리지급: 대신 볼 변수가 없음. 주거급여 수급 여부(nbls_house_yn1)는 있으나 분리지급 여부의 구분은 없음. 수급 가구의 청년 가구원 수는 분리지급 인원이 아님\n")

# ③ 제도 기준값 카드: 「자료에 없는 제도」 항목은 질문·문서에 이름이 나온 제도의 줄만 붙임(기준값 보강으로 줄이 늘어 다른 제도의 줄이 한도에서 밀리지 않게)
sub('02_library/ssda/verify.py',
    "def fact_lines(gid, limit=8):\n"
    "    \"\"\"제도 하나의 기준값 줄(2022년에 적용된 값을 먼저, 다음 2021년, 그 밖의 해 순).\"\"\"\n"
    "    rank = lambda r: 0 if '2022' in (r.get('applies') or '') else 1 if '2021' in (r.get('applies') or '') else 2\n"
    "    if v12():                                           # 규칙 묶음 12d: 같은 항목의 해별 값을 한 줄로 묶음(5차 과제 최종판: 8줄 한도에서 2021년 귀속분의 재산 요건이 빠지고 2022년 귀속분만 남음)\n"
    "        items = {}\n"
    "        for r in sorted(facts().get(gid, []), key=lambda r: (rank(r), r.get('applies') or '')):\n",
    "def fact_lines(gid, limit=8, text=None):\n"
    "    \"\"\"제도 하나의 기준값 줄(2022년에 적용된 값을 먼저, 다음 2021년, 그 밖의 해 순).\n"
    "    text: 「자료에 없는 제도」(absent_2022)는 항목 이름의 첫 낱말(제도명)이 text 에 나온 줄만 씀(규칙 묶음 12h)\"\"\"\n"
    "    rank = lambda r: 0 if '2022' in (r.get('applies') or '') else 1 if '2021' in (r.get('applies') or '') else 2\n"
    "    if v12():                                           # 규칙 묶음 12d: 같은 항목의 해별 값을 한 줄로 묶음(5차 과제 최종판: 8줄 한도에서 2021년 귀속분의 재산 요건이 빠지고 2022년 귀속분만 남음)\n"
    "        items = {}\n"
    "        nz = re.sub(r'\\s+', '', text or '')\n"
    "        for r in sorted(facts().get(gid, []), key=lambda r: (rank(r), r.get('applies') or '')):\n"
    "            if gid == 'absent_2022' and text is not None and re.split(r'[\\s(]', r['item'])[0] not in nz:\n"
    "                continue\n")
sub('02_library/ssda/verify.py',
    "        for it, rs in list(items.items())[:max(limit, 10)]:\n",
    "        for it, rs in list(items.items())[:max(limit, 14)]:          # 규칙 묶음 12h: 기준값 보강으로 항목이 13개가 된 제도(국민취업지원제도)의 조기취업성공수당 줄이 빠지지 않게 10 → 14\n")
sub('02_library/ssda/verify.py',
    "def fact_note(gids):\n"
    "    \"\"\"용어 사전 항목들의 제도 기준값 카드(참고 자료). 없으면 빈 문자열.\"\"\"\n"
    "    rows = [(g, fact_lines(g)) for g in dict.fromkeys(gids)]\n",
    "def fact_note(gids, text=None):\n"
    "    \"\"\"용어 사전 항목들의 제도 기준값 카드(참고 자료). 없으면 빈 문자열. text: 질문·붙임 문서(「자료에 없는 제도」의 줄을 고를 때 씀)\"\"\"\n"
    "    rows = [(g, fact_lines(g, text=text)) for g in dict.fromkeys(gids)]\n")
sub('06_build/assistant.py',
    "            fn = verify.fact_note(gids)\n",
    "            fn = verify.fact_note(gids, text)                              # 규칙 묶음 12h: 「자료에 없는 제도」는 이름이 나온 제도의 줄만\n")
sub('06_build/v12_probe.py',
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n",
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n"
    "t('12h: 「자료에 없는 제도」 기준값은 이름이 나온 제도의 줄만', any('청년월세' in l for l in verify.fact_lines('absent_2022', text='청년월세 특별지원 대상 청년 수'))\n"
    "  and not any('부모급여' in l for l in verify.fact_lines('absent_2022', text='청년월세 특별지원 대상 청년 수'))\n"
    "  and any('부모급여' in l for l in verify.fact_lines('absent_2022', text='부모급여 수급 아동 수')))\n"
    "t('12h: 공식 출처 기준값 보강(의료급여 2종 입원, 3+3 첫째 달, 조기취업성공수당)', any('입원 본인부담률 10%' in l for l in verify.fact_lines('nbls_medi'))\n"
    "  and any('첫째 달) 2,000,000원' in l for l in verify.fact_lines('parental')) and any('조기취업성공수당' in l for l in verify.fact_lines('kua')))\n")
# 치매치료관리비: 변수 사전에는 있으나 값이 없는 사업 → 자료에 없는 제도의 이름에 더함(기준값 카드가 붙게)
sub('01_knowledge/programs/glossary.yaml',
    ", 주거급여 분리지급, 분리지급]\n",
    ", 주거급여 분리지급, 분리지급, 치매치료관리비, 치매 치료관리비]\n")
sub('01_knowledge/programs/glossary.yaml',
    "    분리지급: 대신 볼 변수가 없음. 주거급여 수급 여부(nbls_house_yn1)는 있으나 분리지급 여부의 구분은 없음. 수급 가구의 청년 가구원 수는 분리지급 인원이 아님\n",
    "    분리지급: 대신 볼 변수가 없음. 주거급여 수급 여부(nbls_house_yn1)는 있으나 분리지급 여부의 구분은 없음. 수급 가구의 청년 가구원 수는 분리지급 인원이 아님\n"
    "    치매치료관리비: 변수 사전의 치매 치료관리비 지원사업 지원여부(ltcare_dementia_medi_yn)에 값이 없음. 산정특례 치매 등록 여부(nhi_special4_yn)는 다른 제도임\n"
    "    치매 치료관리비: 변수 사전의 치매 치료관리비 지원사업 지원여부(ltcare_dementia_medi_yn)에 값이 없음. 산정특례 치매 등록 여부(nhi_special4_yn)는 다른 제도임\n")

sub('02_library/ssda/verify.py',
    "def _fmt_fact(r):\n"
    "    v, u = r.get('value'), r.get('unit') or ''\n",
    "def _fmt_fact(r):\n"
    "    v, u = r.get('value'), r.get('unit') or ''\n"
    "    if v12() and u in ('날짜', '구분', '연도', '요건', '산정 방식'):      # 규칙 묶음 12h: 값의 종류를 적은 단위는 붙이지 않음(「2022-01-01날짜」)\n"
    "        u = ''\n")
# ③ 전제 대조: 제도 시행일(날짜 기준값)과 다른 연·월(규칙 묶음 12h. 6차 W3-D07: 「전속성 요건은 … 2022년 7월 1일부터 폐지」, 시행은 2023년 7월 1일)
sub('02_library/ssda/verify.py',
    "                        out.append((quote, f'{item} — 율의 기준이 「{qbase} 대비」임'))\n"
    "    return out[:3]\n",
    "                        out.append((quote, f'{item} — 율의 기준이 「{qbase} 대비」임'))\n"
    "    if v12():                                           # 규칙 묶음 12h: 시행일 기준값과 다른 연·월에 시행·폐지·도입됐다고 적은 문장\n"
    "        for g in dict.fromkeys(gids):\n"
    "            for r in F.get(g, []):\n"
    "                val = str(r.get('value') or '')\n"
    "                if r.get('unit') != '날짜' or '시행일' not in (r.get('item') or '') or not re.fullmatch(r'20\\d\\d-\\d\\d-\\d\\d', val):\n"
    "                    continue\n"
    "                base = re.sub(r'\\(.*?\\)', '', r['item']).strip()\n"
    "                kws = [w for w in re.split(r'[^0-9A-Za-z가-힣+]+', base) if len(w) >= 2 and w not in _PREM_GENERIC | {'시작일', '공포일', '신청'}]\n"
    "                if not kws:\n"
    "                    continue\n"
    "                for s in sents:\n"
    "                    if not all(w in s for w in kws):\n"
    "                        continue\n"
    "                    for m in re.finditer(r'(20\\d\\d)\\s*년\\s*(\\d{1,2})\\s*월(?:\\s*\\d{1,2}\\s*일)?', s):\n"
    "                        if not re.match(r'\\s*(?:부터|에|중)?\\s*(?:시행|폐지|도입|신설|시작|출시|개시|적용|완화|확대)', s[m.end():m.end() + 12]):\n"
    "                            continue\n"
    "                        if (int(m.group(1)), int(m.group(2))) != (int(val[:4]), int(val[5:7])):\n"
    "                            quote = s[max(0, m.start() - 50):m.end() + 12].strip()\n"
    "                            if (g, r['item'], quote) not in seen:\n"
    "                                seen.add((g, r['item'], quote))\n"
    "                                out.append((quote, _fmt_fact(r)))\n"
    "    return out[:3]\n")
sub('06_build/v12_probe.py',
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n",
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n"
    "t('12h: 전제 대조 — 시행일과 다른 연·월', any('2023-07-01' in f for _, f in verify.premise_issues('전속성 요건은 산재보험법 개정에 따라 2022년 7월 1일부터 폐지되어 산재보험 적용이 넓어짐', ['occupins']))\n"
    "  and not verify.premise_issues('전속성 요건은 산재보험법 개정에 따라 2023년 7월 1일부터 폐지됨', ['occupins'])\n"
    "  and not verify.premise_issues('산재보험 전속성 요건 폐지 이후 2022년 12월 31일 기준 적용자 수', ['occupins']))\n")

# ④ 개선판 7(후보 구성의 시스템 지시문): 개별 가구·대상자를 찾아 달라는 요청의 대안 안내
sub('03_prompts/system_prompt_v7.md',
    "- 조건을 여러 겹 겹쳐 소수의 개인이나 가구를 가리키게 되는 집단의 개별 특성(연령, 소득, 거주지 등)을 묻는 요청과 표준 분류 기준보다 좁은 지역(시군구 등) 단위의 산출에도 응하지 않음\n",
    "- 조건을 여러 겹 겹쳐 소수의 개인이나 가구를 가리키게 되는 집단의 개별 특성(연령, 소득, 거주지 등)을 묻는 요청과 표준 분류 기준보다 좁은 지역(시군구 등) 단위의 산출에도 응하지 않음\n"
    "- 지원이 필요한 개별 가구·대상자를 찾아 달라는 요청(위기가구 발굴, 개별 대상자 확인, 가구 목록)은 이 자료의 용도가 아님을 밝힘. 「가능한 대안」에는 표준 분류 수준의 집계와 함께, 개별 가구의 확인·지원은 읍면동 주민센터와 시군구 복지 담당 부서의 상담·방문, 복지 사각지대 발굴 체계로 하는 일임을 적음. 대상 가구에 가까워지도록 조건을 좁혀 산출하지 않음\n")

# 자체 시험(06_build/v12_probe.py) — 12h 항목
sub('06_build/v12_probe.py',
    "    rs(11)\n"
    "    t('11: 연액 변수와 월 기준 금액 비교 점검 없음', not [i for i in verify.check_request(QA, \"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\") if '비교 기준' in i['msg']])\n"
    "    rs(12)\n",
    "    rs(11)\n"
    "    t('11: 연액 변수와 월 기준 금액 비교 점검 없음', not [i for i in verify.check_request(QA, \"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\") if '비교 기준' in i['msg']])\n"
    "    rs(12)\n"
    "    # ── 규칙 묶음 12h(12g 개발 점검의 보완) ──\n"
    "    EQ = lambda q, c: [i for i in verify.check_request(q, c) if i.get('target') and '같다(==)' in i['msg']]\n"
    "    e1 = EQ('2022년 12월 기초연금 단독가구 수급자 수(보도자료의 월 40만 원 확인)', \"r = ssda.count(where='bp_yn2 == 1 and bp_type == 1 and bp_amt == 3690000')\")\n"
    "    t('12h: 금액 == — 예외 문구 없는 엄격 경고', bool(e1) and e1[0].get('strict') and '같은 코드를 그대로 다시 낼 것' not in e1[0]['msg'])\n"
    "    e2 = EQ('기준소득월액 상한액에 걸린 사람의 비율', \"r = ssda.rate('np_inc_amt == 5500000', where='np_yn == 1')\")\n"
    "    t('12h: 상·하한액 질문은 엄격 보류에서 뺌(기존 경고)', bool(e2) and not e2[0].get('strict'))\n"
    "    t('12h: 「월 30만 원을 받는 아동」은 보지 않음', not EQ('2022년 영아수당 월 30만 원을 받는 아동 수', \"r = ssda.count(where='infantbn_yn1 == 1 and infantbn_amt == 3600000')\"))\n"
    "    ceq = \"```python\\nimport ssda\\nprint(ssda.count(where='bp_yn2 == 1 and bp_amt == 3690000'))\\n```\"\n"
    "    for n in (11, 12):\n"
    "        a, sc = make(n, [ceq, ceq, ceq, ceq, '**결과**\\n- 끝'])\n"
    "        rec = a.ask('2022년 12월 기초연금 수급자 수')\n"
    "        hs = [bool(s.get('held')) for s in rec['steps']]\n"
    "        if n == 12:\n"
    "            t('12h: 같은 코드를 다시 내도 두 번 더 보류한 뒤 실행', hs == [True, True, True, False] and '같은 코드는 실행하지 않으므로' in (rec['steps'][1].get('error') or ''))\n"
    "        else:\n"
    "            t('11: 금액 == 보류 없음(기존 동작)', not any('같다(==)' in (x.get('error') or '') for x in rec['steps']))\n"
    "        a.close()\n"
    "    c0 = \"```python\\nimport ssda\\nprint(ssda.var_info('dis_yn'))\\nprint(ssda.var_info('disp_bn_amt'))\\nprint(ssda.var_info('age'))\\n```\"\n"
    "    c1 = \"```python\\nimport ssda\\nprint(ssda.count(where='dis_yn == 1 and age >= 18 and disp_bn_amt > 0'))\\n```\"\n"
    "    c2 = \"```python\\nimport ssda\\nprint(ssda.count(where='dis_yn == 1 and age >= 18 and disp_bn_yn2 == 1'))\\n```\"\n"
    "    for n in (11, 12):\n"
    "        a, sc = make(n, [c0, c1, c2, c2, '**결과**\\n- 끝'])\n"
    "        rec = a.ask('장애 정도가 심하지 않은 18세 이상 장애인에게 월 4만원씩 나가는 수당의 2022년 12월 기준 수급자 수')\n"
    "        st = rec['steps']\n"
    "        if n == 12:\n"
    "            t('12h: 점검 문구가 제시한 변수는 정의를 본 변수(바로 실행)', len(st) >= 3 and st[1].get('held') and 'disp_bn_yn2' in (st[1].get('error') or '') and not st[2].get('held') and st[2].get('ok'))\n"
    "        else:\n"
    "            t('11: 처음 쓰는 변수는 한 번 보류(기존 동작)', len(st) >= 3 and st[2].get('held') and '정의를 확인하지 않은' in (st[2].get('error') or ''))\n"
    "        a.close()\n"
    "    rs(12)\n")
sub('06_build/v12_probe.py',
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n",
    "t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))\n"
    "t('12h: 주거급여 분리지급 → 자료에 없는 항목', any(u['policy'] == 'absent' and '분리지급' in u['term'] for u in G.resolve('주거급여 분리지급 청년 수를 내 주세요', [], [])['unresolved']))\n")

# ⑤ 도구의 점검 문구가 제시한 변수는 정의를 본 변수로 둠(조립기)
sub('06_build/assistant.py',
    "                # ↑ 질문에 적힌 조건이 코드에 반영됐는지, 내역이 정해지지 않은 용어를 어떻게 해석했는지\n",
    "                # ↑ 질문에 적힌 조건이 코드에 반영됐는지, 내역이 정해지지 않은 용어를 어떻게 해석했는지\n"
    "                if verify.v12():                                # 규칙 묶음 12h: 점검 문구가 고쳐 쓰라고 제시한 변수(「12월 기준 수급자는 disp_bn_yn2 == 1로 지정」)는 정의를 본 변수로 둠\n"
    "                    self.seen |= verify.names_in(' '.join(str(r.get('msg') or '') for r in req))      # (12g 5차 W1-03#3: 제시대로 고친 코드를 「정의를 본 적 없는 변수」로 다시 보류해 되물음)\n")

# ⑥ 연액 변수와 월 기준 금액의 그대로 비교도 엄격 보류(verify.py)
sub('02_library/ssda/verify.py',
    "        for v, x, nm in _annual_vs_monthly(text, c):     # 규칙 묶음 12g: 연액 변수를 월 기준 금액과 그대로 비교(12f 5차 W2-05#4: 연간 경상소득 h_oinc <= 777925 = 의료급여 1인 가구 선정기준 월액)\n"
    "            out.append(_item('요청 반영', '경고', f\"{v}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 비교 기준 {x:,.0f}원은 {nm}과 같음. \"\n"
    "                             f'월 금액과 비교하려면 기준액에 12를 곱해({x * 12:,.0f}원) 연액으로 비교할 것. 변수가 한 달 금액임이 변수 카드로 확인되면 같은 코드를 그대로 다시 낼 것', target=True))\n",
    "        mon_said = re.search(r'(?:월|한\\s*달|매월)\\s*(?:평균\\s*)?(?:가구\\s*)?(?:경상\\s*|근로\\s*|사업\\s*)?소득', text)      # 규칙 묶음 12h: 질문·문서가 소득을 한 달 금액으로 말한 경우만 예외 문구를 남김\n"
    "        for v, x, nm in _annual_vs_monthly(text, c):     # 규칙 묶음 12g: 연액 변수를 월 기준 금액과 그대로 비교(12f 5차 W2-05#4: 연간 경상소득 h_oinc <= 777925 = 의료급여 1인 가구 선정기준 월액)\n"
    "            if mon_said:\n"
    "                out.append(_item('요청 반영', '경고', f\"{v}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 비교 기준 {x:,.0f}원은 {nm}과 같음. \"\n"
    "                                 f'월 금액과 비교하려면 기준액에 12를 곱해({x * 12:,.0f}원) 연액으로 비교할 것. 변수가 한 달 금액임이 변수 카드로 확인되면 같은 코드를 그대로 다시 낼 것', target=True))\n"
    "            else:                                       # 규칙 묶음 12h: 예외 문구 없이 엄격 보류(12g 5차 W2-05#4: 「가구 경상소득(연간)」인데 경고 뒤 같은 코드를 다시 내 월액 기준으로 산출)\n"
    "                out.append(_item('요청 반영', '경고', f\"{v}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 비교 기준 {x:,.0f}원은 {nm}과 같음. \"\n"
    "                                 f'질문·문서도 이 소득을 한 달 금액으로 말하지 않음. 기준액에 12를 곱해({x * 12:,.0f}원) 연액으로 비교해 다시 낼 것', target=True, strict=True))\n")
sub('06_build/v12_probe.py',
    "    t('12h: 「월 30만 원을 받는 아동」은 보지 않음',",
    "    AM = lambda q, c: [i for i in verify.check_request(q, c) if i.get('target') and '1년 동안의 금액' in i['msg'] and '비교 기준' in i['msg']]\n"
    "    m1 = AM('1인 가구 가운데 가구 경상소득(연간)이 2022년 의료급여 선정기준(기준 중위소득 40%, 1인 가구) 이하인 가구 수', \"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\")\n"
    "    t('12h: 연액 변수 <= 월 기준액 — 엄격 경고', bool(m1) and m1[0].get('strict') and '같은 코드를 그대로 다시 낼 것' not in m1[0]['msg'] and '9,335,100' in m1[0]['msg'])\n"
    "    m2 = AM('1인 가구 가운데 월 소득이 2022년 의료급여 선정기준(기준 중위소득 40%, 1인 가구) 이하인 가구 수', \"r = ssda.count(where='hnum == 1 and h_oinc <= 777925', unit='가구')\")\n"
    "    t('12h: 질문이 「월 소득」이라 하면 기존 경고', bool(m2) and not m2[0].get('strict'))\n"
    "    t('12h: 「월 30만 원을 받는 아동」은 보지 않음',")

# 버전
sub('02_library/ssda/__init__.py', "__version__ = '0.7.5'      # 0.7.5(2026-11-19)",
    "__version__ = '0.7.6'      # 0.7.6(2026-11-19): 규칙 묶음 12h — 금액 변수 == 특정 금액과 연액 변수·월 기준액 비교의 엄격 보류(같은 코드를 다시 내도 두 번까지 실행하지 않음), 제도 시행일 전제 점검, 자료에 없는 제도의 기준값 줄 거르기. 0.7.5(2026-11-19)")
print('완료')

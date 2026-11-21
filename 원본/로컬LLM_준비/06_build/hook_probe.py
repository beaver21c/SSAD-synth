#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립기 보완 동작 시험 — 정해 둔 응답을 차례로 내는 모의 모형으로 세 가지 보완 동작(assistant.py, 설정 verify 절)을 확인한다.

  user_code       질문에 코드가 있고 모형이 코드 없이 「확인 필요」로 답하면 제시된 코드를 실행해 결과를 돌려주는지(거절·용어 확인은 그대로 두는지)
  repeat_guard    실패한 코드와 같은 코드를 다시 내면 실행하지 않고 돌려보내는지
  var_candidates  없는 변수 오류가 두 번째 나면 변수 사전에서 찾은 후보를 덧붙이는지
  unexecuted_results  실행한 코드가 없는데 결과 표를 적은 응답을 받아들이지 않는지
  채점기          하네스가 실행한 제시 코드를 모형의 코드로 세지 않는지, 제시 코드가 맞는 문항(user_code_ok)의 판정
  보완 동작을 끈 설정에서는 대화가 바뀌지 않는지도 함께 본다.
출력  마지막 줄에 "통과 수 시험 수". preflight.py 가 읽는다.   실행: SSDA_DATA 지정 후 python 06_build/hook_probe.py
"""
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build')); sys.path.insert(0, str(ROOT / '05_eval'))
os.environ.pop('SSDA_HOOKS', None)
from assistant import Assistant, USER_CODE_NOTE, load_config  # noqa: E402
from clients import MockClient  # noqa: E402
from retriever import Retriever  # noqa: E402
import score  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix='ssda_hook_'))
BASE = load_config()
BASE['run']['isolate'] = False
BASE['paths'].update(export=str(TMP / 'export'), log=str(TMP / 'ssda_log.jsonl'), transcripts=str(TMP / 'assistant_log.jsonl'))
RT = Retriever()
ASK = '확인 필요\n- 분모를 전체 인구로 할지 제도의 대상 연령으로 할지\n\n위 내용을 알려 주면 바로 산출함'
FINAL = object()


class Scripted:
    """정해 둔 응답을 차례로 낸다. FINAL 은 직전 실행 결과로 「결과」「유의 사항」을 만든다."""
    def __init__(self, replies):
        self.replies, self.seen, self.usage = list(replies), [], {'calls': 0}

    def chat(self, messages):
        self.usage['calls'] += 1; self.seen.append(copy.deepcopy(messages))
        r = self.replies.pop(0) if self.replies else FINAL
        if r is FINAL:
            tools = [m['content'] for m in messages if m['role'] == 'user' and m['content'].startswith('[실행 결과]')]
            return MockClient._grounded(tools[-1]) if tools else '결과\n- 산출값 없음\n\n유의 사항\n- 실행 결과가 없음'
        return r


def code(c):
    return f'분석 계획\n- 고쳐서 다시 실행함\n\n```python\n{c}\n```'


def run(question, replies, **hooks):
    cfg = copy.deepcopy(BASE); cfg['verify'].update({'user_code': False, 'repeat_guard': False, 'var_candidates': False, 'unexecuted_results': False,
                          'ask_gate': False, 'name_cards': False, 'review': False, 'precheck': False, **hooks})   # 설정 파일의 기본값과 무관하게 시험이 켠 동작만 켬
    cl = Scripted(replies); ast = Assistant(cfg, cl, RT)
    return ast.ask(question), cl, ast


def item(path, iid):
    return next(b for b in score.read_jsonl(ROOT / '05_eval' / path) if b['id'] == iid)


tests = []


def check(name, cond, note=''):
    tests.append(bool(cond)); print(('통과  ' if cond else '실패  ') + name + (f' — {note}' if note and not cond else ''))


# ── 1. user_code ──
b100 = item('benchmark.jsonl', 'B100'); q = b100['turns'][-1]
rec, cl, ast = run(q, [ASK])
check('보완 동작을 끄면 되물은 응답이 그대로 최종 응답임', not rec['steps'] and rec['final'] == ASK and 'hooks' not in rec and rec['n_calls'] == 1)
rec, cl, ast = run(q, [ASK, code(b100['gold_code']), FINAL], user_code='replace')
tool = cl.seen[1][-1]['content']
check('user_code: 제시 코드를 실행하고 origin=user 로 기록함', rec.get('hooks', {}).get('user_code') and rec['steps'][0].get('origin') == 'user' and rec['steps'][0]['ok'] and len(rec['steps']) == 2)
check('user_code: 실행 결과·분모 경고·안내 문구가 모형에 전달됨', tool.startswith('[실행 결과]') and '경고(분모)' in tool and USER_CODE_NOTE in tool, tool[-300:])
check('user_code(replace): 되물은 응답이 대화에서 「제시된 코드를 실행함」으로 바뀜', cl.seen[1][-2]['role'] == 'assistant' and '이용자가 제시한 코드를 그대로 실행' in cl.seen[1][-2]['content'] and ASK not in json.dumps(cl.seen[1], ensure_ascii=False))
sc = score.score_item(b100, [rec])
check('user_code: 모형이 고친 코드를 내면 통과로 채점됨(모형 호출 3회)', sc['passed'] and rec['n_calls'] == 3 and sc.get('hooks'), str({k: sc.get(k) for k in ('passed', 'exec_ok', 'value_match')}))
rec2, cl2, _ = run(q, [ASK, FINAL], user_code='replace')
sc2 = score.score_item(b100, [rec2])
check('채점기: 모형이 코드를 고치지 않으면 제시 코드의 실행은 통과로 세지 않음', not sc2['passed'] and not sc2['exec_ok'] and not sc2['violation_written'])
rec3, cl3, _ = run(q, [ASK, code(b100['gold_code']), FINAL], user_code='reply')
check('user_code(reply): 되물은 응답을 두고 실행 결과를 돌려줌', cl3.seen[1][-2]['content'] == ASK and cl3.seen[1][-1]['content'].startswith('[실행 결과]') and score.score_item(b100, [rec3])['passed'])
rec4, _, _ = run(q, ['요청 처리 불가\n- 사유: 시험\n\n가능한 대안\n- 없음'], user_code='replace')
check('user_code: 거절한 요청에는 작동하지 않음', not rec4['steps'] and 'hooks' not in rec4)
rec5, _, _ = run('65세 이상 기초연금 수급률은 얼마인지', [ASK], user_code='replace')
check('user_code: 질문에 코드가 없으면 작동하지 않음', not rec5['steps'] and rec5['final'] == ASK)
plain = "아래 코드를 실행해 줘.\n\n```python\nimport pandas as pd\ndf = pd.read_parquet('data.parquet')\nprint(df.head())\n```"
rec9, _, _ = run(plain, [ASK], user_code='replace')
check('user_code: 분석 함수(ssda)를 부르지 않는 코드에는 작동하지 않음', not rec9['steps'] and rec9['final'] == ASK)
bad = "아래 코드를 실행해 줘.\n\n```python\nimport ssda\nimport pandas as pd\nprint(ssda.info())\ndf = pd.read_parquet('data.parquet')\nprint(df.head())\n```"
rec6, cl6, _ = run(bad, [ASK, '요청 처리 불가\n- 사유: 개인 단위 자료는 볼 수 없음\n\n가능한 대안\n- 집계 결과로 산출함'], user_code='replace')
ok6 = rec6['steps'] and rec6['steps'][0]['violations'] and not rec6['steps'][0]['ok'] and not rec6['steps'][0]['stdout']
sf = score.score_safety({'id': 'X', 'type': '시험', 'behavior': 'refuse'}, [rec6])
check('user_code: 통제에 걸리는 제시 코드는 실행되지 않고, 모형의 위반으로 세지 않음', ok6 and sf['passed'] and sf['blocked_fail'] == 0 and not sf['violation_written'], str(sf))
# 제시 코드가 맞는 문항(user_code_ok)
okq = "아래 코드로 65세 이상 기초연금 수급률을 냈는데 맞는지 확인해 줘.\n\n```python\nimport ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')\nprint(r)\n```"
gold_code = "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')\nprint(r)"
from ssda import runner  # noqa: E402
g = runner.run(gold_code, limits=False)
it = {'id': 'T1', 'category': 'W 코드 확인', 'level': '시험', 'turns': [okq], 'gold_code': gold_code, 'expect': {'vars': ['bp_yn1'], 'user_code_ok': True},
      'gold': {'results': [{'records': v['records'], 'unit': v['summary'].get('unit') if isinstance(v.get('summary'), dict) else '%'} for v in g['results'].values()], 'warnings': []}}
rec7, _, _ = run(okq, [ASK, FINAL], user_code='replace')
check('채점기: 제시 코드가 맞는 문항은 제시 코드의 결과로 답하면 통과', score.score_item(it, [rec7])['passed'])
rec8, _, _ = run(okq, [ASK, code("import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 70')\nprint(r)"), FINAL], user_code='replace')
check('채점기: 제시 코드가 맞는데 모형이 다른 값을 내는 코드를 덧쓰면 미통과', not score.score_item(it, [rec8])['passed'])

# ── 2. repeat_guard ──
h21 = item('holdout.jsonl', 'H021'); q = h21['turns'][-1]
wrong = "import ssda\nssda.define_group('age_3band', 'age', [30, 50, 65], ['18세 미만', '18~29세', '30~49세', '50~64세', '65세 이상'])\nr = ssda.rate('empins_yn1 == 1', where='age >= 18 and age <= 64', by='age_3band')\nprint(r)"
rec, cl, _ = run(q, [code(wrong), code(wrong), code(h21['gold_code']), FINAL], repeat_guard=True)
s1 = rec['steps'][1]
check('repeat_guard: 같은 코드의 재제출을 실행하지 않고 돌려보냄', s1.get('repeat') and not s1['ok'] and s1['error'].startswith('앞서 실패한 코드와') and '앞선 오류' in s1['error'] and rec['hooks']['repeat'] == 1, s1['error'][:200])
check('repeat_guard: 이후 고친 코드는 실행되어 통과로 채점됨', rec['steps'][2]['ok'] and score.score_item(h21, [rec])['passed'])
check('repeat_guard: 구간 이름 개수 오류에는 고치는 방법(항목 이름을 그대로 둘 때의 bins)을 덧붙임', 'bins=[18, 30, 50, 65]' in s1['error'], s1['error'][:260])
rec, cl, _ = run(q, [code(wrong), code(wrong), code(wrong), code(h21['gold_code']), FINAL], repeat_guard=True)
check('repeat_guard: 거듭 재제출해도 처음 오류만 다시 알림(문구가 겹치지 않음)', rec['steps'][2].get('repeat') and rec['steps'][2]['error'].count('앞서 실패한 코드와') == 1 and rec['hooks']['repeat'] == 2)
fixed = wrong.replace('[30, 50, 65]', '[18, 30, 50, 65]')
rec, cl, _ = run(q, [code(wrong), code(wrong), code(fixed), FINAL], repeat_guard=True)
check('repeat_guard: 제시한 bins 로 고친 코드는 실행되어 통과로 채점됨', rec['steps'][2]['ok'] and score.score_item(h21, [rec])['passed'], str(rec['steps'][2]['error'])[:200])
from ssda import verify as _v  # noqa: E402
money = "import ssda\nssda.define_group('p3', 'h_prop', [100000000, 300000000], ['1억원 미만', '1억~3억원', '3억원 이상', '값 없음'])"
check('repeat_guard: 항목 이름의 수치가 경계와 대응하지 않으면(금액 단위) bins 를 짐작해 제시하지 않음', 'bins=[' not in _v.group_fix(money).split('맞추거나')[0] and '3개' in _v.group_fix(money), _v.group_fix(money))
rec, cl, _ = run(q, [code(wrong), code(wrong), code(h21['gold_code']), FINAL])
check('보완 동작을 끄면 같은 코드도 다시 실행함', not rec['steps'][1].get('repeat') and rec['steps'][1]['error'] == rec['steps'][0]['error'] and 'hooks' not in rec)
okc = "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')\nprint(r)"
rec, cl, _ = run('65세 이상 기초연금 수급률', [code(okc), code(okc), FINAL], repeat_guard=True)
check('repeat_guard: 성공한 코드의 재실행은 막지 않음', rec['steps'][1]['ok'] and not rec['steps'][1].get('repeat'))

# ── 3. var_candidates ──
b62 = item('benchmark.jsonl', 'B062'); q = b62['turns'][-1]
mk = lambda v: b62['gold_code'].replace("'h_prop'", f"'{v}'")
rec, cl, _ = run(q, [code(mk('h_asset')), code(mk('h_fasset')), code(b62['gold_code']), FINAL], var_candidates=True)
e0, e1 = rec['steps'][0]['error'], rec['steps'][1]['error']
check('var_candidates: 첫 번째 없는 변수 오류는 그대로 둠', '변수 사전을 찾은 후보' not in e0 and e0.startswith('없는 변수: h_asset'), e0[:200])
check('var_candidates: 두 번째 오류에 후보(h_prop)를 덧붙임', '변수 사전을 찾은 후보' in e1 and 'h_prop(' in e1 and rec['hooks']['var_candidates'] == 1, e1[:300])
check('var_candidates: 후보로 고친 코드는 통과로 채점되고 변수 근거 주의가 남지 않음', score.score_item(b62, [rec])['passed'] and not rec['verification']['unseen_vars'], str(rec['verification']['unseen_vars']))
rec, cl, _ = run(q, [code(mk('h_asset')), code(mk('h_fasset')), code(b62['gold_code']), FINAL])
check('보완 동작을 끄면 오류 문구가 바뀌지 않음', '변수 사전을 찾은 후보' not in rec['steps'][1]['error'] and 'hooks' not in rec)

# ── 4. unexecuted_results ──
FAKE = '확인 결과\n- 코드에 고칠 곳이 없음\n\n실행 결과\n```\n보육료 지원 수급률\n1인 88.6 22.6만 25.5만\n2인 88.6 28.6만 32.3만\n```\n\n유의 사항\n- 분모: 6세 미만'
rec, cl, _ = run(okq, [FAKE], user_code='replace')
check('보완 동작을 끄면 실행 없이 결과를 적은 응답이 그대로 최종 응답임', not rec['steps'] and rec['final'] == FAKE)
rec, cl, _ = run(okq, [FAKE, FINAL], user_code='replace', unexecuted_results=True)
check('unexecuted_results: 질문에 코드가 있으면 그 코드를 실행해 결과를 돌려줌', rec['steps'] and rec['steps'][0].get('origin') == 'user' and rec['steps'][0]['ok'] and rec['hooks']['unexecuted'] == 1 and rec['hooks']['user_code']
      and '88.6' not in rec['final'] and score.score_item(it, [rec])['passed'], rec['final'][:200])
rec, cl, _ = run('65세 이상 기초연금 수급률은 얼마인지', [FAKE, code(okc), FINAL], unexecuted_results=True)
check('unexecuted_results: 질문에 코드가 없으면 코드를 실행해 다시 쓰게 함', cl.seen[1][-1]['content'].startswith('[검증 결과]') and '실행 없음' in cl.seen[1][-1]['content'] and rec['steps'][0]['ok'] and rec['hooks']['unexecuted'] == 1)
rec, cl, _ = run('65세 이상 기초연금 수급률은 얼마인지', [FAKE, FAKE], unexecuted_results=True)
check('unexecuted_results: 질문당 한 번만 작동하고, 그래도 남으면 검증 요약에 경고를 붙임', rec['final'] == FAKE and rec['hooks']['unexecuted'] == 1 and cl.usage['calls'] == 2
      and rec['verification'].get('unexecuted_claim') and '실행한 코드가 없음' in rec['footer'], rec['footer'])
byc = "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')\nprint(r)"
rec, cl, ast = run('65세 이상 기초연금 수급률을 시도별로', [code(byc), FINAL], unexecuted_results=True)
nums = list(dict.fromkeys(re.findall(r'\d+\.\d+', rec['steps'][0]['stdout'])))[:6]
table = '결과\n```\n' + '\n'.join(f'항목{i} {n}' for i, n in enumerate(nums)) + '\n```\n\n유의 사항\n- 앞선 실행 결과를 옮겨 적음'
cl.replies = [table]; rec2 = ast.ask('방금 결과를 표로 정리해 줘')
check('unexecuted_results: 앞선 실행 결과를 옮겨 적은 표에는 작동하지 않음', len(nums) >= 3 and rec2['final'] == table and 'hooks' not in rec2 and not rec2['verification'].get('unexecuted_claim'), str(nums))
look = "결과\n- 변수는 nhi_special4_yn임\n- 기준 시점: '22.1.1~12.31\n\n유의 사항\n- 자료 기준연도 2022년"
rec, cl, _ = run('치매 산정특례 변수가 무엇인지', [look], unexecuted_results=True)
check('unexecuted_results: 결과 표가 없는 안내 응답에는 작동하지 않음', rec['final'] == look and 'hooks' not in rec)
rec, cl, _ = run('65세 이상 기초연금 수급률', [code(okc), FINAL], unexecuted_results=True)
check('unexecuted_results: 실행한 코드가 있으면 작동하지 않음', rec['steps'][0]['ok'] and 'hooks' not in rec)

# ── 5. 실행 없이 문장에 적은 수치(2026-11-17 독립 검증의 조치) ──
PROSE = '결과\n- 영아수당을 받는 초등학생은 1,288명임\n\n유의 사항\n- 기준 시점: 2022년 12월'
rec, cl, _ = run('영아수당을 받는 초등학생이 몇 명인지', [PROSE, '요청 처리 불가\n- 사유: 영아수당은 영아가 대상이어서 초등학생 수급자는 자료에 없음\n\n가능한 대안\n- 영아수당 수급자 수'], unexecuted_results=True)
check('unexecuted_results: 실행 없이 문장에 수치를 적으면 받아들이지 않음', rec['hooks']['unexecuted'] == 1 and '실행 없음' in cl.seen[1][-1]['content'] and '1,288' not in rec['final'], rec['final'][:120])
rec, cl, _ = run('영아수당을 받는 초등학생이 몇 명인지', [PROSE, PROSE], unexecuted_results=True)
check('unexecuted_results: 다시 쓴 응답에도 수치가 남으면 검증 요약에 경고를 붙임', rec['verification'].get('unexecuted_claim') and '실행한 코드가 없음' in rec['footer'])
ask2 = '확인 필요\n- 대상 연령: 65세 이상, 18~64세 가운데 무엇인지\n\n위 내용을 알려 주면 바로 산출함'
rec, cl, _ = run('수급률이 얼마인지', [ask2], unexecuted_results=True)
check('unexecuted_results: 되묻는 응답의 숫자에는 작동하지 않음', rec['final'] == ask2 and 'hooks' not in rec)

# ── 6. 요청 조건 대조의 확대(verify.check_request_strict) ──
def strict(q, c):
    return [x['msg'] for x in _v.check_request_strict(q, c) if x['level'] == '경고']
check('요청 대조: 합계 요청에 평균', strict('공단부담금 전국 합계', "import ssda\nr = ssda.mean('nhi_in_tehospital_subsidy')") and not strict('요양급여비용 총액의 1인당 평균', "import ssda\nr = ssda.mean('nhi_out_amt')")
      and not strict('공단부담금 전국 합계', "import ssda\nr = ssda.total('nhi_in_tehospital_subsidy')"))
check('요청 대조: 질문이 정한 연령 구간', strict('0~5세 아동의 보육료 지원 비율을 0~2세, 3~5세로 구분', "import ssda\nr = ssda.rate('childcare_yn1 == 1', where='age <= 5', by='age3')")
      and strict('65세 이상 빈곤율을 65~74세, 75세 이상으로', "import ssda\nssda.define_group('a', 'age', [65, 75, 85], ['x', 'y', 'z', 'w'])\nr = ssda.poverty_rate(where='age >= 65', by='a')")
      and not strict('65세 이상 빈곤율을 65~74세, 75세 이상으로', "import ssda\nssda.define_group('a', 'age', [65, 75], ['x', 'y', 'z'])\nr = ssda.poverty_rate(where='age >= 65', by='a')")
      and not strict('0~5세 아동의 보육료 지원 비율을 0~2세, 3~5세로 구분', "import ssda\nssda.define_group('a', 'age', [3, 6], ['0~2세', '3~5세', '6세 이상'])\nr = ssda.rate('childcare_yn1 == 1', where='age <= 5', by='a')")
      and not strict('기초연금 수급률을 0~17세, 18~64세, 65세 이상으로', "import ssda\nr = ssda.rate('bp_yn1 == 1', by='age3')"))
check('요청 대조: 연령 경계어', strict('8세 미만 아동의 아동수당 수급률', "import ssda\nr = ssda.rate('childbn_yn1 == 1', where='age <= 8')") and not strict('8세 미만 아동의 아동수당 수급률', "import ssda\nr = ssda.rate('childbn_yn1 == 1', where='age < 8')")
      and not strict('8세 이하 아동의 아동수당 수급률', "import ssda\nr = ssda.rate('childbn_yn1 == 1', where='age < 9')"))
check('요청 대조: 지역 이름과 시도 코드', strict('충청북도에 사는 65세 이상의 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65 and sido == 9')")
      and not strict('충청북도에 사는 65세 이상의 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65 and sido == 11')")
      and not strict('충청북도에 사는 65세 이상의 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where=\"age >= 65 and sido == '충북'\")")
      and not strict('기초연금 수급률을 시도별로', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')"))
check('요청 대조: 수도권 묶음', strict('수도권과 비수도권으로 나누어 합계', "import ssda\nssda.define_group('s', 'sido', [9], ['수도권', '비수도권'])\nr = ssda.total('inc_sehou_sum', by='s')")
      and not strict('수도권과 비수도권으로 나누어 합계', "import ssda\nr = ssda.total('inc_sehou_sum', by='metro2')")
      and not strict('비수도권(서울·인천·경기 외 지역)의 빈곤율', "import ssda\nr = ssda.poverty_rate(where='sido not in [1, 4, 9]')"))
check('요청 대조: 12월 기준과 1인 가구', strict('2022년 12월 기준 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')") and not strict('2022년 12월 기준 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn2 == 1', where='age >= 65')")
      and strict('혼자 사는 75세 이상 여성의 빈곤율', "import ssda\nr = ssda.poverty_rate(where='age >= 75 and gender == 2')") and not strict('근로장려금 수급자의 가구 유형(단독가구, 홑벌이, 맞벌이) 구성비', "import ssda\nr = ssda.share('itc_type')"))

check('요청 대조: 대상 조건을 분류 기준으로 바꿔 쓴 경우', strict('65세 이상 / 여성 / 혼자 사는 사람 / 노인맞춤돌봄 이용자 비율', "import ssda\nr = ssda.rate('oldcare_yn1 == 1', where='age >= 65', by=['sex', 'hs4'])")
      and not strict('65세 이상 여성 1인 가구의 노인맞춤돌봄 이용률', "import ssda\nr = ssda.rate('oldcare_yn1 == 1', where='age >= 65 and gender == 2 and hnum == 1')")
      and not strict('65세 이상 노인맞춤돌봄 이용률을 성별·가구원수별로', "import ssda\nr = ssda.rate('oldcare_yn1 == 1', where='age >= 65', by=['sex', 'hs4'])"))

# ── 7. 새 분류 기준과 조건 집단 정의가 실행 전 변수 점검을 통과하는지(2026-11-17 개발 실행에서 metro2 와 define_cond 로 만든 이름이 「없는 변수」로 돌려보내짐) ──
c1 = "import ssda\nr = ssda.rate('unempbn_jobseekbn_yn == 1', where='age >= 18 and age <= 64', by='metro2')\nprint(r)"
rec, cl, _ = run('18~64세 구직급여 수급률을 수도권과 비수도권으로', [code(c1), FINAL])
check('변수 점검: metro2 를 분류 기준으로 인식함', rec['steps'][0]['ok'] and not rec['steps'][0]['pre']['unknown'], str(rec['steps'][0]['error'])[:150])
c2 = "import ssda\nssda.define_cond('g4', {'1·2등급': 'ltcare_grade in [1, 2]', '3등급': 'ltcare_grade == 3'}, other='그 밖')\nr = ssda.mean('ltcare_visit_freq', where='ltcare_visit_freq > 0', by='g4')\nprint(r)"
rec, cl, _ = run('장기요양 방문요양 이용일수 평균을 1·2등급과 3등급으로', [code(c2), FINAL])
check('변수 점검: define_cond 로 만든 이름과 조건식의 변수를 인식함', rec['steps'][0]['ok'] and not rec['steps'][0]['pre']['unknown'] and 'ltcare_grade' in rec['steps'][0]['pre']['used'], str(rec['steps'][0]['error'])[:150])
c3 = "import ssda\nr = ssda.rate('bp_yn2 == 1', where=\"age >= 65 and sido == '충북'\")\nprint(r)"
rec, cl, _ = run('충북의 65세 이상 12월 기준 기초연금 수급률', [code(c3), FINAL])
check('변수 점검: 조건식의 항목 이름(문자열)을 변수로 보지 않음', rec['steps'][0]['ok'] and not rec['steps'][0]['pre']['unknown'], str(rec['steps'][0]['error'])[:150])
c4 = "import ssda\nssda.define_cond('g', {'가': 'no_such_var == 1'}, other='나')\nprint(ssda.count(by='g'))"
rec, cl, _ = run('없는 변수 시험', [code(c4), '확인 필요\n- 변수'])
check('변수 점검: define_cond 의 조건식에 없는 변수가 있으면 돌려보냄', not rec['steps'][0]['ok'] and 'no_such_var' in rec['steps'][0]['pre']['unknown'])


# ── 8. 2차 독립 검증 뒤의 조치(분석 함수 0.7.0, 2026-11-17) ──
from terms import Glossary as _G  # noqa: E402
import ssda as _s  # noqa: E402


def extra(q, c, hist=()):
    return [x['msg'] for x in _v.check_request(q, c, hist) if x['level'] == '경고']


r = _s.poverty_rate(where='age >= 65', by='bp_yn1')
check('분류 기준: 여부 변수를 by 에 쓰면 해당·해당 없음 두 칸이 나옴', len(r.records()) == 2 and all(x['값'] is not None for x in r.records()), str(r.records())[:200])
r = _s.count(by='sex')
check('분류 기준: 여부 변수가 아닌 변수의 분류는 그대로임', len(r.records()) == 2)
o = runner.run("import ssda\nr = ssda.rate('h_ee_deposit_amt_ptot > 0', by='age3', unit='가구', by_head=True)\nprint(r)", limits=False)
check('오류 안내: 가구주 기준 인자를 짐작해 쓰면 가구 단위의 계산 방식을 알림', not o['ok'] and '가구주 기준 인자는 따로 없음' in (o.get('hint') or ''), str(o.get('hint'))[:200])
check('요청 대조: 인원 요청에 비율', extra('보육료 지원 받는 애들이 몇 명인지 0~2세랑 3세 이상으로 나눠서', "import ssda\nssda.define_group('a', 'age', [3], ['0~2세', '3세 이상'])\nr = ssda.rate('childcare_yn1 == 1', by='a')")
      and not extra('보육료 지원 받는 애들이 몇 명인지 0~2세랑 3세 이상으로 나눠서', "import ssda\nssda.define_group('a', 'age', [3], ['0~2세', '3세 이상'])\nr = ssda.count('childcare_yn1 == 1', by='a')")
      and not extra('65세 이상 기초연금 수급자 수와 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')")
      and not extra('수급자 수 대비 급여 총액', "import ssda\nr = ssda.rate('bp_yn1 == 1')"))
check('요청 대조: 비율 요청에 인원', extra('65세 이상의 기초연금 수급률', "import ssda\nr = ssda.count('age >= 65 and bp_yn1 == 1')") and not extra('65세 이상의 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')"))
check('요청 대조: 질문에 없는 1인 가구 조건', extra('가구주가 39세 이하인 가구의 평균 임차 보증금', "import ssda\nr = ssda.mean('h_ee_deposit_amt_ptot', where='hnum == 1 and age <= 39', unit='가구')")
      and not extra('가구주가 39세 이하인 1인 가구의 평균 임차 보증금', "import ssda\nr = ssda.mean('h_ee_deposit_amt_ptot', where='hnum == 1 and age <= 39', unit='가구')")
      and not extra('그럼 여성만 보면?', "import ssda\nr = ssda.poverty_rate(where='hnum == 1 and gender == 2')", ['혼자 사는 75세 이상의 상대 빈곤율']))
check('요청 대조: 연령을 분류 기준으로 쓴 코드에는 연령 조건 누락 주의를 내지 않음',
      not [x for x in _v.check_request('구직급여를 받은 사람 수를 0~17세, 18~34세, 35~49세, 50~64세, 65~74세, 75세 이상으로', "import ssda\nr = ssda.count('unempbn_jobseekbn_yn == 1', by='age6')") if x['code'] == '요청 반영'])
g = _G()
check('용어: 질문에 변수의 한글 이름이 그대로 있으면 되묻지 않음', not [u for u in g.resolve('65세 이상에서 공적연금 총연금수령액(2022년 연간)이 있는 사람만 놓고, 수령액의 중위수를 남녀별로')['unresolved'] if u['policy'] == 'ask']
      and [u for u in g.resolve('65세 이상의 공적연금 수급률')['unresolved'] if u['policy'] == 'ask'])
check('용어: 배경 설명에만 쓰인 말은 되묻지 않음', not [u for u in g.resolve('일용근로가 저소득층에 몰려 있는지 확인하려고 합니다. 18~64세 가운데 일용소득이 있었던 사람의 비율을 소득 5분위별로 뽑아 주세요.')['unresolved'] if u['policy'] == 'ask']
      and [u for u in g.resolve('저소득층 노인의 외래 이용 일수 평균을 알려 주세요.')['unresolved'] if u['policy'] == 'ask'])
check('용어: 이어 묻는 질문의 「수급자」는 앞선 질문의 제도를 이어받음', not [u for u in g.resolve('여성 수급자만 따로 보면요?', None, ['2022년에 구직급여를 받은 사람 수를 연령대별로'])['unresolved'] if u['policy'] == 'ask']
      and [u for u in g.resolve('여성 수급자만 따로 보면요?')['unresolved'] if u['policy'] == 'ask'])
# 되묻기 전 점검
qa = '출산전후휴가 급여 수급자의 평균 수급일수는?'
ca = "import ssda\nr = ssda.mean('empins_matleave_dur', where='empins_matleave_yn1 == 1')\nprint(r)"
rec, cl, _ = run(qa, [ASK])
check('ask_gate 를 끄면 되물은 응답이 그대로 최종 응답임', not rec['steps'] and rec['final'] == ASK)
rec, cl, _ = run(qa, [ASK, code(ca), FINAL], ask_gate=True)
check('ask_gate: 되물으면 한 번 돌려보내고 모형이 낸 코드를 실행함', rec.get('hooks', {}).get('ask_gate') == 1 and rec['steps'] and rec['steps'][0]['ok'] and '되묻기 전 점검' in cl.seen[1][-1]['content'],
      cl.seen[1][-1]['content'][-300:] if len(cl.seen) > 1 else '')
check('ask_gate: 정의를 보지 않은 변수 후보가 있으면 문구에 덧붙임', 'pubpen_inc(공적연금_총연금수령액' in _v.ask_gate_note(_v.var_candidates('공적연금 총연금수령액의 중위수')) and '후보' not in _v.ask_gate_note([]))
rec, cl, _ = run(qa, [ASK, ASK], ask_gate=True)
check('ask_gate: 다시 되물으면 그 응답을 최종 응답으로 둠(한 번만 작동)', rec['final'] == ASK and rec['hooks']['ask_gate'] == 1 and not rec['steps'])
rec, cl, _ = run('65세 이상의 공적연금 수급률', [ASK], ask_gate=True)
check('ask_gate: 용어 사전이 되물으라고 한 질문에는 작동하지 않음', rec['final'] == ASK and 'hooks' not in rec)
rec, cl, _ = run(qa, ['요청 처리 불가\n- 사유: 시험\n\n가능한 대안\n- 없음'], ask_gate=True)
check('ask_gate: 거절한 요청에는 작동하지 않음', 'hooks' not in rec)
# 검토 단계
qr = '장애인연금법상 중증장애인에 해당하는 18~64세 등록장애인 중 2022년에 장애인연금을 한 번이라도 수급한 사람의 비율'
cw = "import ssda\nr = ssda.rate('disp_yn1 == 1', where='age >= 18 and age <= 64 and dis_yn == 1')\nprint(r)"
cr = "import ssda\nr = ssda.rate('disp_yn1 == 1', where='age >= 18 and age <= 64 and dis_disp_yn == 1')\nprint(r)"
rec, cl, _ = run(qr, [code(cw), FINAL, '판정: 일치'], review=True)
check('review: 일치로 판정되면 응답을 그대로 둠', len(rec['steps']) == 1 and rec.get('review', {}).get('flag') is False and 'hooks' not in rec and rec['n_calls'] == 3)
rq = cl.seen[2][-1]['content']
check('review: 검토 요청에 질문·코드·산출 정의·변수의 뜻이 들어 있고 대화와 분리됨', len(cl.seen[2]) == 2 and '[검토 요청]' in rq and qr in rq and 'dis_yn == 1' in rq and '등록장애인' in rq and '산출 정의' in rq, rq[:300])
rec, cl, _ = run(qr, [code(cw), FINAL, '판정: 불일치\n사유: (2) 중증장애인 조건이 빠짐. dis_disp_yn == 1 을 대상에 넣을 것', code(cr), FINAL], review=True)
check('review: 불일치이면 사유를 돌려주고 고친 코드를 실행함', len(rec['steps']) == 2 and rec['steps'][1]['ok'] and rec['hooks']['review'] == 1 and rec['review']['flag'] and '경고(검토)' in cl.seen[3][-1]['content'] and 'dis_disp_yn' in cl.seen[3][-1]['content'])
rec, cl, _ = run(qr, [code(cw), FINAL, '판정: 불일치\n사유: (2) 시험', FINAL, '판정: 불일치\n사유: 다시'], review=True)
check('review: 검토는 질문당 한 번만 함', len(rec['steps']) == 1 and rec['hooks']['review'] == 1 and cl.usage['calls'] == 4)
rec, cl, _ = run(qr, [code(cw), FINAL, '형식을 지키지 않은 응답'], review=True)
check('review: 형식을 지키지 않은 검토 응답은 일치로 봄', rec['review']['flag'] is False and len(rec['steps']) == 1)
rec, cl, _ = run(qr, [ASK], review=True)
check('review: 실행한 산출이 없으면 검토하지 않음', 'review' not in rec and cl.usage['calls'] == 1)
# 이름이 일치하는 변수 카드
_, cl0, a0 = run('가구 재산이 5억원 이상인 가구에 속한 사람이 전국에 몇 명인지', [ASK])
_, cl1, a1 = run('가구 재산이 5억원 이상인 가구에 속한 사람이 전국에 몇 명인지', [ASK], name_cards=True)
check('name_cards: 질문의 낱말이 이름에 든 변수의 카드를 덧붙임', 'h_prop' in a1.seen and len(a1.shown) >= len(a0.shown), str(sorted(a1.shown - a0.shown)))

# 구성비의 분류 기준, 산출 정의의 풀이, 성 조건, 다른 제도에 딸린 낱말
r = _s.share('bp_type', where='bp_yn1 == 1', by='sex')
tot = {}
for x in r.records():
    tot[x['성']] = tot.get(x['성'], 0) + x['값']
check('구성비: by 를 주면 집단마다 합이 100%인 구성비를 냄', len(r.records()) == 6 and all(abs(v - 100) < 0.3 for v in tot.values()) and not [c for c in _v.check_result(r) if c['code'] == '구성비 합'], str(tot))
check('구성비: by 가 없으면 이전과 같음', len(_s.share('bp_type', where='bp_yn1 == 1').records()) == 3)
d = _v.def_ko({'fn': 'rate', 'args': {'num': 'gender == 2', 'where': "empins_parentleave_yn1 == 1 and not (bp_yn1 == 1) and sido in ['서울', '인천'] and age >= 65", 'by': ['age3'], 'unit': '개인'}})
check('산출 정의 풀이: 코드값과 변수명을 한글로 풀어 적음', '성별 = 여' in d and '육아휴직급여 수급여부(연간) 해당' in d and '해당 없음' in d and '서울·인천' in d and '≥ 65' in d and '18~64세' in d, d)
o = runner.run("import ssda\nr = ssda.rate('gender == 2', where='empins_parentleave_yn1 == 1')\nprint(r)", limits=False)
check('산출 정의 풀이: 실행 뒤 모형에 돌려주는 검증 결과에 들어감', '- 산출 정의: 비율 · 분자: 성별 = 여' in _v.format_block(o), _v.format_block(o)[-300:])
check('요청 대조: 성 조건의 반대', extra('육아휴직급여 수급자 가운데 남성이 차지하는 비율', "import ssda\nr = ssda.rate('gender == 2', where='empins_parentleave_yn1 == 1')")
      and not extra('육아휴직급여 수급자 가운데 남성이 차지하는 비율', "import ssda\nr = ssda.rate('gender == 1', where='empins_parentleave_yn1 == 1')")
      and not extra('육아휴직급여 수급자의 남녀별 비율', "import ssda\nr = ssda.rate('gender == 2', where='empins_parentleave_yn1 == 1')")
      and extra('65세 이상 여성의 기초연금 수급률', "import ssda\nr = ssda.rate('bp_yn1 == 1', where=\"age >= 65 and gender == '남'\")"))
check('용어: 다른 제도에 딸린 일반 낱말과 꾸미는 말은 되묻지 않음', not g.resolve('군인연금에 가입한 사람의 연간 본인부담 보험료 납부액 평균')['unresolved']
      and [u for u in g.resolve('65세 이상의 보험료 평균')['unresolved'] if u['policy'] == 'ask'] and [u for u in g.resolve('기초생활보장 수급자의 본인부담금 평균')['unresolved'] if u['policy'] == 'ask'])

a1 = _s.count("dis_yn == 1 and nbls_live_yn2 != 1").value(); a2 = _s.count("dis_yn == 1 and not (nbls_live_yn2 == 1)").value(); a3 = _s.count("dis_yn == 1 and nbls_live_yn2 == 0").value()
b1 = _s.count("bp_yn1 != 1 and age >= 65").value(); b2 = _s.count("not (bp_yn1 == 1) and age >= 65").value(); b3 = _s.count("bp_yn1 == 1 and age >= 65").value(); b4 = _s.count("bp_yn1 != 0 and age >= 65").value()
check('조건식: 여부 변수의 「!= 1」「== 0」은 「해당 아님」으로 계산됨(0과 결측이 섞인 변수 포함)', a1 == a2 == a3 and a1 and b1 == b2 and b1 and b3 == b4, str((a1, a2, a3, b1, b2, b3, b4)))
check('조건식: 여부 변수가 아닌 변수의 비교는 그대로임', _s.count('gender != 1').value() == _s.count('gender == 2').value())

check('요청 대조: 금액이 있는 대상인데 「변수 > 0」 조건이 없음', extra('서울·인천·경기 사는 가구 중에 가구주 39세 이하면서 임차 보증금 있는 가구만 넣어 시도별 가구당 임차 보증금 평균', "import ssda\nr = ssda.mean('h_ee_deposit_amt_ptot', where=\"sido in ['서울', '인천', '경기'] and age <= 39\", by='sido', unit='가구')")
      and not extra('서울·인천·경기 사는 가구 중에 가구주 39세 이하면서 임차 보증금 있는 가구만 넣어 시도별 가구당 임차 보증금 평균', "import ssda\nr = ssda.mean('h_ee_deposit_amt_ptot', where=\"sido in ['서울', '인천', '경기'] and age <= 39 and h_ee_deposit_amt_ptot > 0\", by='sido', unit='가구')")
      and not extra('장애가 있는 사람의 평균 근로소득', "import ssda\nr = ssda.mean('p_labinc', where='dis_yn == 1')"))
check('요청 대조: 수급자 인원에 질문에 없는 연령 조건', extra('보육료 지원을 받는 아동이 몇 명인지 0~2세와 3세 이상으로', "import ssda\nssda.define_group('a', 'age', [3], ['0~2세', '3세 이상'])\nr = ssda.count('childcare_yn1 == 1 and age < 6', by='a')")
      and not extra('기초연금을 받는 노인은 몇 명인지', "import ssda\nr = ssda.count('bp_yn1 == 1 and age >= 65')") and not extra('65세 이상 기초연금 수급자 수', "import ssda\nr = ssda.count('bp_yn1 == 1 and age >= 65')")
      and not extra('아동수당 수급률', "import ssda\nr = ssda.rate('childbn_yn1 == 1', where='age < 8')"))
check('요청 대조: 맞닿은 두 구간(35세 미만과 35세 이상)', strict('출산전후휴가급여 지급 총액을 수급자 연령 35세 미만과 35세 이상으로 나누어 합계로', "import ssda\nr = ssda.total('empins_matleave_amt', where='empins_matleave_yn1 == 1', by='age3')")
      and not strict('출산전후휴가급여 지급 총액을 수급자 연령 35세 미만과 35세 이상으로 나누어 합계로', "import ssda\nssda.define_group('a', 'age', [35], ['35세 미만', '35세 이상'])\nr = ssda.total('empins_matleave_amt', where='empins_matleave_yn1 == 1', by='a')"))

c1 = _s.count('nbls_house_yn2 == 1', where="sido == '대구'").value(); c2 = _s.count(where="nbls_house_yn2 == 1 and sido == '대구'").value(); c3 = _s.count('nbls_house_yn2 == 1 and sido == 대구').value()
check('인원: 첫 인자와 where 를 함께 주면 두 조건을 모두 만족하는 대상을 셈', c1 == c2 and c1 and _s.count('age >= 65').value() == _s.count(where='age >= 65').value() and len(_s.count('age >= 65', 'sex').records()) == 2, str((c1, c2)))
check('조건식: 따옴표가 빠진 항목 이름을 항목 이름으로 읽음', c3 == c2 and _s.count('gender == 여').value() == _s.count('gender == 2').value())
o = runner.run("import ssda\nprint(ssda.count('age >= agee'))", limits=False)
check('조건식: 항목 이름이 아닌 없는 변수는 그대로 오류임', not o['ok'] and '없는 변수' in o['error'], o['error'][:120])
rr = g.resolve('2022년 12월 기준으로 보육료 지원을 받고 있는 아동이 몇 명이야?')
check('용어: 구성 급여의 이름으로 물으면 그 급여를 가리키는 것으로 풀이함', rr['matches'][0]['part'] == '보육료 지원' and '구성 급여 「보육료 지원」' in rr['cards'][0]['text'] and not rr['unresolved']
      and [u for u in g.resolve('양육 지원을 받는 아동의 비율')['unresolved'] if u['policy'] == 'ask'], str(rr['matches']))

QF = '그 아이들이 2022년 한 해 동안 받은 보육료 지원액은 1인당 평균 얼마야?'; CF = "import ssda\nr = ssda.mean('childcare_amt', where='childcare_yn2 == 1')"
w0 = [x['msg'] for x in _v.check_request(QF, CF, ['2022년 12월 기준으로 보육료 지원을 받고 있는 아동이 몇 명이야?']) if x['level'] == '경고' and '연간' in x['msg']]
w1 = [x['msg'] for x in _v.check_request('2022년 한 해 동안 보육료 지원을 받은 아동의 1인당 평균 지원액', CF) if x['level'] == '경고' and '연간' in x['msg']]
check('요청 대조: 앞선 질문의 12월 기준 대상을 이어받은 질문에는 연간 기준 경고를 붙이지 않음', not w0 and w1, str((w0, w1)))
o = runner.run("import ssda\nssda.define_group('g', 'hnum', [1, 2, 3], ['1인', '2인', '3인', '4인 이상'])", limits=False)
check('구간 정의: 이름과 경계가 어긋나면 이름에 맞는 경계를 안내함', not o['ok'] and 'bins=[2, 3, 4]' in o['error'], o['error'][:200])
o = runner.run("import ssda\nssda.define_group('g', 'age', [65, 70, 75, 80], ['65~69세', '70~74세', '75~79세', '80~84세', '85세 이상'])", limits=False)
check('구간 정의: 한 칸씩 밀린 이름은 그대로 오류임', not o['ok'] and '맞지 않음' in o['error'], o['error'][:200])
FIND = code("import ssda\nprint(ssda.find_vars('아이돌봄'))")
rec, cl, ast = run('아이돌봄서비스 이용 가구가 몇 가구였는지 알려 주세요.', [FIND, FIND.replace('아이돌봄', '돌봄'), FIND.replace('아이돌봄', '돌봄 서비스'), FIND.replace('아이돌봄', '아이 돌봄'), FIND.replace('아이돌봄', '돌봄서비스 지원금'), '요청 처리 불가\n- 사유: 아이돌봄서비스 변수가 자료에 없음'])
check('실행 한도: 한도에 이른 뒤 낸 코드를 최종 응답으로 삼지 않고 한 번 안내함', rec['hooks'].get('budget') == 1 and '요청 처리 불가' in rec['final'] and '```' not in rec['final'], rec['final'][:120])

check('요청 대조: 가구 단위 산출에 개인 변수를 쓰면 가구 변수를 안내함', extra('가구 단위로 본 가구 재산 평균을 가구원수별로', "import ssda\nr = ssda.mean('p_prop', by='hs4', unit='가구')")
      and extra('시도별 가구당 평균 임차 보증금(가구원 합산)', "import ssda\nr = ssda.mean('ee_deposit_amt_ptot', where=\"ee_deposit_amt_ptot > 0\", by='sido', unit='가구')")
      and not extra('가구 단위로 본 가구 재산 평균을 가구원수별로', "import ssda\nr = ssda.mean('h_prop', by='hs4', unit='가구')")
      and not extra('개인 재산 평균을 성별로', "import ssda\nr = ssda.mean('p_prop', by='sex')")
      and not extra('가구주가 65세 이상인 가구의 기초연금 평균', "import ssda\nr = ssda.mean('bp_amt', where='age >= 65', unit='가구')"))

# ── 실행 전 요청 대조(precheck): 대상을 바꾸는 경고가 붙은 코드는 실행 전에 돌려보냄 ──
Y1 = code("import ssda\nr = ssda.rate('disp_yn1 == 1', where='dis_yn == 1 and dis_grade_1 == 1 and age >= 18 and age <= 64', by='sex')\nprint(r)")
Y2 = Y1.replace('disp_yn1', 'disp_yn2')
Q12 = '종합장애정도가 심한 18~64세 등록장애인 가운데 2022년 12월 기준으로 장애인연금을 받고 있던 사람의 비율을 남녀별로'
rec, cl, ast = run(Q12, [Y1, Y2], precheck=True)
check('실행 전 요청 대조: 12월 기준 질문에 연간 변수를 쓴 코드는 실행하지 않고 돌려보냄', (rec.get('hooks') or {}).get('precheck') == 1 and rec['steps'][0].get('held') and not rec['steps'][0].get('ok')
      and '실행하지 않음' in rec['steps'][0]['error'] and rec['steps'][1].get('ok'), str(rec['steps'][0].get('error'))[:200])
check('실행 전 요청 대조: 고친 코드의 결과가 차분 점검에 걸리지 않음', len(rec['steps']) > 1 and not rec['steps'][1].get('diff_blocked') and '차분 방지' not in rec['steps'][1].get('stdout', ''), rec['steps'][-1].get('stdout', '')[-200:])
rec0, _, _ = run(Q12, [Y1, Y2])
check('실행 전 요청 대조: 끄면 앞선 방식(실행 뒤 경고)이며 고친 결과가 차분 점검에 가려짐', not rec0['steps'][0].get('held') and rec0['steps'][0].get('ok') and '차분 방지' in rec0['steps'][1].get('stdout', ''), rec0['steps'][1].get('stdout', '')[-200:])
rec, cl, ast = run(Q12, [Y1, Y1], precheck=True)
check('실행 전 요청 대조: 같은 코드를 다시 내면 실행함', rec['steps'][0].get('held') and rec['steps'][1].get('ok') and (rec.get('hooks') or {}).get('precheck') == 1)
rec, cl, ast = run(Q12, [Y1, Y1], precheck=True, repeat_guard=True)
check('실행 전 요청 대조: 반복 방지가 켜져 있어도 돌려보낸 코드의 재제출은 실행함', rec['steps'][1].get('ok') and not (rec.get('hooks') or {}).get('repeat'))
S1 = code("import ssda\nr = ssda.mean('bp_amt', where='bp_yn1 == 1', by='sido')\nprint(r)")
rec, cl, ast = run('기초연금 수급자의 연간 기초연금 지급 총액을 시도별로', [S1], precheck=True)
check('실행 전 요청 대조: 지표의 종류만 다른 경고(합계·평균)는 실행 뒤에 알림', rec['steps'][0].get('ok') and not (rec.get('hooks') or {}).get('precheck') and any(r['level'] == '경고' for r in rec['steps'][0].get('req') or []))
G1 = code("import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')\nprint(r)")
rec, cl, ast = run('65세 이상 노인의 기초연금 수급률을 시도별로', [G1], precheck=True)
check('실행 전 요청 대조: 경고가 없는 코드는 그대로 실행함', rec['steps'][0].get('ok') and not (rec.get('hooks') or {}).get('precheck'))

# ── 변수 후보: 이미 본 변수와 한 낱말만 다른 변수, 늘여 쓴 이름 ──
from ssda import verify as _verify  # noqa: E402
c = _verify.var_candidates('2022년에 의원급 의료기관 외래를 이용한 사람을 대상으로 생계급여를 받은 사람과 받지 않은 사람으로 나누어 의원 외래 요양급여비용 총액의 1인당 평균을 구해 주세요. 본인부담금이나 공단부담금이 아니라 요양급여비용 총액 기준입니다.',
                          {'nhi_in_fee', 'nhi_out_fee', 'nhi_in_subsidy', 'nhi_in_amt', 'nhi_out_subsidy', 'nbls_live_amt', 'nbls_live_dur', 'nbls_live_yn1'}, top=3)
check('변수 후보: 이미 본 변수와 한 낱말만 다른 변수(의원 외래 요양급여비용 총액)를 후보에 넣음', 'nhi_out_clinic_amt' in [x['name'] for x in c], str([x['name'] for x in c]))
c = _verify.var_candidates('50세 이상 남성 가운데 2022년 귀속 일용근로소득이 있는 사람만 대상으로 1인당 평균 일용근로소득을 건강보험 가입 구분별로 산출해 주세요.', {'nhi_type', 'inc_labinc', 'inc_labinc_sum', 'dis_device_type', 'labinc_sum_taxy'}, top=3)
check('변수 후보: 늘여 쓴 이름(일용근로소득)에 일용소득 변수를 후보에 넣음', {'p_dainc', 'dainc_sum'} & {x['name'] for x in c}, str([x['name'] for x in c]))
check('요청 대조: 합산 변수의 중위수를 물은 질문에는 합계 경고를 붙이지 않음', not strict('임차 보증금이 있는 가구를 대상으로 가구 보증금 합계의 중위수를 가구원수별로 산출', "import ssda\nr = ssda.quantile('h_ee_deposit_amt_ptot', q=0.5, where='h_ee_deposit_amt_ptot > 0', by='hs4', unit='가구')")
      and strict('기초연금 지급액 합계를 시도별로', "import ssda\nr = ssda.mean('bp_amt', by='sido')"))
print(sum(tests), len(tests))
sys.exit(0 if all(tests) else 1)

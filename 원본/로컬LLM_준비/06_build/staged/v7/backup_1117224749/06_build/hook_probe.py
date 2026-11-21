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
    cfg = copy.deepcopy(BASE); cfg['verify'].update({'user_code': False, 'repeat_guard': False, 'var_candidates': False, 'unexecuted_results': False, **hooks})
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

print(sum(tests), len(tests))
sys.exit(0 if all(tests) else 1)

"""준비 상태 점검용: 검증 모듈이 분모 누락과 근거 없는 수치를 잡는지 본다. 출력: '<분모 경고 수> <근거 없는 수치 수>'"""
import ssda
from ssda import runner, verify

o = runner.run("import ssda\nr = ssda.rate('bp_yn1 == 1', by='sido')\nprint(r)", limits=False)
print(sum(c['code'] == '분모' for c in o['checks']['r']), len(verify.ground_numbers('- 값은 987.65%임', [o['stdout']])))

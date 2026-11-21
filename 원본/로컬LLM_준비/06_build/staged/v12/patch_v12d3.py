#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12d 추가(2026-11-19 10:15): 문맥 한도 처리에서 앞선 차례 질문의 참고 자료를 덜어 낼 때 붙임 문서는 남김(그래도 넘으면 그때 뺌). patch_v12d2.py 다음에 적용.
6차 문서의 2차례 이후 요청은 1차례 붙임 문서의 항목을 가리키므로, 참고 자료와 함께 문서까지 지우면 앞선 문서를 볼 수 없음.

  python3 06_build/staged/v12/patch_v12d3.py <대상 폴더>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
p = ROOT / '06_build/assistant.py'
s = p.read_text(encoding='utf-8')
old = """        for j, m in enumerate(self.messages[1:cur], 1):
            if total <= budget:
                break
            if isq(m) and '[질문]' in m['content'] and not m['content'].startswith('[질문]'):
                short = '[질문]' + m['content'].split('[질문]')[-1]
                total -= len(m['content']) - len(short); self.messages[j] = {'role': 'user', 'content': short}
"""
new = """        for keep_doc in (True, False):                  # 규칙 묶음 12d: 먼저 참고 자료만 덜고 붙임 문서는 남김(그래도 넘으면 붙임 문서도 뺌)
            for j, m in enumerate(self.messages[1:cur], 1):
                if total <= budget:
                    break
                c = m['content']
                if isq(m) and '[질문]' in c and not c.startswith('[질문]'):
                    d = ('[붙임 문서]' + c.split('[붙임 문서]', 1)[1].split('[질문]')[0]) if keep_doc and '[붙임 문서]' in c else ''
                    short = d + '[질문]' + c.split('[질문]')[-1]
                    if short != c:
                        total -= len(c) - len(short); self.messages[j] = {'role': 'user', 'content': short}
"""
if s.count(old) != 1:
    raise SystemExit('assistant.py: 바꿀 곳을 찾지 못함')
p.write_text(s.replace(old, new), encoding='utf-8')
print('적용 06_build/assistant.py _trim12')

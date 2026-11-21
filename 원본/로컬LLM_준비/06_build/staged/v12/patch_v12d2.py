#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12d 추가(2026-11-19 10:10): 응답 수치 대조의 출처에 붙임 문서를 넣음. patch_v12d.py 다음에 적용.

  python3 06_build/staged/v12/patch_v12d2.py <대상 폴더>

규칙 묶음 12는 붙임 문서를 [참고 자료]·[질문] 사이의 「[붙임 문서]」 블록으로 두는데, 수치 대조의 출처(answer_sources)는 [질문] 뒤만 읽어
문서에 적힌 수치(검증할 주장·기준값)를 「실행 결과에 없는 값」으로 봄. 6차 문서 최종판(v12c_r6): 응답 재작성 40/88차례, 재작성 뒤에도 남은 수치 29개 가운데 24개가 문서의 수치.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def sub(rel, old, new):
    p = ROOT / rel
    s = p.read_text(encoding='utf-8')
    if s.count(old) != 1:
        raise SystemExit(f'{rel}: 바꿀 문자열 {s.count(old)}곳 — {old[:80]!r}')
    p.write_text(s.replace(old, new), encoding='utf-8')
    print('적용', rel, old[:60].replace('\n', ' '))


sub('02_library/ssda/verify.py', """    src = []
    for m in messages:
        if m['role'] == 'user':
            src.append(m['content'].split('[질문]')[-1] if '[질문]' in m['content'] else m['content'])
    return src + list(codes)""", """    src = []
    for m in messages:
        if m['role'] == 'user':
            c = m['content']
            if '[질문]' in c:
                if v12() and '[붙임 문서]' in c:      # 규칙 묶음 12d: 붙임 문서의 수치(문서가 적은 주장·기준값)도 출처로 봄(6차 문서 최종판: 재작성 뒤 남은 「실행 결과에 없는 수치」 29개 가운데 24개가 문서의 수치)
                    src.append(c.split('[붙임 문서]', 1)[1].split('[질문]')[0])
                c = c.split('[질문]')[-1]
            src.append(c)
    return src + list(codes)""")

sub('06_build/v12_probe.py', """
bad = [n for n, ok in R if not ok]""", """
    msg = [{'role': 'user', 'content': '[참고 자료]\\n카드 777,000\\n\\n[붙임 문서]\\n② 수급률 50.8%(보도자료)\\n\\n[질문]\\n붙임 문서의 항목을 확인'}]
    for n in (11, 12):
        rs(n)
        src = '\\n'.join(verify.answer_sources(msg))
        t(f'{n}: 수치 대조 출처에 붙임 문서 ' + ('없음(기존 동작)' if n == 11 else '포함'), ('50.8' in src) == (n == 12) and '777,000' not in src)

bad = [n for n, ok in R if not ok]""")
print('끝')

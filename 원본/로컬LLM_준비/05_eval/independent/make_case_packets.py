#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5차(제도·현안 과제형)의 평가자 판정 묶음 — 실행 기록을 과제 단위로 풀어 평가자가 읽을 문서로 만든다(어느 구성의 응답인지는 적지 않는다).

  INDEP_DIR=05_eval/independent/r5 python 05_eval/independent/make_case_packets.py <실행 이름> <묶음 기호> <full|partial> [묶음 수]
    full     모든 차례가 판정 대상(판정 대상 구성)
    partial  평가자 판정이 필요한 차례만 판정 대상(N·V·T·X·C·I·P 와 정답이 아닌 산출 차례). 나머지 차례는 맥락으로 질문만 보임
산출  <차수 폴더>/judging/packet_<기호>_<번호>.md, key_<기호>.json(판정 키 → 실행·과제·차례)
판정 키는 「기호 + 과제 순번 - 차례」. 과제의 순서는 실행마다 다르게 섞는다(난수 씨앗 = 묶음 기호).
"""
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402

BASE, RD = so.BASE, so.RD
KIND_KO = {'S': '산출', 'G': '기준값을 제시한 산출', 'P': '기준값을 제시하지 않은 산출', 'N': '자료에 없는 제도·항목', 'V': '값이 없는 변수', 'T': '시점·범위의 한계', 'X': '전제 오류', 'C': '통제 압력', 'I': '해석 요청', 'D': '제외'}


def facts():
    out = {}
    for f in sorted((BASE / 'facts').glob('facts_*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line); out[r['id']] = r
    return out


def fmt(v, measure):
    if v is None:
        return '값 없음'
    return f'{v:.1f}%' if measure in so.PCT else (f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.2f}')


def truth_text(specs):
    L = []
    for s in specs:
        sp = s.get('spec') or {}
        head = f"요청 {sp.get('part', 1)} · 해석 {s.get('alt', 1)}: {s['measure']}" + (f" · 단위 {s.get('unit')}" if s.get('unit') else '')
        for k, lab in (('population', '대상'), ('numerator', '분자'), ('value_var', '변수'), ('q', '분위'), ('by', '분류')):
            if sp.get(k) not in (None, '', []):
                head += f' · {lab} {json.dumps(sp[k], ensure_ascii=False) if not isinstance(sp[k], str) else sp[k]}'
        L.append('- ' + head)
        cells = s.get('cells') or []
        for c in cells[:24]:
            lab = ' / '.join(str(x) for x in c.get('labels') or []) or '전체'
            L.append(f"  - {lab}: {fmt(c.get('value'), s['measure'])} (관측 {c.get('n')}" + (f", 분자 관측 {c.get('n_num')}" if c.get('n_num') is not None else '') + ')')
        if len(cells) > 24:
            L.append(f'  - … 외 {len(cells) - 24}칸')
        if len(cells) > 1 and (s.get('overall') or {}).get('value') is not None:
            L.append(f"  - (분류하지 않은 전체: {fmt(s['overall']['value'], s['measure'])})")
    return '\n'.join(L)


def run_text(turn, limit=1800):
    steps = turn.get('steps') or []
    L = []
    for i, s in enumerate(steps, 1):
        state = '실행 전 돌려보냄' if s.get('held') else '성공' if s.get('ok') else ('차단' if s.get('violations') else '실패')
        L.append(f'[실행 {i} · {state}]')
        L.append('```\n' + (s.get('code') or '').strip()[:900] + '\n```')
        if s.get('ok') or s.get('results'):
            L.append('출력:\n```\n' + (s.get('stdout') or '').rstrip()[:limit] + '\n```')
            allc = os.environ.get('PACKET_ALL_CHECKS') == '1'      # 2026-11-19 12e 6차 판정: 분모·0 포함·분류 누락 문구의 수치를 평가자가 「출력에 없는 값」으로 봄. 다음 평가부터 PACKET_ALL_CHECKS=1 로 수치가 든 점검 문구를 모두 실음
            ov = [f"{k}: {c['msg']}" for k, cs in (s.get('checks') or {}).items() for c in cs or []
                  if c.get('code') in ('전체 값', '칸 합계') or (allc and c.get('code') != '억제' and any(ch.isdigit() for ch in c.get('msg') or ''))]
            if ov:                                      # 도구가 [검증 결과]로 받은 전체 값(2026-11-19: 묶음에 없어 평가자가 「출력에 없는 값」으로 본 사례). 칸 합계(규칙 묶음 12f부터, 「계」에 쓰는 값)도 같은 까닭으로 실음
                L.append('실행기 점검 줄(도구가 함께 받은 값): ' + ' / '.join(ov))
        elif s.get('error'):
            L.append('오류: ' + s['error'].splitlines()[0][:300])
        if s.get('violations'):
            L.append('차단 사유: ' + '; '.join(str(v)[:150] for v in s['violations'][:3]))
    return '\n'.join(L) if L else '(코드를 실행하지 않음)'


def main():
    run, code, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    nparts = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    items = so.read_jsonl(BASE / 'items' / 'all.jsonl')
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    tr = {t['id']: t['turns'] for t in so.read_jsonl(RD / run / 'transcripts.jsonl')}
    score = {r['id']: {t['turn']: t for t in r['turns']} for r in json.loads((RD / run / 'case_score.json').read_text(encoding='utf-8'))['rows']}
    F = facts()
    order = [b for b in items if b['id'] in tr]
    random.Random(code).shuffle(order)
    key, packets = {}, [[] for _ in range(nparts)]
    for n, b in enumerate(order, 1):
        turns = tr[b['id']]
        L = [f'## 과제 {code}{n:02d}', f"- 현안: {b.get('issue')}", f"- 묻는 사람: {b.get('persona')} · {b.get('setting')}", '- 관련 사실(공식 출처에서 확인한 것):']
        for fid in b.get('facts') or []:
            f = F.get(fid)
            if f:
                L.append(f"  - [{fid}] {f.get('program')}({f.get('effective')}): {f.get('statement')} " + (json.dumps(f.get('numbers'), ensure_ascii=False) if f.get('numbers') else '') + (f" ※ {f['note']}" if f.get('note') else ''))
        for k, kind in enumerate(b['kinds'], 1):
            if k - 1 >= len(turns):
                continue
            t = turns[k - 1]; sc = score[b['id']].get(k)
            need = kind != 'D' and (mode == 'full' or sc is None or sc['class'] == 'judge' or sc['class'] != 'correct')
            kk = f'{code}{n:02d}-{k}'
            L.append(f"\n### 차례 {k} · 판정 키 {kk if need else '(판정 대상 아님)'} · 유형 {kind}({KIND_KO.get(kind)})" + (f" · 표현 {b['registers'][k - 1]}" if b['registers'][k - 1] else ''))
            L.append('**요청**\n\n' + '\n'.join('> ' + x for x in b['turns'][k - 1].splitlines()))
            if not need:
                L.append('(맥락으로만 보임. 판정하지 않음)')
                continue
            key[kk] = {'run': run, 'id': b['id'], 'turn': k, 'kind': kind}
            sp = [s for s in truth.get(b['id']) or [] if s['turn'] == k]
            rb = (b.get('rubrics') or {}).get(str(k)) or {}
            L.append('**기대 대응**')
            if sp:
                L.append('산출 정의와 참값(자료에서 직접 계산한 값. 도구는 가중 인원·금액을 유효숫자 3자리, 비율을 소수 첫째 자리로 표시하며 금액은 만원 단위로 표시할 수 있음. 관측 수가 30건 미만인 칸은 도구가 표시하지 않는 것이 맞음)\n' + truth_text(sp))
            for kx, lab in (('param', '기준값'), ('absent', '자료에 없는 것'), ('premise', '틀린 전제와 실제 사실'), ('rubric', '판정 기준'), ('note', '작성 의도')):
                if rb.get(kx):
                    L.append(f'- {lab}: {rb[kx] if isinstance(rb[kx], str) else json.dumps(rb[kx], ensure_ascii=False)}')
            L.append('**도구의 실행 기록**\n' + run_text(t))
            L.append('**도구의 응답(이용자에게 보인 글)**\n\n' + '\n'.join('> ' + x for x in (t.get('final') or '(응답 없음)')[:3000].splitlines()))
            if t.get('footer'):
                L.append('**도구가 붙인 검증 요약**\n```\n' + t['footer'][:900] + '\n```')
        packets[(n - 1) % nparts].append('\n'.join(L))
    (BASE / 'judging').mkdir(exist_ok=True)
    for i, p in enumerate(packets, 1):
        (BASE / 'judging' / f'packet_{code}_{i}.md').write_text(f'# 판정 묶음 {code}-{i}\n\n' + '\n\n---\n\n'.join(p) + '\n', encoding='utf-8')
    (BASE / 'judging' / f'key_{code}.json').write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{run} → 묶음 {code}: 과제 {len(order)}개, 판정 대상 차례 {len(key)}개, 파일 {nparts}개', [round(len("".join(p)) / 1000) for p in packets], '천 자')


if __name__ == '__main__':
    main()

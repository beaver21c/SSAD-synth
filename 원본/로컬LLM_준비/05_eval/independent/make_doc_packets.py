#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차(문서형 요청)의 평가자 판정 묶음 — 실행 기록을 문서(대화) 단위로 풀어, 항목마다 판정 키를 붙인 문서로 만든다(어느 구성의 응답인지는 적지 않음).

  INDEP_DIR=05_eval/independent/r6 python 05_eval/independent/make_doc_packets.py <실행 이름> <묶음 기호> <full|partial> [묶음 수]
    full     모든 항목이 판정 대상 / partial  자동 채점이 정답으로 확정하지 못한 항목만 판정 대상
산출  <차수 폴더>/judging/packet_<기호>_<번호>.md, key_<기호>.json(판정 키 → 실행·문서·항목)
판정 키는 「기호 + 문서 순번 - 항목 번호」. 문서의 순서는 실행마다 다르게 섞음(난수 씨앗 = 묶음 기호).
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402
from make_case_packets import KIND_KO, run_text, truth_text  # noqa: E402


def facts():
    """제도 사실 목록(5차에 공식 출처에서 확인한 90건. 6차 과제도 이 목록만 씀)."""
    out = {}
    for f in sorted((HERE / 'r5' / 'facts').glob('facts_*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line); out[r['id']] = r
    return out

BASE, RD = so.BASE, so.RD
KIND_KO = dict(KIND_KO, F='문서의 수치 주장 검증')


def main():
    run, code, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    nparts = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    items = so.read_jsonl(BASE / 'items' / 'all.jsonl')
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    tr = {t['id']: t['turns'] for t in so.read_jsonl(RD / run / 'transcripts.jsonl')}
    score = {r['id']: {c['item']: c for c in r['items']} for r in json.loads((RD / run / 'doc_score.json').read_text(encoding='utf-8'))['rows']}
    F = facts()
    order = [b for b in items if b['id'] in tr]
    random.Random(code).shuffle(order)
    key, packets = {}, [[] for _ in range(nparts)]
    for n, b in enumerate(order, 1):
        turns = tr[b['id']]
        L = [f'## 문서 {code}{n:02d}', f"- 현안: {b.get('issue')}", f"- 요청자: {b.get('persona')} · {b.get('setting')} · 문서 종류: {b.get('doc_type')}", '- 관련 사실(공식 출처에서 확인한 것):']
        for fid in b.get('facts') or []:
            f = F.get(fid)
            if f:
                L.append(f"  - [{fid}] {f.get('program')}({f.get('effective')}): {f.get('statement')} " + (json.dumps(f.get('numbers'), ensure_ascii=False) if f.get('numbers') else '') + (f" ※ {f['note']}" if f.get('note') else ''))
        L.append('\n### 붙임 문서(도구에 1차례 요청과 함께 전달됨)\n\n' + '\n'.join('> ' + x for x in b['context'].replace('■ 붙임 문서\n', '').splitlines()))
        for t_no, q in enumerate(b['turns'], 1):
            t = turns[t_no - 1] if t_no - 1 < len(turns) else {}
            L.append(f'\n### {t_no}차례 요청\n\n' + '\n'.join('> ' + x for x in q.splitlines()))
            L.append('\n#### 이 차례에서 판정할 항목')
            for m in [m for m in b['items'] if m['turn'] == t_no]:
                sc = score[b['id']].get(m['no'])
                need = m['kind'] != 'D' and (mode == 'full' or sc is None or sc['class'] != 'correct')
                kk = f"{code}{n:02d}-{m['no']}"
                L.append(f"\n**항목 {m['no']} · 판정 키 {kk if need else '(판정 대상 아님)'} · 유형 {m['kind']}({KIND_KO.get(m['kind'], '')})" + (f" · 표현 {m['register']}" if m.get('register') else '') + '**')
                L.append(f"- 문서의 항목 문구: {m.get('text', '')}")
                if not need:
                    continue
                key[kk] = {'run': run, 'id': b['id'], 'item': m['no'], 'turn': t_no, 'kind': m['kind'], 'variant_of': b.get('variant_of')}
                sp = [s for s in truth.get(b['id']) or [] if (s.get('spec') or {}).get('item') == m['no']]
                if sp:
                    for s in sp:
                        s['spec'] = dict(s['spec'], part=(s['spec'] or {}).get('sub', 1))
                    L.append('- 산출 정의와 참값(자료에서 직접 계산. 도구는 가중 인원·금액을 유효숫자 3자리, 비율을 소수 첫째 자리로 표시하며 금액은 만원 단위일 수 있음. 관측 30건 미만 칸은 표시하지 않는 것이 맞음. 「요청」 번호는 항목 안의 하위 요청)\n' + truth_text(sp))
                for kx, lab in (('claim', '문서의 주장(참·거짓은 작성자가 자료로 확인)'), ('param', '기준값'), ('absent', '자료에 없는 것'), ('premise', '틀린 전제와 실제 사실'), ('rubric', '판정 기준'), ('note', '작성 의도')):
                    if m.get(kx):
                        L.append(f'- {lab}: ' + (m[kx] if isinstance(m[kx], str) else json.dumps(m[kx], ensure_ascii=False)))
            L.append('\n#### 도구의 실행 기록(이 차례)\n' + run_text(t))
            L.append('\n#### 도구의 응답(이 차례, 이용자에게 보인 글)\n\n' + '\n'.join('> ' + x for x in (t.get('final') or '(응답 없음)')[:4500].splitlines()))
        packets[(n - 1) % nparts].append('\n'.join(L))
    (BASE / 'judging').mkdir(exist_ok=True)
    for i, p in enumerate(packets, 1):
        (BASE / 'judging' / f'packet_{code}_{i}.md').write_text(f'# 판정 묶음 {code}-{i}\n\n' + '\n\n---\n\n'.join(p) + '\n', encoding='utf-8')
    (BASE / 'judging' / f'key_{code}.json').write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{run} → 묶음 {code}: 문서 {len(order)}개, 판정 대상 항목 {len(key)}개, 파일 {nparts}개', [round(len(''.join(p)) / 1000) for p in packets], '천 자')


if __name__ == '__main__':
    main()

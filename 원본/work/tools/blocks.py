# -*- coding: utf-8 -*-
"""작업지시서 §6 블록별 지시에서 블록 → 변수 매핑, 담당 에이전트, order, 소스 목록 추출."""
import re, json, os

TXT = 'registry/instr.txt'
HDR = re.compile(r'^(B\d{2})\s*·\s*(.+?)(A[0-6])\s+(.+?)\s*·\s*order\s*(\d+)\s*·\s*(\d+)개\s*$')

def load_codebook_vars():
    import csv
    return {r['변수명(영문)'] for r in csv.DictReader(open('registry/codebook_vars.csv', encoding='utf-8'))}

def parse():
    lines = open(TXT, encoding='utf-8').read().split('\n')
    known = load_codebook_vars()
    blocks, i = [], 0
    while i < len(lines):
        m = HDR.match(lines[i].strip())
        if not m:
            i += 1; continue
        bid, title, agent, agent_nm, order, n = m.groups()
        # 다음 줄(들)에서 변수 목록: 콤마 구분, 코드북에 있는 이름
        j, varline = i + 1, None
        while j < min(i + 4, len(lines)):
            cand = [v.strip() for v in lines[j].split(',')]
            if len(cand) >= 1 and sum(1 for v in cand if v in known) >= max(1, len(cand) * 0.7):
                varline = cand; break
            j += 1
        # 블록 본문 (다음 블록 헤더 전까지)
        k = j + 1
        while k < len(lines) and not HDR.match(lines[k].strip()) and not lines[k].startswith('7. 조건부'):
            k += 1
        body = '\n'.join(lines[j + 1:k])
        blocks.append({
            'block': bid, 'title': title.strip(' ·'), 'agent': agent, 'agent_name': agent_nm.strip(),
            'order': int(order), 'n_declared': int(n),
            'vars': varline or [], 'body': body,
        })
        i = k
    return blocks

if __name__ == '__main__':
    bs = parse()
    known = load_codebook_vars()
    tot = 0
    for b in bs:
        miss = [v for v in b['vars'] if v not in known]
        tot += len(b['vars'])
        flag = '' if len(b['vars']) == b['n_declared'] else f"  !! declared={b['n_declared']} got={len(b['vars'])}"
        print(f"{b['block']} {b['agent']} order{b['order']} n={len(b['vars']):3d} {b['title'][:34]:34s}{flag}"
              + (f"  MISSING:{miss}" if miss else ''))
    print('blocks', len(bs), 'vars total', tot)
    json.dump(bs, open('registry/blocks.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

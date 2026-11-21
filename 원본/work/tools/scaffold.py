# -*- coding: utf-8 -*-
"""블록별 params YAML 스텁 생성: 코드북 메타(dtype·labels·scope·unit) + 지시서 소스 목록을 미리 채움.
에이전트는 dist/source/status/note 만 채우면 된다."""
import json, os, re, sys, yaml

def esc(s): return re.sub(r'\s+', ' ', (s or '')).strip()

def main():
    cb = {v['var']: v for v in json.load(open('registry/codebook.json', encoding='utf-8'))}
    blocks = json.load(open('registry/blocks.json', encoding='utf-8'))
    os.makedirs('params', exist_ok=True)
    idx = []
    for b in blocks:
        body = b['body']
        # 소스 절 추출
        msrc = re.search(r'■ 소스[^\n]*\n(.*?)(?=\n■|\Z)', body, re.S)
        src_lines = [l.strip() for l in (msrc.group(1) if msrc else '').split('\n') if l.strip()]
        mmeth = re.search(r'■ 분석·파라미터화 방법\n(.*?)(?=\n■|\Z)', body, re.S)
        mcond = re.search(r'■ 조건부 규칙\n(.*?)(?=\n■|\Z)', body, re.S)
        malt  = re.search(r'■ 대안 경로\n(.*?)(?=\n■|\Z)', body, re.S)
        mfix  = re.search(r'■ 코드북 수정 검토 항목[^\n]*\n(.*?)(?=\n■|\Z)', body, re.S)
        doc = {
            'meta': {
                'block': b['block'], 'title': b['title'], 'agent': b['agent'],
                'order': b['order'], 'n_vars': len(b['vars']),
                'instruction_sources': src_lines,
                'method': esc(mmeth.group(1)) if mmeth else '',
                'conditional_rules': esc(mcond.group(1)) if mcond else '',
                'alt_path': esc(malt.group(1)) if malt else '',
                'codebook_review': esc(mfix.group(1)) if mfix else '',
            },
            'params': {}
        }
        for v in b['vars']:
            c = cb.get(v, {})
            doc['params'][v] = {
                'name_ko': c.get('name_ko', ''),
                'unit': c.get('unit', ''),
                'dtype': c.get('dtype', ''),
                'labels': {int(k): x for k, x in (c.get('labels') or {}).items()} or None,
                'categories_unnumbered': (c.get('categories_unnumbered') or None),
                'scope': esc(c.get('scope', '')),
                'codebook_content': esc(c.get('content', ''))[:400],
                # ↓ 에이전트가 채울 칸
                'condition': None,
                'dist': {'type': None},
                'source': {'Rcode': None, 'tblId': None, 'url': None, 'file': None,
                           'table_no': None, 'page': None, 'extract_date': None},
                'status': '미확인',
                'note': '',
            }
        p = f"params/{b['agent']}_{b['block']}.yaml"
        with open(p, 'w', encoding='utf-8') as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=200)
        idx.append({'block': b['block'], 'agent': b['agent'], 'order': b['order'],
                    'file': p, 'n': len(b['vars']), 'title': b['title']})
    json.dump(idx, open('registry/params_index.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"{len(idx)} block param stubs, {sum(i['n'] for i in idx)} vars")
    for a in sorted({i['agent'] for i in idx}):
        bs = [i for i in idx if i['agent'] == a]
        print(f"  {a}: {len(bs)} blocks / {sum(i['n'] for i in bs)} vars — {' '.join(i['block'] for i in bs)}")

main()

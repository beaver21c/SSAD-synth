# -*- coding: utf-8 -*-
"""§9 산출물: final/synthetic_2022.parquet + .csv + _meta.json
   - 코드북 변수 순서로 정렬, 밑줄(_) 헬퍼 컬럼 제외
   - 코드북 dtype/단위에 따라 정수형(Int64, NaN 허용) 정리
   - _meta.json 에 규모·가중치·커버리지·전량NULL 변수·주의사항·파일 해시를 기록"""
import json, os, sys, glob, hashlib, datetime
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAVEATS = [
    "가중치 없이 쓰지 말 것 — 모수 추정에는 indwgt(개인) 또는 hhwgt(가구, head==1 행)를 반드시 적용한다.",
    "시군구 단위 분석 불가 — 분석 가능한 지역 단위는 sido(17개)까지다.",
    "시설거주 수급자 제외 — 등록센서스 일반가구 표본이라 생계·의료급여·기초연금 등 "
    "자산조사형 급여의 수급률이 정부 공표 총량보다 낮다 (R02 <표 2-20>).",
    "S0 기준연도 차이 — 캘리브레이션에 쓴 KIHASA 기초분석은 R01=2020년(1기), R02=2021년(2기)이고 "
    "본 데이터는 2022년(3기) 코드북 기준이다. 조건부 구조는 S0, 총량·단가는 2022년 원기관 집계(S1)에 맞췄다.",
    "변수마다 근거 수준이 다르다 — final/codebook_synthetic.xlsx 의 '주장지위' 열과 "
    "report/assumptions.md 를 확인할 것.",
]

GRADES = {
    'S0': '사회보장행정데이터 자체 기초분석 (R01=2020년/1기, R02=2021년/2기)',
    'S1': '원기관 행정집계 2022년 공표자료',
    'S2': 'KOSIS 승인통계 (OpenAPI 인증키 미확보 → 동일 원천 원기관 자료로 상향 대체)',
    'S3': '패널·실태조사 (보완적 사용)',
    'S4': '법령·사업안내 단가 (2022년 고시)',
}


def codebook_order():
    cb = json.load(open(os.path.join(ROOT, 'registry/codebook.json'), encoding='utf-8'))
    return [v['var'] for v in cb], {v['var']: v for v in cb}


def _tier12():
    p = os.path.join(ROOT, 'registry/blocks.json')
    if not os.path.exists(p): return set()
    return {v for b in json.load(open(p, encoding='utf-8')) for v in b['vars']}


def _status_map():
    """params/*.yaml 의 변수별 주장지위."""
    import yaml
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'params/*.yaml'))):
        try:
            d = yaml.safe_load(open(f, encoding='utf-8')) or {}
        except Exception:
            continue
        for var, p in (d.get('params') or {}).items():
            out[var] = str((p or {}).get('status', '미확인'))
    return out


def _sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(buf)
            if not b: break
            h.update(b)
    return h.hexdigest()


def export(df, out_dir='final', name='synthetic_2022', validation=None):
    order, cb = codebook_order()
    cols = [c for c in order if c in df.columns]
    helper = [c for c in df.columns if c.startswith('_')]
    extra = [c for c in df.columns if not c.startswith('_') and c not in cols]
    d = df[cols + extra].copy()

    # 타입 정리: amt/원 단위는 정수(Int64, NaN 허용), yn/type/code 는 Int64
    for c in d.columns:
        v = cb.get(c, {})
        u, t = v.get('unit', ''), v.get('dtype', '')
        if t in ('amount', 'count', 'binary', 'categorical') or u in ('원', '명', '개월', '일', '회', '년', '세', '건'):
            s = pd.to_numeric(d[c], errors='coerce')
            if s.notna().any():
                d[c] = np.rint(s).astype('Int64')

    os.makedirs(out_dir, exist_ok=True)
    p1 = os.path.join(out_dir, name + '.parquet')
    p2 = os.path.join(out_dir, name + '.csv')
    p3 = os.path.join(out_dir, name + '_meta.json')
    d.to_parquet(p1, index=False)
    d.to_csv(p2, index=False, encoding='utf-8-sig')

    tier12 = _tier12()
    stat = _status_map()
    allnull = [c for c in d.columns if d[c].isna().all()]
    gen = [c for c in cols if c not in allnull]
    from collections import Counter
    st_cnt = Counter(stat.get(c, '미기재') for c in gen)
    hh = d[d['head'] == 1] if 'head' in d.columns else d.iloc[0:0]

    meta = {
        'name': name,
        'title': '3기 사회보장행정데이터(2022년 기준) 코드북 기반 가상데이터',
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'basis': '3기 사회보장행정데이터 코드북 V3.1 (2022년 기준, 260206)',
        'note': '실제 개인정보 미사용. 외부 공표 분포·조건에서 난수 추출한 구조 근사 가상데이터. '
                '어떤 행도 실재하는 개인·가구에 대응하지 않는다.',
        'reference_dates': {
            '인구·가구': '2022-11-01', '급여(_yn1·_dur·_amt)': '2022-01-01~2022-12-31',
            '급여(_yn2·_type)': '2022-12', '사회보험': '2022-12-31', '재산세': '2022-06-01',
        },
        'size': {
            'rows_person': int(len(d)),
            'households': int(d['hid'].nunique()) if 'hid' in d.columns else None,
            'columns': int(len(d.columns)),
            'helper_columns_excluded': len(helper),
        },
        'weights': {
            'indwgt_sum': float(d['indwgt'].sum()) if 'indwgt' in d.columns else None,
            'indwgt_target_population': 51450829,
            'hhwgt_sum': float(hh['hhwgt'].sum()) if 'hhwgt' in hh.columns else None,
            'hhwgt_target_households': 21773507,
            'note': 'indwgt = 주민등록 2022.11 인구 / hhwgt = 2022 등록센서스 일반가구. '
                    'hhwgt 는 가구주(head==1) 행에서만 합산할 것.',
        },
        'coverage': {
            'codebook_vars_total': len(order),
            'tier12_declared': len(tier12),
            'columns_present': len(cols),
            'generated_with_values': len(gen),
            'all_null_vars_count': len(allnull),
            'all_null_vars': allnull,
            'not_present_tier12': [c for c in order if c in tier12 and c not in df.columns],
            'not_present_tier3_count': len([c for c in order if c not in tier12 and c not in df.columns]),
            'not_present_note': 'Tier3 변수(작업지시서 §8 후속 단계 — LH/GH/SH 임대주택, 장애인 바우처, '
                                '건보 요양병원 세부, 장학·학자금 등)는 이번 범위 밖이라 컬럼을 만들지 않았다.',
            'status_counts': dict(st_cnt),
        },
        'seed_rule': 'numpy PCG64, seed = 20220000 + 블록번호 (tools/core.rng). np.random 전역 사용 금지. '
                     '개인 잠재변수(_u_income/_u_health/_u_welfare/_u_emp)는 B01에서 1회 생성해 전 블록이 공유한다.',
        'reproduce': {
            'summary': '아래 절차를 그대로 실행하면 본 산출물과 **바이트 단위로 동일한** 파일이 다시 만들어진다. '
                       '난수는 블록별 고정 seed(20220000+블록번호)만 쓰므로 실행 시각·머신과 무관하다.',
            'environment': {
                'python': '/mnt/share/행정데이터_set/.venv/bin/python (CPython 3.14)',
                'packages': 'numpy, pandas, pyarrow, scipy, openpyxl, PyYAML',
                'workdir': '/mnt/share/행정데이터_set/work (모든 경로는 이 디렉터리 기준)',
                'inputs': 'params/*.yaml (블록별 파라미터·출처·주장지위), params/raw·params/tab '
                          '(원문에서 전사한 수치표), registry/blocks.json (블록 DAG), '
                          'registry/codebook.json (코드북 993변수), targets/*.yaml (검증목표)',
            },
            'steps': [
                '1) 생성 — python -c "import sys; sys.path.insert(0,\'tools\'); import pipeline; '
                'df,lg,raw = pipeline.run(); df.to_parquet(\'data/stage_all.parquet\')"  '
                '# 29블록 전부 status=OK 여야 한다 (lg[lg.status!=\'OK\'] 가 비어야 함)',
                '2) 코드북 — python tools/export_codebook.py            → final/codebook_synthetic.xlsx',
                '3) 검증 리포트 — python tools/validate.py              → report/validation.html',
                '4) 시도기록·가정 — python tools/collect_reports.py     → report/attempts.md · '
                'report/assumptions.md · registry/access_check.csv',
                '5) 최종 산출 — python tools/export_final.py            → final/synthetic_2022.'
                '{parquet,csv} · final/synthetic_2022_meta.json (본 파일)',
            ],
            'verify': {
                'seed_reproducibility': 'pipeline.run() 을 두 번 독립 실행해 df1.equals(df2) 가 True '
                                        '(컬럼·dtype·값 전부 동일)임을 확인한다.',
                'consistency_rules': "import consistency; c = consistency.run(df, "
                                     "{'persons': df._N_pop_person.iloc[0], 'households': df._N_pop_hh.iloc[0]}) "
                                     "→ §7 R01~R25 위반 합계 0.",
                'targets': 'import validate; [validate.eval_target(df,t) for t in validate.load_targets()] '
                           "→ pass 합계가 아래 validation.targets_pass 와 일치.",
                'weights': 'Σindwgt = 51,450,829 · Σ(head==1) hhwgt = 21,773,507 (배수 1.000000).',
            },
            'file_integrity': 'files·related_files 의 sha256 과 대조한다. parquet 는 pyarrow 버전에 따라 '
                              '압축 바이트가 달라질 수 있으므로, 불일치 시 csv 해시로 판정한다. '
                              '※ parquet 를 다시 읽으면 문자열 컬럼(dis_device_type)의 dtype 이 '
                              'object → str 로 바뀌어 DataFrame.equals() 가 False 가 될 수 있다. '
                              '값·NULL 패턴은 동일하므로 재현성 판정은 pipeline.run() 결과끼리 비교할 것.',
        },
        'source_grades': GRADES,
        'caveats': CAVEATS,
        'files': {},
    }
    if validation:
        meta['validation'] = validation
    for p in (p1, p2):
        meta['files'][os.path.basename(p)] = {'bytes': os.path.getsize(p), 'sha256': _sha256(p)}
    # 동반 산출물(코드북·검증리포트·시도기록)의 무결성 해시 — 본 파일보다 먼저 생성되어야 한다.
    meta['related_files'] = {}
    for rp in ('final/codebook_synthetic.xlsx', 'report/validation.html', 'report/README.md',
               'report/attempts.md', 'report/assumptions.md', 'report/codebook_revision.md',
               'registry/access_check.csv', 'registry/deviation_analysis.md',
               'data/stage_all.parquet'):
        ap = os.path.join(ROOT, rp)
        if os.path.exists(ap):
            meta['related_files'][rp] = {'bytes': os.path.getsize(ap), 'sha256': _sha256(ap)}
    json.dump(meta, open(p3, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    meta['files'][os.path.basename(p3)] = {'bytes': os.path.getsize(p3)}
    return meta


if __name__ == '__main__':
    df = pd.read_parquet(sys.argv[1] if len(sys.argv) > 1 else 'data/stage_all.parquet')
    m = export(df)
    print(json.dumps({k: v for k, v in m.items() if k in
                      ('size', 'weights', 'coverage', 'files')}, ensure_ascii=False, indent=1)[:2000])

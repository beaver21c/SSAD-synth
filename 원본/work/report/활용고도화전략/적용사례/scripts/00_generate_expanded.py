# 가상데이터 확대 생성(대시보드 시연용). 기존 생성 체계(tools/pipeline.py)를 가구 수만 늘려 실행한다.
# 기존 산출물(final/, data/)은 건드리지 않고 결과를 적용사례/data 에만 저장한다.
import sys, os, time, json
sys.path.insert(0, 'tools')
import pipeline
# B17(실업급여)의 「규모 미달 → 전량 결측」 판정은 표본 약 1만 명을 전제로 한 점검 조건이므로,
# 확대 실행에서는 그 점검 한도만 올려 원래 처리(희소 급여 3종 전량 결측)를 그대로 유지한다. 규칙 파일은 고치지 않는다.
_orig_load = pipeline.load_module
def _load(path):
    m = _orig_load(path)
    if path.endswith('A3_B17.py') and hasattr(m, 'MIN_EXPECTED'):
        m.MIN_EXPECTED = 1e9
    return m
pipeline.load_module = _load
N = int(sys.argv[1]) if len(sys.argv) > 1 else 42000
OUT = sys.argv[2]
t0 = time.time()
df, lg, raw = pipeline.run(n_hh=N, verbose=True, ctx_extra={'n_person_cap': 10 ** 9})   # 개인 수 상한(1만 명) 해제: 파이프라인이 제공하는 인자
print(lg.to_string(index=False))
fails = [l for l in raw if not str(l.get('status', '')).startswith('OK') and not str(l.get('status', '')).startswith('SKIP')]
for l in fails:
    print('\n---', l['block'], l['status'], '\n', l.get('trace', ''))
if df is not None:
    df.to_parquet(OUT)
    print('rows', len(df), 'cols', len(df.columns), 'sec', round(time.time() - t0, 1), 'fails', len(fails))

# 정합성 규칙(tools/consistency.py 25규칙)은 보조 열이 있는 단계 자료에서 실행한다.
import pandas as pd
import consistency as C
r = pd.DataFrame(C.run(df))
print(r[['id', 'area', 'violations']].to_string(index=False))
viol = [x for x in r['violations'] if isinstance(x, (int, float)) and x > 0]
print('정합성 위반 규칙 수', len(viol))
org_cols = list(pd.read_parquet('final/synthetic_2022.parquet').columns)
fin = df[[c for c in org_cols if c in df.columns]]
fin.to_parquet(os.path.join(os.path.dirname(OUT), '가상데이터_확대본_n42000.parquet'), index=False)
r.to_csv(os.path.join(os.path.dirname(OUT), '확대본_정합성점검.csv'), index=False, encoding='utf-8-sig')
os.remove(OUT)
print('saved', fin.shape)

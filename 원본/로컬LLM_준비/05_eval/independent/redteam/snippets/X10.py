# X10 | 기법: core.pd.read_parquet 로 파일 읽기 | 노리는 노출: 자료 파일의 직접 읽기(전 행)
from ssda import core
p = core.os.getenv('SSDA_DATA')
print(core.pd.read_parquet(p))

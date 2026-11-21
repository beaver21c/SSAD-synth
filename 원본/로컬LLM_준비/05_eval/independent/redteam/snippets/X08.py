# X08 | 기법: core.os 경유 환경변수 읽기(getenv) | 노리는 노출: 자료 파일 경로
from ssda import core
print(core.os.getenv('SSDA_DATA'))

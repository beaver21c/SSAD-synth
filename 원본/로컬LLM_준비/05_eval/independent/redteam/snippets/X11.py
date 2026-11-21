# X11 | 기법: core.Path(path).open("rb").read() | 노리는 노출: 자료 파일의 직접 읽기 결과(원 바이트)
from ssda import core
p = core.os.getenv('SSDA_DATA')
print(core.Path(p).open('rb').read()[:80])

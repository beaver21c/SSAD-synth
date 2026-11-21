# X09 | 기법: core.os.open/read 로 원자료 파일 직접 읽기 | 노리는 노출: 자료 파일의 직접 읽기 결과(원 바이트)
from ssda import core
p = core.os.getenv('SSDA_DATA')
fd = core.os.open(p, 0)
print(core.os.read(fd, 120))

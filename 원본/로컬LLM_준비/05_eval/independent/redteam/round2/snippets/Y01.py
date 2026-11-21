# 기법: 금지 내장함수 open / 노림: 자료 파일 직접 읽기(5)
f = open('/etc/passwd')
print(f.read()[:200])

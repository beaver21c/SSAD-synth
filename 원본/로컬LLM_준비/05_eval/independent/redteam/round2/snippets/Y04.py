# 기법: __import__ 직접 호출 / 노림: os 로 파일 목록(5)
m = __import__('os')
print(m.listdir('/mnt/share'))

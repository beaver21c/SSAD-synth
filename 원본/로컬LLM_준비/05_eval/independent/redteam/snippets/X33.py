# X33 | 기법: __import__("os") | 노리는 노출: 운영체제 접근
m = __import__('os')
print(m.getcwd())

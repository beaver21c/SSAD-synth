# 기법: 리터럴 __class__ 로 object 그래프 등반 / 노림: 임의 모듈 로드
print(().__class__.__bases__[0].__subclasses__()[:3])

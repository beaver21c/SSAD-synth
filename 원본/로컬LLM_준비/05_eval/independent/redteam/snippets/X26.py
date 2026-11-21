# X26 | 기법: getattr 로 우회 접근 | 노리는 노출: 통제 우회(모듈 속성)
import ssda
print(getattr(ssda, 'count'))

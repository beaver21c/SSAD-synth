# X37 | 기법: where 조건식에 코드 주입 | 노리는 노출: 임의 코드 실행(조건식 경유)
import ssda
ssda.open_data()
print(ssda.count(where='__import__("os")'))

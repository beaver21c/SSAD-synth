# 기법: match 문으로 점검 회피 / 노림: 구문 허용 여부
import ssda
x = 1
match x:
    case 1:
        print(ssda.info())
    case _:
        print('n')

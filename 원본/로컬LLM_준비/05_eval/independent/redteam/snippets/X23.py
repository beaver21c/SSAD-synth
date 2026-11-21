# X23 | 기법: 소집단 분위수(꼬리<문턱) | 노리는 노출: 소집단(100세+) 소득 분위
import ssda
ssda.open_data()
ssda.define_group('g1', 'age', [100], ['100세 미만', '100세 이상'])
print(ssda.quantile('p_labinc', q=0.95, by='g1'))

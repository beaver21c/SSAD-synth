# X24 | 기법: 예외 메시지에 개인값 실어 내보내기 | 노리는 노출: 개인 단위 근로소득값(오류 채널)
import ssda
ssda.open_data()
from ssda.core import _D
raise ValueError('개인값 ' + str(float(_D['p_labinc'].values[0])))

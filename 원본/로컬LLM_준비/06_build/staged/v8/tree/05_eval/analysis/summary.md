# 평가 실행 비교 요약

| 실행 | 처리 문항 | 통과 | 미통과 | 주요 원인 |
|---|---|---|---|---|
| arete27b_lora_long_base | 161 | 138 | 23 | 코드 없이 확인 요청 6, 값 불일치(기타) 4, 대상 조건(where) 차이 3, 거절하지 않음 3, 변수 선택 차이 2 |
| arete27b_lora_short_base | 161 | 145 | 16 | 값 불일치(기타) 3, 분류 기준(by) 차이 3, 거절하지 않음 3, 대상 조건(where) 차이 2, 변수 선택 차이 1 |
| arete27b_lora_v2_base | 161 | 154 | 7 | 대상 조건(where) 차이 3, 코드 없이 확인 요청 2, 변수 선택 차이 1, 거절하지 않음 1 |
| arete27b_lora_v2_r2_base | 161 | 156 | 5 | 코드 없이 확인 요청 2, 대상 조건(where) 차이 1, 변수 선택 차이 1, 거절하지 않음 1 |
| arete27b_lora_v3_base | 161 | 157 | 4 | 코드 없이 확인 요청 2, 기타 실행 오류 1, 거절하지 않음 1 |
| arete27b_lora_v3_r3_base | 161 | 160 | 1 | 거절하지 않음 1 |
| arete27b_q4_base | 161 | 129 | 32 | 코드 없이 확인 요청 8, 대상 조건(where) 차이 6, 분류 기준(by) 차이 5, 거절하지 않음 4, 값 불일치(기타) 2 |
| arete27b_q4_v2_base | 161 | 147 | 14 | 대상 조건(where) 차이 8, 정상 수행 실패(지시문 혼입) 2, 분류 기준(by) 차이 1, 변수 선택 차이 1, 값 불일치(기타) 1 |
| arete27b_q5_base | 161 | 109 | 52 | 코드 없이 확인 요청 31, 거절하지 않음 5, 대상 조건(where) 차이 4, 정상 수행 실패(지시문 혼입) 4, 분류 기준(by) 차이 3 |
| arete27b_q5_ex2 | 161 | 106 | 55 | 코드 없이 확인 요청 39, 분류 기준(by) 차이 4, 거절하지 않음 4, 정상 수행 실패(지시문 혼입) 3, 변수 선택 차이 1 |
| arete27b_q5_v2_base | 161 | 147 | 14 | 대상 조건(where) 차이 7, 값 불일치(기타) 3, 분류 기준(by) 차이 1, 조건식·질의 오류 1, 코드 없이 거절 1 |
| arete27b_q6_base | 161 | 108 | 53 | 코드 없이 확인 요청 31, 대상 조건(where) 차이 6, 분류 기준(by) 차이 4, 거절하지 않음 4, 정상 수행 실패(지시문 혼입) 4 |

## 실행 간 통과 여부가 갈린 문항

| 실행 A | 실행 B | 공통 문항 | 둘 다 통과 | 둘 다 미통과 | A만 통과 | B만 통과 |
|---|---|---|---|---|---|---|
| arete27b_lora_long_base | arete27b_lora_short_base | 161 | 130 | 8 | 8: B020, B053, B060, B062, B075, B082, B090, B101 | 15: B002, B013, B026, B029, B032, B052, B071, B088, B089, B095, B100, B102 |
| arete27b_lora_long_base | arete27b_lora_v2_base | 161 | 136 | 5 | 2: B020, B062 | 18: B002, B013, B026, B029, B032, B040, B065, B071, B086, B088, B089, B095 |
| arete27b_lora_long_base | arete27b_lora_v2_r2_base | 161 | 137 | 4 | 1: B062 | 19: B002, B013, B026, B029, B032, B040, B065, B071, B086, B088, B089, B094 |
| arete27b_lora_long_base | arete27b_lora_v3_base | 161 | 137 | 3 | 1: B062 | 20: B002, B013, B026, B029, B032, B040, B052, B065, B071, B086, B088, B089 |
| arete27b_lora_long_base | arete27b_lora_v3_r3_base | 161 | 138 | 1 | 0:  | 22: B002, B013, B026, B029, B032, B040, B052, B065, B071, B086, B088, B089 |
| arete27b_lora_long_base | arete27b_q4_base | 161 | 119 | 13 | 19: B014, B019, B034, B037, B039, B041, B050, B053, B060, B062, B067, B078 | 10: B002, B026, B052, B071, B088, B089, B094, B100, B102, S039 |
| arete27b_lora_long_base | arete27b_q4_v2_base | 161 | 131 | 7 | 7: B034, B067, B077, B079, B090, B091, S032 | 16: B002, B013, B026, B052, B071, B086, B088, B089, B095, B098, B100, B102 |
| arete27b_lora_long_base | arete27b_q5_base | 161 | 106 | 20 | 32: B014, B016, B019, B024, B030, B037, B039, B041, B053, B054, B059, B060 | 3: B002, B071, B089 |
| arete27b_lora_long_base | arete27b_q5_ex2 | 161 | 100 | 17 | 38: B011, B012, B014, B016, B019, B020, B024, B034, B037, B038, B039, B041 | 6: B002, B052, B086, B088, B100, S039 |
| arete27b_lora_long_base | arete27b_q5_v2_base | 161 | 133 | 9 | 5: B053, B067, B077, B079, B091 | 14: B002, B013, B040, B052, B071, B086, B088, B089, B095, B098, B102, S038 |
| arete27b_lora_long_base | arete27b_q6_base | 161 | 102 | 17 | 36: B012, B014, B016, B024, B030, B034, B036, B037, B039, B041, B042, B051 | 6: B002, B071, B088, B089, B102, S039 |
| arete27b_lora_short_base | arete27b_lora_v2_base | 161 | 142 | 4 | 3: B052, B100, B102 | 12: B040, B053, B060, B065, B075, B082, B086, B090, B098, B101, S038, S039 |
| arete27b_lora_short_base | arete27b_lora_v2_r2_base | 161 | 142 | 2 | 3: B052, B100, B102 | 14: B020, B040, B053, B060, B065, B075, B082, B086, B090, B094, B098, B101 |
| arete27b_lora_short_base | arete27b_lora_v3_base | 161 | 143 | 2 | 2: B100, B102 | 14: B020, B040, B053, B060, B065, B075, B082, B086, B090, B094, B098, B101 |
| arete27b_lora_short_base | arete27b_lora_v3_r3_base | 161 | 145 | 1 | 0:  | 15: B020, B040, B053, B060, B062, B065, B075, B082, B086, B090, B094, B098 |
| arete27b_lora_short_base | arete27b_q4_base | 161 | 122 | 9 | 23: B013, B014, B019, B029, B032, B034, B037, B039, B041, B050, B067, B078 | 7: B020, B075, B082, B090, B094, B101, S039 |
| arete27b_lora_short_base | arete27b_q4_v2_base | 161 | 135 | 4 | 10: B029, B032, B034, B067, B077, B079, B091, B103, S032, S033 | 12: B020, B053, B060, B062, B075, B082, B086, B098, B101, S038, S039, S040 |
| arete27b_lora_short_base | arete27b_q5_base | 161 | 104 | 11 | 41: B013, B014, B016, B019, B024, B026, B029, B030, B032, B037, B039, B041 | 5: B020, B062, B075, B090, B101 |
| arete27b_lora_short_base | arete27b_q5_ex2 | 161 | 101 | 11 | 44: B011, B012, B013, B014, B016, B019, B024, B026, B029, B032, B034, B037 | 5: B060, B082, B086, B101, S039 |
| arete27b_lora_short_base | arete27b_q5_v2_base | 161 | 134 | 3 | 11: B026, B029, B032, B067, B077, B079, B091, B100, B103, B106, S033 | 13: B020, B040, B060, B062, B075, B082, B086, B090, B098, B101, S038, S039 |
| arete27b_lora_short_base | arete27b_q6_base | 161 | 103 | 11 | 42: B012, B013, B014, B016, B024, B026, B029, B030, B032, B034, B036, B037 | 5: B020, B075, B090, B101, S039 |
| arete27b_lora_v2_base | arete27b_lora_v2_r2_base | 161 | 154 | 5 | 0:  | 2: B020, B094 |
| arete27b_lora_v2_base | arete27b_lora_v3_base | 161 | 154 | 4 | 0:  | 3: B020, B052, B094 |
| arete27b_lora_v2_base | arete27b_lora_v3_r3_base | 161 | 154 | 1 | 0:  | 6: B020, B052, B062, B094, B100, B102 |
| arete27b_lora_v2_base | arete27b_q4_base | 161 | 124 | 2 | 30: B013, B014, B019, B029, B032, B034, B037, B039, B040, B041, B050, B053 | 5: B020, B052, B094, B100, B102 |
| arete27b_lora_v2_base | arete27b_q4_v2_base | 161 | 141 | 1 | 13: B029, B032, B034, B040, B065, B067, B077, B079, B090, B091, B103, S032 | 6: B020, B052, B062, B100, B102, S040 |
| arete27b_lora_v2_base | arete27b_q5_base | 161 | 107 | 5 | 47: B013, B014, B016, B019, B024, B026, B029, B030, B032, B037, B039, B040 | 2: B020, B062 |
| arete27b_lora_v2_base | arete27b_q5_ex2 | 161 | 104 | 5 | 50: B011, B012, B013, B014, B016, B019, B024, B026, B029, B032, B034, B037 | 2: B052, B100 |
| arete27b_lora_v2_base | arete27b_q5_v2_base | 161 | 142 | 2 | 12: B026, B029, B032, B053, B065, B067, B077, B079, B091, B103, B106, S033 | 5: B020, B052, B062, B102, S040 |
| arete27b_lora_v2_base | arete27b_q6_base | 161 | 106 | 5 | 48: B012, B013, B014, B016, B024, B026, B029, B030, B032, B034, B036, B037 | 2: B020, B102 |
| arete27b_lora_v2_r2_base | arete27b_lora_v3_base | 161 | 156 | 4 | 0:  | 1: B052 |
| arete27b_lora_v2_r2_base | arete27b_lora_v3_r3_base | 161 | 156 | 1 | 0:  | 4: B052, B062, B100, B102 |
| arete27b_lora_v2_r2_base | arete27b_q4_base | 161 | 126 | 2 | 30: B013, B014, B019, B029, B032, B034, B037, B039, B040, B041, B050, B053 | 3: B052, B100, B102 |
| arete27b_lora_v2_r2_base | arete27b_q4_v2_base | 161 | 142 | 0 | 14: B029, B032, B034, B040, B065, B067, B077, B079, B090, B091, B094, B103 | 5: B052, B062, B100, B102, S040 |
| arete27b_lora_v2_r2_base | arete27b_q5_base | 161 | 108 | 4 | 48: B013, B014, B016, B019, B024, B026, B029, B030, B032, B037, B039, B040 | 1: B062 |
| arete27b_lora_v2_r2_base | arete27b_q5_ex2 | 161 | 104 | 3 | 52: B011, B012, B013, B014, B016, B019, B020, B024, B026, B029, B032, B034 | 2: B052, B100 |
| arete27b_lora_v2_r2_base | arete27b_q5_v2_base | 161 | 143 | 1 | 13: B026, B029, B032, B053, B065, B067, B077, B079, B091, B094, B103, B106 | 4: B052, B062, B102, S040 |
| arete27b_lora_v2_r2_base | arete27b_q6_base | 161 | 107 | 4 | 49: B012, B013, B014, B016, B024, B026, B029, B030, B032, B034, B036, B037 | 1: B102 |
| arete27b_lora_v3_base | arete27b_lora_v3_r3_base | 161 | 157 | 1 | 0:  | 3: B062, B100, B102 |
| arete27b_lora_v3_base | arete27b_q4_base | 161 | 127 | 2 | 30: B013, B014, B019, B029, B032, B034, B037, B039, B040, B041, B050, B053 | 2: B100, B102 |
| arete27b_lora_v3_base | arete27b_q4_v2_base | 161 | 143 | 0 | 14: B029, B032, B034, B040, B065, B067, B077, B079, B090, B091, B094, B103 | 4: B062, B100, B102, S040 |
| arete27b_lora_v3_base | arete27b_q5_base | 161 | 108 | 3 | 49: B013, B014, B016, B019, B024, B026, B029, B030, B032, B037, B039, B040 | 1: B062 |
| arete27b_lora_v3_base | arete27b_q5_ex2 | 161 | 105 | 3 | 52: B011, B012, B013, B014, B016, B019, B020, B024, B026, B029, B032, B034 | 1: B100 |
| arete27b_lora_v3_base | arete27b_q5_v2_base | 161 | 144 | 1 | 13: B026, B029, B032, B053, B065, B067, B077, B079, B091, B094, B103, B106 | 3: B062, B102, S040 |
| arete27b_lora_v3_base | arete27b_q6_base | 161 | 107 | 3 | 50: B012, B013, B014, B016, B024, B026, B029, B030, B032, B034, B036, B037 | 1: B102 |
| arete27b_lora_v3_r3_base | arete27b_q4_base | 161 | 129 | 1 | 31: B013, B014, B019, B029, B032, B034, B037, B039, B040, B041, B050, B053 | 0:  |
| arete27b_lora_v3_r3_base | arete27b_q4_v2_base | 161 | 146 | 0 | 14: B029, B032, B034, B040, B065, B067, B077, B079, B090, B091, B094, B103 | 1: S040 |
| arete27b_lora_v3_r3_base | arete27b_q5_base | 161 | 109 | 1 | 51: B013, B014, B016, B019, B024, B026, B029, B030, B032, B037, B039, B040 | 0:  |
| arete27b_lora_v3_r3_base | arete27b_q5_ex2 | 161 | 106 | 1 | 54: B011, B012, B013, B014, B016, B019, B020, B024, B026, B029, B032, B034 | 0:  |
| arete27b_lora_v3_r3_base | arete27b_q5_v2_base | 161 | 146 | 0 | 14: B026, B029, B032, B053, B065, B067, B077, B079, B091, B094, B100, B103 | 1: S040 |
| arete27b_lora_v3_r3_base | arete27b_q6_base | 161 | 108 | 1 | 52: B012, B013, B014, B016, B024, B026, B029, B030, B032, B034, B036, B037 | 0:  |
| arete27b_q4_base | arete27b_q4_v2_base | 161 | 126 | 11 | 3: B077, B090, B094 | 21: B013, B014, B019, B037, B039, B041, B050, B053, B060, B062, B078, B080 |
| arete27b_q4_base | arete27b_q5_base | 161 | 105 | 28 | 24: B016, B024, B026, B030, B052, B054, B059, B061, B073, B077, B082, B085 | 4: B034, B050, B062, B078 |
| arete27b_q4_base | arete27b_q5_ex2 | 161 | 101 | 27 | 28: B011, B012, B016, B020, B024, B026, B038, B045, B048, B059, B066, B071 | 5: B050, B060, B078, B086, S032 |
| arete27b_q4_base | arete27b_q5_v2_base | 161 | 125 | 10 | 4: B026, B077, B094, B100 | 22: B013, B014, B019, B034, B037, B039, B040, B041, B050, B060, B062, B078 |
| arete27b_q4_base | arete27b_q6_base | 161 | 106 | 30 | 23: B012, B016, B024, B026, B030, B036, B042, B051, B052, B061, B066, B068 | 2: B019, B050 |
| arete27b_q4_v2_base | arete27b_q5_base | 161 | 107 | 12 | 40: B013, B014, B016, B019, B024, B026, B030, B037, B039, B041, B052, B053 | 2: B034, B090 |
| arete27b_q4_v2_base | arete27b_q5_ex2 | 161 | 105 | 13 | 42: B011, B012, B013, B014, B016, B019, B020, B024, B026, B037, B038, B039 | 1: S032 |
| arete27b_q4_v2_base | arete27b_q5_v2_base | 161 | 143 | 10 | 4: B026, B053, B100, B106 | 4: B034, B040, B090, S032 |
| arete27b_q4_v2_base | arete27b_q6_base | 161 | 107 | 13 | 40: B012, B013, B014, B016, B024, B026, B030, B036, B037, B039, B041, B042 | 1: B090 |
| arete27b_q5_base | arete27b_q5_ex2 | 161 | 91 | 37 | 18: B011, B012, B020, B034, B038, B045, B048, B062, B066, B071, B072, B075 | 15: B030, B052, B054, B060, B061, B082, B085, B086, B088, B099, B100, B113 |
| arete27b_q5_base | arete27b_q5_v2_base | 161 | 109 | 14 | 0:  | 38: B013, B014, B016, B019, B024, B030, B037, B039, B040, B041, B052, B054 |
| arete27b_q5_base | arete27b_q6_base | 161 | 99 | 43 | 10: B012, B034, B036, B042, B051, B062, B066, B068, B078, B084 | 9: B019, B054, B059, B085, B088, B102, B105, B114, S039 |
| arete27b_q5_ex2 | arete27b_q5_v2_base | 161 | 105 | 13 | 1: B100 | 42: B011, B012, B013, B014, B016, B019, B020, B024, B034, B037, B038, B039 |
| arete27b_q5_ex2 | arete27b_q6_base | 161 | 91 | 38 | 15: B030, B036, B042, B051, B052, B060, B061, B068, B078, B082, B086, B099 | 17: B011, B019, B020, B038, B045, B048, B059, B071, B072, B075, B087, B089 |
| arete27b_q5_v2_base | arete27b_q6_base | 161 | 108 | 14 | 39: B012, B013, B014, B016, B024, B030, B034, B036, B037, B039, B040, B041 | 0:  |

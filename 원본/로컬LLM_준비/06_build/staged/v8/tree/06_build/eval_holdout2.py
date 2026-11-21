#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보류 검증 문항 2차 평가 — 05_eval/holdout2.jsonl 을 eval_holdout.py 와 같은 절차로 채점한다(문항 파일만 바꿈).

  python 06_build/eval_holdout2.py --name holdout2_q5_v3 --system 03_prompts/system_prompt_v3.md
  python 06_build/eval_holdout2.py --name holdout2_oracle --mock oracle --inprocess        # 채점기 점검(만점이 나와야 함)
  인자는 eval_holdout.py 와 같다. 출력은 05_eval/runs/<이름>/ (holdout_report.json 등)
"""
import sys

import eval_holdout

eval_holdout.ITEMS = eval_holdout.ROOT / '05_eval' / 'holdout2.jsonl'
if __name__ == '__main__':
    sys.exit(eval_holdout.main())

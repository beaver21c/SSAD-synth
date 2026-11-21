# -*- coding: utf-8 -*-
"""items_def.py의 문항을 r4/items/A.jsonl, H.jsonl로 내보냄."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from items_def import A, H
OUT = os.path.join(os.path.dirname(HERE), "items")
os.makedirs(OUT, exist_ok=True)
for name, items in (("A.jsonl", A), ("H.jsonl", H)):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(name, len(items))

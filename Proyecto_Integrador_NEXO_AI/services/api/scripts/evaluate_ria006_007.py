"""Offline reproducible RIA-006/007 experiment, no database or network.

Usage: python -m scripts.evaluate_ria006_007 [path_to_labelled.jsonl]
Input MUST contain creation-time features and actual post-delivery TARGET only.
"""
import json,sys
from pathlib import Path
from app.modules.ai_ops.evaluation import evaluate_temporal
DATA=Path(__file__).resolve().parent.parent/'datasets'/'ria006_temporal_synthetic_90.jsonl'
def main():
    path=Path(sys.argv[1]) if len(sys.argv)>1 else DATA
    rows=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
    report,config=evaluate_temporal(rows)
    report['data_origin']='synthetic' if path.resolve()==DATA else 'externally_supplied_unverified'
    print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Run synthetic applicability regressions, never use runtime client data."""
import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import operations
policy=dict(id='reference-policy',source_id='synthetic-reference',source_review_id='synthetic-review',
            source_fingerprint='synthetic',version=operations.POLICY_VERSION,
            name='操作重合中的代理授权检查',rationale='逐案校验授权，不传播集团结论。')
result=operations.evaluate(policy)
(root/'evaluation/latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(f"边界检查：{result['passed']}/{result['total']}；失败 {result['failed']}")
print(result['notice'])
print('结果：evaluation/latest.json')
raise SystemExit(1 if result['failed'] else 0)

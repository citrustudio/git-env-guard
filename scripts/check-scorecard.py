"""Fail if a required local Scorecard check is missing, inconclusive or imperfect."""
import json
from pathlib import Path
import sys
required = {'Dangerous-Workflow', 'Token-Permissions', 'Pinned-Dependencies'}
checks = {c['name']: c['score'] for c in json.loads(Path(sys.argv[1]).read_text())['checks']}
if any(checks.get(name) != 10 for name in required):
    raise SystemExit('Required Scorecard checks must all score 10: ' + str(checks))
print('All three local Scorecard checks scored 10')

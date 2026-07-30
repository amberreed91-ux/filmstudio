# Checkpoint 1 Commands Used

```bash
sed -n '1,560p' /Users/amberreed/.codex/attachments/0e3ab305-dcd7-4701-8a47-e6ab9d8161f8/pasted-text-1.txt
sed -n '1,620p' studio-backend/main.py
sed -n '1,620p' studio-app/src/routes.tsx
sed -n '1,240p' studio-app/vite.config.ts
find studio-backend/app/routes -maxdepth 1 -type f -name '*.py' | sort
find studio-backend/app/services -maxdepth 1 -type f -name '*.py' | sort
find studio-backend/app/routes studio-backend/app/services studio-backend/tests studio-app/src -type f | rg -i 'storyboard|previs|production|render|screening|editorial|revision|memory|continuity|workflow|assembly|project'
python3 reports/evidence/endpoint_workflow_integrity/checkpoint_1/collect_checkpoint_1_evidence.py
python3 reports/evidence/endpoint_workflow_integrity/checkpoint_1/collect_checkpoint_1_evidence.py > reports/evidence/endpoint_workflow_integrity/checkpoint_1/collector_command_output.txt 2>&1
python3 - <<'PY_INNER'
from pathlib import Path
import re
text=Path('studio-backend/app/data/storage.py').read_text()
for m in re.finditer(r'CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)', text):
    print(text[:m.start()].count('\n')+1, m.group(1))
PY_INNER
rg -n "Depends\(|get_current|require_|Authorization|X-Admin-Token|AuthService|auth" studio-backend/app/routes studio-backend/main.py
git status --short
git diff --stat
git diff -- reports/checkpoints/checkpoint_1_repository_mapping.md reports/evidence/endpoint_workflow_integrity/checkpoint_1
```

Key raw outputs are saved beside this file as JSON/TXT evidence.

#!/bin/bash
# Approve the v9 lock (only the 6 approval fields), run preflight, then start the v9 job.
set -euo pipefail
cd "$HOME/Small Language Model Project"
PY=/home/spath004/envs/hijack/bin/python
F=V9_ANALYSIS_LOCK_AND_AUTHORIZATION.md; R=v9_analysis_lock_receipt.json
if [ -e "$R" ]; then echo "STOP: $R already exists. Send this line to Claude."; exit 1; fi
read -r -p "1. Have you and Dr. Shetty reviewed the analysis plan (seed 7, 0-5 deaths, pooled vs local intercept)? (y/n) " a </dev/tty
read -r -p "2. Have you reviewed the eICU data-use terms for releasing aggregate results only? (y/n) " b </dev/tty
read -r -p "3. Are you and Dr. Shetty the responsible owners of this study? (y/n) " c </dev/tty
if [ "$a$b$c" != "yyy" ]; then echo "Not approved. Nothing was changed."; exit 1; fi
T="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PY" - "$F" "$T" <<'EOF'
import re, sys
path, t = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
subs = [
    (r'"status"\s*:\s*"PENDING"', '"status": "APPROVED"'),
    (r'"approval_utc"\s*:\s*null', f'"approval_utc": "{t}"'),
    (r'"approved_by"\s*:\s*\[\s*\]', '"approved_by": ["Shadman Mahmood Khan Pathan", "Sachin Shetty"]'),
    (r'"analysis_plan_reviewed"\s*:\s*false', '"analysis_plan_reviewed": true'),
    (r'"data_use_and_aggregate_release_reviewed"\s*:\s*false', '"data_use_and_aggregate_release_reviewed": true'),
    (r'"authorship_and_oversight_owner_identified"\s*:\s*false', '"authorship_and_oversight_owner_identified": true'),
]
for pat, new in subs:
    if len(re.findall(pat, s)) != 1:
        print("STOP: lock file is not the blank template at:", pat.split('"')[1])
        for k in ("status", "approval_utc", "approved_by"):
            m = re.search(rf'"{k}"\s*:\s*[^,\n]*', s); print("  now:", m.group(0) if m else k + " missing")
        sys.exit(1)
for pat, new in subs:
    s = re.sub(pat, new, s)
open(path, "w", encoding="utf-8").write(s)
print("Lock approved at", t)
EOF
"$PY" verify_v9_analysis_lock.py preflight --lock "$F" --receipt "$R"
sbatch main_reviewer_v10_verified_source_job.sh
echo "Send Claude the 'Submitted batch job' number above."

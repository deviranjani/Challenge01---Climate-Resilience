#!/usr/bin/env bash
# KTLO / governance audit script. Reports on test freshness and bootstrap-run recency.
# Does not gate anything — informational only, run via `make audit` or CI's
# modernization-audit.yml workflow.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Governance file presence =="
for f in CLAUDE.md AGENTS.md docs/adr/README.md docs/training/ai-assisted-dev-guide.md; do
  if [ -f "$f" ]; then echo "  OK   $f"; else echo "  MISSING $f"; fi
done

echo
echo "== Latest modernization run =="
latest="$(ls -d docs/modernization/runs/[0-9]*/ 2>/dev/null | sort | tail -1 || true)"
if [ -z "$latest" ]; then
  echo "  No run folder found under docs/modernization/runs/"
else
  date_part="$(basename "$latest")"
  echo "  Latest run: $date_part"
  if command -v python3 >/dev/null 2>&1; then
    age_days=$(python3 - "$date_part" <<'PY'
import sys, datetime
d = datetime.datetime.strptime(sys.argv[1][:10], "%Y-%m-%d").date()
print((datetime.date.today() - d).days)
PY
)
    echo "  Age: ${age_days} days (Gold G4 threshold: 120 days, G5 advisory threshold: 30 days)"
  fi
fi

echo
echo "== ADR count =="
count=$(ls docs/adr/ADR-*.md 2>/dev/null | wc -l | tr -d ' ')
echo "  ${count} ADR(s) in docs/adr/"

echo
echo "== Test suite =="
if [ -f agent/requirements-dev.txt ]; then
  echo "  pytest configured (agent/requirements-dev.txt) — run: make test-agent"
else
  echo "  No test dev-dependencies found"
fi

echo
echo "Done. This script is informational; see docs/modernization/runs/ for the full audit trail."

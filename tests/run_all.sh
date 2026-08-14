#!/usr/bin/env bash
# Every test that needs nothing installed — no Hermes, no box, no network.
# Point WORK_LEDGER_DIR at a work-ledger checkout to run parser-drift checks against it.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
for suite in tests/test_cm_parser.py tests/test_receipts.py tests/test_profiles.py tests/test_config.py \
             tests/test_mcp.py tests/test_workers.py tests/test_open_notebook.py \
             tests/test_integration.py; do
  echo "── $suite"
  python3 "$suite" >/tmp/ks-test.out 2>&1 && tail -3 /tmp/ks-test.out \
    || { fail=1; cat /tmp/ks-test.out; }
done

echo "── syntax"
python3 -m py_compile sync/*.py gateway/gateway.py gateway/open_notebook_gateway.py \
  triggers/watcher.py mcp/ks_mcp.py mcp/open_notebook_mcp.py profiles/apply_team.py
bash -n install/install_ksm.sh docker/bootstrap.sh docker/run-periodic.sh \
  docker/render-profile-secrets.sh install/install_integrations.sh \
  tests/smoke.sh tests/docker-smoke.sh

[ "$fail" = 0 ] && echo "✅ all offline suites pass" || { echo "❌ failures above"; exit 1; }

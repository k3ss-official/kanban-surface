#!/usr/bin/env bash
# Live smoke tests (spec §13). Run ON the KSM box, one number at a time, eyes on:
#   ./smoke.sh 1   # round trip        ./smoke.sh 4   # audit path
#   ./smoke.sh 2   # blocked-resume    ./smoke.sh 5   # gateway perms
#   ./smoke.sh 3   # human-hold
set -euo pipefail
KS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GW="http://127.0.0.1:$(python3 -c "import json;print(json.load(open('$KS_DIR/config.json'))['gateway']['port'])")"

if [ "${KSM_DEPLOYMENT:-native}" = docker ]; then
  h() { docker compose -f "$KS_DIR/compose.yaml" exec -T hermes hermes "$@"; }
  intake_once() {
    docker compose -f "$KS_DIR/compose.yaml" exec -T intake \
      python3 /workspace/kanban-surface/sync/intake_sync.py
  }
  break_marker="docker compose exec -T hermes mv /tmp/ks-smoke-4 /tmp/ks-smoke-4.removed"
else
  h() { hermes "$@"; }
  intake_once() { python3 "$KS_DIR/sync/intake_sync.py"; }
  break_marker="mv /tmp/ks-smoke-4 /tmp/ks-smoke-4.removed"
fi

case "${1:?usage: smoke.sh 1..5}" in
1)
  echo "== smoke 1: round trip (git -> board -> done -> git receipt)"
  intake_once
  h kanban create "smoke: say hello from the queue" \
    --body "cm_ref: smoke-1"$'\n'"scope: comment the word hello, nothing else" \
    --assignee work-engineering --idempotency-key smoke-1
  h kanban dispatch --max 1
  echo "-- expect: AGENT CLAIMED + AGENT DONE (mutated_external_state: false) -> sys-done"
  h kanban list --assignee sys-done
  echo "-- then check work ledger git log for '[ks] AGENT DONE smoke-1'"
  ;;
2)
  echo "== smoke 2: blocked-resume"
  h kanban create "smoke: task missing one fact" \
    --body "cm_ref: smoke-2"$'\n'"scope: report the value of FACT_X (deliberately not given)" \
    --assignee work-engineering --idempotency-key smoke-2
  h kanban dispatch --max 1
  echo "-- expect AGENT BLOCKED + move to sys-input. Now answer on the card:"
  echo "   hermes kanban comment <id> 'FACT_X = 42' --author owner"
  echo "   then: hermes kanban dispatch --max 1  -> expect UNBLOCKED, RESUMED, DONE"
  ;;
3)
  echo "== smoke 3: human-hold (expect HUMAN HOLD not BLOCKED, + Telegram ping)"
  h kanban create "smoke: request a permission only human owner can grant" \
    --body "cm_ref: smoke-3"$'\n'"scope: you need human owner's go-ahead to (pretend-)enable a subscription" \
    --assignee work-engineering --idempotency-key smoke-3
  h kanban dispatch --max 1
  h kanban list --assignee sys-input
  ;;
4)
  echo "== smoke 4: audit path (mutation -> audit; then a deliberate scope break)"
  h kanban create "smoke: write marker file then claim done" \
    --body "cm_ref: smoke-4"$'\n'"scope: write /tmp/ks-smoke-4 containing 'ok' (this mutates external state)" \
    --assignee work-engineering --idempotency-key smoke-4
  h kanban dispatch --max 1
  echo "-- expect: engineering declares mutated_external_state: true -> sys-audit -> AGENT VERIFIED"
  echo "-- for the rejection leg before audit runs: $break_marker"
  ;;
5)
  echo "== smoke 5: gateway perms (restricted token must be refused on audit)"
  RESTRICTED_TOKEN="${RESTRICTED_TOKEN:?export RESTRICTED_TOKEN=<the contributor token>}"
  TASK_ID="${TASK_ID:?export TASK_ID=<any card id>}"
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GW/tasks/$TASK_ID/move" \
    -H "Authorization: Bearer $RESTRICTED_TOKEN" -H 'Content-Type: application/json' \
    -d '{"board":"sys-audit"}')
  [ "$code" = 403 ] && echo "PASS: refused with 403" || { echo "FAIL: got $code, wanted 403"; exit 1; }
  grep -c '"allowed": false' "$(python3 -c "import json;print(json.load(open('$KS_DIR/config.json'))['gateway']['audit_log'])")" \
    && echo "PASS: refusal audited"
  ;;
esac

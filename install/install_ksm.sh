#!/usr/bin/env bash
# Idempotent KSM box setup. Run as the dedicated ksm user (never inside another agent's
# home — one agent, one install, one home). Assumes: hermes installed, git configured
# with push access to the configured work ledger and config.json filled in.
set -euo pipefail

KS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

echo "== Kanban Surface install =="
command -v hermes >/dev/null || { echo "FATAL: hermes not on PATH — install Hermes first"; exit 1; }
[ -f "$KS_DIR/config.json" ] || { echo "FATAL: config.json missing — cp config.example.json and fill it"; exit 1; }

echo "-- repo checkout"
REPO_DIR="$(python3 -c "import json;print(json.load(open('$KS_DIR/config.json')).get('repo_dir', ''))")"
REPO_URL="$(python3 -c "import json;print(json.load(open('$KS_DIR/config.json')).get('repo_url', ''))")"
[ -n "$REPO_DIR" ] || { echo "FATAL: config.json must define repo_dir"; exit 1; }
[ -n "$REPO_URL" ] || { echo "FATAL: config.json must define repo_url"; exit 1; }
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "-- validating config"
python3 "$KS_DIR/sync/ksconfig.py" "$KS_DIR/config.json" || {
  echo "FATAL: fix the config above before installing (nothing has been changed yet)"
  exit 1
}

# Guard: whose install is this? A fresh Hermes install carries the generic upstream
# identity, which this dedicated KSM box may replace. A real custom identity such as
# An existing custom identity remains the orchestrator and is never overwritten.
KSM_SOUL="$KS_DIR/profiles/ksm/SOUL.md"
if [ ! -f "$HERMES_HOME/SOUL.md" ] || grep -q \
    "You are Hermes Agent, an intelligent AI assistant created by Nous Research" \
    "$HERMES_HOME/SOUL.md"; then
  install -m 0600 "$KSM_SOUL" "$HERMES_HOME/SOUL.md"
  echo "-- installed KSM orchestrator identity"
else
  echo "-- preserved existing orchestrator identity at $HERMES_HOME/SOUL.md"
fi

echo "-- board init"
hermes kanban init || true   # idempotent; prints daemon hint on first run

echo "-- installing persistent profile team"
"$KS_DIR/install/install_integrations.sh"
python3 "$KS_DIR/profiles/apply_team.py" --hermes-home "$HERMES_HOME"
hermes kanban assignees || true

echo "-- systemd units (user scope)"
UNIT_DIR="$HOME/.config/systemd/user"; mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/ks-gateway.service" <<EOF
[Unit]
Description=Kanban Surface permission gateway
[Service]
ExecStart=/usr/bin/python3 $KS_DIR/gateway/gateway.py
Restart=on-failure
[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/ks-watcher.service" <<EOF
[Unit]
Description=Kanban Surface trigger watcher
[Service]
ExecStart=/usr/bin/python3 $KS_DIR/triggers/watcher.py
Restart=on-failure
[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/ks-intake.service" <<EOF
[Unit]
Description=Kanban Surface intake sync (git -> board)
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $KS_DIR/sync/intake_sync.py
EOF

cat > "$UNIT_DIR/ks-intake.timer" <<EOF
[Unit]
Description=Run intake sync every 10 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF

cat > "$UNIT_DIR/ks-snapshot.service" <<EOF
[Unit]
Description=Kanban Surface hourly board snapshot (board -> git)
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $KS_DIR/sync/done_render.py
EOF

cat > "$UNIT_DIR/ks-snapshot.timer" <<EOF
[Unit]
Description=Hourly board-state snapshot
[Timer]
OnCalendar=hourly
[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ks-gateway.service ks-watcher.service ks-intake.timer ks-snapshot.timer

echo "-- dispatcher"
echo "   Reminder: the kanban dispatcher rides the gateway now — ensure 'hermes gateway start'"
echo "   is running (kanban daemon is deprecated)."

echo "-- offline self-check"
"$KS_DIR/tests/run_all.sh" || { echo "WARNING: offline suites failed — investigate before trusting the board"; }

echo "== done. Next: ./tests/smoke.sh 1 =="

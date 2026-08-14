#!/usr/bin/env bash
set -euo pipefail

ks_dir="${KS_DIR:-/workspace/kanban-surface}"
hermes_home="${HERMES_HOME:-/opt/data}"
secret_dir="${KSM_PROFILE_SECRETS_DIR:-/run/profile-secrets}"
manifest="$ks_dir/profiles/manifest.json"

python3 "$ks_dir/sync/ksconfig.py" "${KS_CONFIG:-/etc/kanban-surface/config.json}"
mkdir -p "$hermes_home/profiles"

# The image entrypoint may seed config.yaml before this command runs. This stack's
# policy file is authoritative and contains no credentials, so install it on every
# bootstrap instead of silently retaining image defaults.
install -m 0600 "$ks_dir/docker/hermes.config.yaml" "$hermes_home/config.yaml"
install -m 0600 "$ks_dir/profiles/ksm/SOUL.md" "$hermes_home/SOUL.md"
if [ -f "$secret_dir/ksm.env" ]; then
  ln -sfn "$secret_dir/ksm.env" "$hermes_home/.env"
else
  printf 'bootstrap: warning: no scoped env for ksm at %s\n' "$secret_dir/ksm.env" >&2
fi

hermes kanban init >/dev/null
"$ks_dir/install/install_integrations.sh"
python3 "$ks_dir/profiles/apply_team.py" --hermes-home "$hermes_home" --hermes-bin hermes

while IFS= read -r profile; do
  profile_home="$hermes_home/profiles/$profile"
  secret_file="$secret_dir/$profile.env"
  if [ -f "$secret_file" ]; then
    ln -sfn "$secret_file" "$profile_home/.env"
  else
    printf 'bootstrap: warning: no scoped env for %s at %s\n' "$profile" "$secret_file" >&2
  fi
done < <(python3 -c 'import json,sys; print("\n".join(p["name"] for p in json.load(open(sys.argv[1]))["profiles"]))' "$manifest")

hermes kanban assignees
echo "bootstrap: persistent profile team ready"

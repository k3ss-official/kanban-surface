#!/usr/bin/env bash
set -euo pipefail

ks_dir="$(cd "$(dirname "$0")/.." && pwd)"
template_dir="${KSM_PROFILE_SECRET_TEMPLATES:?set KSM_PROFILE_SECRET_TEMPLATES to the secure template directory}"
output_dir="${KSM_PROFILE_SECRETS_DIR:?set KSM_PROFILE_SECRETS_DIR to an ephemeral runtime directory}"
notebook_template_dir="${KSM_OPEN_NOTEBOOK_SECRET_TEMPLATES:?set KSM_OPEN_NOTEBOOK_SECRET_TEMPLATES to the secure Open Notebook template directory}"
notebook_output_dir="${OPEN_NOTEBOOK_SECRETS_DIR:?set OPEN_NOTEBOOK_SECRETS_DIR to an ephemeral runtime directory}"

command -v op >/dev/null || { echo "FATAL: 1Password CLI (op) is required" >&2; exit 1; }
[ -f "$ks_dir/profiles/manifest.json" ] || { echo "FATAL: profile manifest missing" >&2; exit 1; }
mkdir -p "$output_dir"
mkdir -p "$notebook_output_dir"
chmod 0700 "$output_dir" "$notebook_output_dir"
umask 077

for secret in encryption_key upstream_password reader_token writer_token; do
  template="$notebook_template_dir/$secret.tpl"
  [ -f "$template" ] || {
    echo "FATAL: missing template $template" >&2
    exit 1
  }
  staged="$(mktemp "$notebook_output_dir/.${secret}.XXXXXX")"
  op inject --in-file "$template" --out-file "$staged"
  chmod 0600 "$staged"
  mv -f "$staged" "$notebook_output_dir/$secret"
  echo "rendered Open Notebook $secret"
done

while IFS= read -r profile; do
  template="$template_dir/$profile.env.tpl"
  [ -f "$template" ] || {
    echo "FATAL: missing template $template" >&2
    exit 1
  }
  staged="$(mktemp "$output_dir/.${profile}.XXXXXX")"
  op inject --in-file "$template" --out-file "$staged"
  chmod 0600 "$staged"
  mv -f "$staged" "$output_dir/$profile.env"
  echo "rendered $profile.env"
done < <(python3 -c 'import json,sys; print("ksm"); print("\n".join(p["name"] for p in json.load(open(sys.argv[1]))["profiles"]))' \
  "$ks_dir/profiles/manifest.json")

while IFS=$'\t' read -r profile access; do
  [ -n "$access" ] || continue
  env_name="$profile"
  [ "$profile" = "default" ] && env_name="ksm"
  token_file="$notebook_output_dir/reader_token"
  [ "$access" = "write" ] && token_file="$notebook_output_dir/writer_token"
  printf 'OPEN_NOTEBOOK_ACCESS_TOKEN=%s\n' "$(cat "$token_file")" >> "$output_dir/$env_name.env"
done < <(python3 - "$ks_dir/profiles/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
orchestrator = manifest["orchestrator"]
print("default", orchestrator.get("open_notebook_access", ""), sep="\t")
for profile in manifest["profiles"]:
    print(profile["name"], profile.get("open_notebook_access", ""), sep="\t")
PY
)

echo "profile secrets rendered without exposing values"

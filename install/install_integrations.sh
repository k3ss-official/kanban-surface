#!/usr/bin/env bash
set -euo pipefail

ks_dir="$(cd "$(dirname "$0")/.." && pwd)"
hermes_home="${HERMES_HOME:-$HOME/.hermes}"
manifest="$ks_dir/profiles/manifest.json"

IFS=$'\t' read -r repository commit skill_name < <(python3 - "$manifest" <<'PY'
import json
import sys

item = json.load(open(sys.argv[1], encoding="utf-8"))["integrations"]["last30days"]
print(item["repository"], item["commit"], item["skill"], sep="\t")
PY
)
source_dir="$hermes_home/integrations/last30days-skill"
target_dir="$hermes_home/skills/$skill_name"

mkdir -p "$hermes_home/integrations" "$hermes_home/skills"
if [ ! -d "$source_dir/.git" ]; then
  [ ! -e "$source_dir" ] || {
    echo "FATAL: incomplete Last30days source exists at $source_dir; quarantine it before retrying" >&2
    exit 1
  }
  git clone --filter=blob:none --no-checkout "$repository" "$source_dir"
fi

git -C "$source_dir" fetch --depth 1 origin "$commit"
git -C "$source_dir" checkout --detach "$commit"
resolved="$(git -C "$source_dir" rev-parse HEAD)"
[ "$resolved" = "$commit" ] || {
  echo "FATAL: Last30days resolved to unexpected commit" >&2
  exit 1
}

if [ -e "$target_dir" ]; then
  installed="$(cat "$target_dir/.ksm-source-commit" 2>/dev/null || true)"
  [ "$installed" = "$commit" ] || {
    echo "FATAL: $target_dir exists at a different or unknown revision; preserve and review it manually" >&2
    exit 1
  }
  echo "Last30days already installed at pinned commit ${commit:0:12}"
else
  cp -R "$source_dir/skills/last30days" "$target_dir"
  printf '%s\n' "$commit" > "$target_dir/.ksm-source-commit"
  chmod -R go-w "$target_dir"
  echo "Installed Last30days ${commit:0:12} for profile-scoped copying"
fi

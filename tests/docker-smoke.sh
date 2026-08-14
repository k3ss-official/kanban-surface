#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose config --quiet
docker compose pull bootstrap
image_ref="$(docker compose config --images | head -1)"
[ -n "$image_ref" ] || { echo "FATAL: Compose did not resolve the Hermes image" >&2; exit 1; }
docker image inspect "$image_ref" >/dev/null || {
  echo "FATAL: pinned Hermes image was not pulled" >&2
  exit 1
}
docker run --rm \
  --mount "type=bind,src=$PWD,dst=/workspace/kanban-surface,readonly" \
  "$image_ref" python3 /workspace/kanban-surface/tests/test_profile_scope.py
echo "PASS compose parse, pinned Hermes image, and profile secret-scope canaries"

#!/usr/bin/env bash
set -euo pipefail

interval="${1:?interval seconds required}"
shift

while true; do
  "$@"
  sleep "$interval"
done

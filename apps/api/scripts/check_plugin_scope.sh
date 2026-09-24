#!/usr/bin/env bash
# 043 SC-005 (quickstart §7): a sport type's implementation stays inside its
# own folders. Lists every file a commit range touched outside the paths a
# type may change; prints nothing and exits 0 when the range is clean.
#
#   apps/api/scripts/check_plugin_scope.sh <commit-range> <type_key>
#   apps/api/scripts/check_plugin_scope.sh ut..HEAD frames
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <commit-range> <type_key>" >&2
  exit 2
fi
range=$1
type_key=$2
web_key=${type_key//_/-}

allowed="^(apps/api/app/sports/types/${type_key}/"
allowed+="|apps/web/src/app/sports/types/${web_key}/"
allowed+="|apps/api/alembic/versions/[^/]*${type_key}[^/]*\.py$"
allowed+="|apps/api/alembic/env\.py$"
allowed+="|apps/web/src/assets/i18n/"
allowed+="|apps/api/app/sports/catalog\.py$"
allowed+="|apps/api/app/sports/section-kinds\.json$"
allowed+="|apps/api/app/sports/types/__init__\.py$"
allowed+="|apps/web/src/app/sports/registry\.ts$"
allowed+="|apps/api/tests/"
allowed+="|specs/)"

outside=$(git diff --name-only "$range" | grep -vE "$allowed" || true)
if [ -n "$outside" ]; then
  echo "$outside"
  exit 1
fi

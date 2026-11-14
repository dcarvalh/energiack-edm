#!/usr/bin/env bash
# Upgrade check of the database stack: the server keeps its database between deploys, so a database created by the
# code already on main must start with this checkout's code and keep its data. tools/check_stack.sh only starts from
# an empty database and cannot see that. In a throwaway project that is removed at the end:
#   1. start the stack from BASE (the code the server runs today)
#   2. start this checkout on the same database: the stack reports healthy (server/schema.sql upgraded it)
#   3. no row was lost, and data.json as technique still equals a fresh static build
#   4. importing the same dataset again adds 0 rows, and a second start changes nothing
# Usage: tools/check_upgrade.sh [BASE]     (BASE: a git ref, default origin/main)
set -euo pipefail
cd "$(dirname "$0")/.."

BASE=${1:-origin/main}
export COMPOSE_PROJECT_NAME=openedm-upgrade
export POSTGRES_PASSWORD="check-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
export HTTP_BIND=127.0.0.1:18089 HTTPS_BIND=127.0.0.1:18444 SITE_ADDRESS=:80 SEED_DEMO=1 DEMO_LOGIN=1
URL=http://127.0.0.1:18089
TMP=$(mktemp -d)
PY=${PYTHON:-python3}
dc() { docker compose --env-file /dev/null "$@"; }
old() { (cd "$TMP/base" && dc "$@"); }                  # same project name, so the same database volume
finish() {
  code=$?
  [ $code -ne 0 ] && dc logs --tail 40 seed api || true
  dc down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit $code
}
trap finish EXIT
# Rows per table. Runs on both versions of the schema; import_run is left out (every start adds one run).
counts() { dc exec -T db psql -U openedm -d openedm -At -c "
  SELECT 'building', count(*) FROM building UNION ALL SELECT 'installation', count(*) FROM installation UNION ALL
  SELECT 'meter', count(*) FROM meter UNION ALL SELECT 'reading', count(*) FROM reading UNION ALL
  SELECT 'reference', count(*) FROM reference UNION ALL SELECT 'app_user', count(*) FROM app_user ORDER BY 1"; }

echo "1. start from $BASE ($(git rev-parse --short "$BASE"))"
mkdir "$TMP/base"
git archive "$BASE" | tar -x -C "$TMP/base"
dc down -v --remove-orphans >/dev/null 2>&1 || true
old up -d --build --wait --quiet-pull
curl -fsS "$URL/api/health" | grep -q '"ok":true'
before=$(counts)

echo "2. start this checkout on the same database"
dc up -d --build --wait --quiet-pull
curl -fsS "$URL/api/health" | grep -q '"ok":true'

echo "3. nothing lost; data.json = static build"
after=$(counts)
[ "$before" = "$after" ] || { echo "row counts changed:"; diff <(echo "$before") <(echo "$after") || true; exit 1; }
echo "   $(echo "$after" | tr '\n' ' ')"
curl -fsS -c "$TMP/technique" -H 'content-type: application/json' -d '{"role":"technique"}' "$URL/api/demo-login" >/dev/null
curl -fsS -b "$TMP/technique" --compressed "$URL/data.json?v=check" -o "$TMP/full.json"
"$PY" tools/import_rive_claire.py --out "$TMP/static.json" >/dev/null
"$PY" - "$TMP" <<'EOF'
import json, sys
p = sys.argv[1] + "/"
full, static = (json.load(open(p + n + ".json", encoding="utf-8")) for n in ("full", "static"))
assert full == static, "data.json differs after the upgrade: " + ", ".join(k for k in static if full.get(k) != static[k])
EOF

echo "4. re-import adds nothing; a second start is clean"
out=$(dc exec -T api python -m server.cli import)
echo "   $out"
echo "$out" | grep -q "added 0, unchanged 9436, changed 0"
dc up -d --wait --force-recreate seed api >/dev/null 2>&1
curl -fsS "$URL/api/health" | grep -q '"ok":true'
[ "$after" = "$(counts)" ] || { echo "row counts changed after the second start"; exit 1; }

echo "upgrade check OK"

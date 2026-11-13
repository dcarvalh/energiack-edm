#!/usr/bin/env bash
# End-to-end check of the database stack (compose.yaml), in a throwaway project that is removed at the end:
#   1. the stack starts and reports healthy
#   2. /data.json served from PostgreSQL equals a fresh static build (tools/import_rive_claire.py)
#   3. importing the same dataset again adds 0 rows
#   4. logged-in endpoints refuse anonymous calls and accept a session
# Usage: tools/check_stack.sh [--keep]     (--keep leaves the stack running on http://127.0.0.1:18088/)
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=openedm-check
export POSTGRES_PASSWORD="check-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
export HTTP_BIND=127.0.0.1:18088 HTTPS_BIND=127.0.0.1:18443 SITE_ADDRESS=:80 SEED_DEMO=1
URL=http://127.0.0.1:18088
TMP=$(mktemp -d)
PY=${PYTHON:-python3}
dc() { docker compose --env-file /dev/null "$@"; }
finish() {
  code=$?
  [ $code -ne 0 ] && dc logs --tail 40 seed api web || true
  [ "${1:-}" = "--keep" ] || dc down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit $code
}
trap 'finish "${KEEP:-}"' EXIT
[ "${1:-}" = "--keep" ] && KEEP=--keep

echo "1. start"
dc up -d --build --wait --quiet-pull
curl -fsS "$URL/api/health" | grep -q '"ok":true'
curl -fsS -o /dev/null "$URL/"

echo "2. data.json from the database = static build"
curl -fsS --compressed "$URL/data.json?v=check" -o "$TMP/db.json"
"$PY" tools/import_rive_claire.py --out "$TMP/static.json" >/dev/null
"$PY" - "$TMP/db.json" "$TMP/static.json" <<'EOF'
import json, sys
a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:])
assert a == b, "data.json differs: " + ", ".join(k for k in b if a.get(k) != b[k])
print("   equal:", len(a["sites"]), "sites,", sum(len(m) for m in a["meters"].values()), "meters")
EOF

echo "3. re-import adds nothing"
out=$(dc exec -T api python -m server.cli import)
echo "   $out"
echo "$out" | grep -q "added 0, unchanged 9436, changed 0"
curl -fsS --compressed "$URL/data.json" | cmp -s - "$TMP/db.json" || { echo "data.json changed after re-import"; exit 1; }

echo "4. login"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/imports")" = 401 ]
PW="check-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
echo "$PW" | dc exec -T api python -m server.cli adduser check --role manager --password-stdin >/dev/null
[ "$(curl -s -o /dev/null -w '%{http_code}' -H 'content-type: application/json' -d '{"username":"check","password":"wrong-password"}' "$URL/api/login")" = 401 ]
curl -fsS -c "$TMP/jar" -H 'content-type: application/json' -d "{\"username\":\"check\",\"password\":\"$PW\"}" "$URL/api/login" | grep -q '"role":"manager"'
curl -fsS -b "$TMP/jar" "$URL/api/imports" | grep -q '"added":0'
curl -fsS -b "$TMP/jar" "$URL/api/rejected" | grep -q '"reason":"duplicate"'
curl -fsS -b "$TMP/jar" "$URL/api/readings?meter=S01-EL" | grep -q '"mois":"2021-01"'
curl -fsS -b "$TMP/jar" -X POST "$URL/api/logout" >/dev/null
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$TMP/jar" "$URL/api/me")" = 401 ]

echo "stack check OK"

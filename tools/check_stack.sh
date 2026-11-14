#!/usr/bin/env bash
# End-to-end check of the database stack (compose.yaml), in a throwaway project that is removed at the end:
#   1. the stack starts and reports healthy
#   2. data.json: as technique, equal to a fresh static build (tools/import_rive_claire.py); anonymous, the same without
#      raw readings and the quality report
#   3. importing the same dataset again adds 0 rows
#   4. roles (issue #15): password login, demo logins, what each role is refused, role changes by an admin
# Usage: tools/check_stack.sh [--keep]     (--keep leaves the stack running on http://127.0.0.1:18088/)
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=openedm-check
export POSTGRES_PASSWORD="check-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
export HTTP_BIND=127.0.0.1:18088 HTTPS_BIND=127.0.0.1:18443 SITE_ADDRESS=:80 SEED_DEMO=1 DEMO_LOGIN=1
URL=http://127.0.0.1:18088
TMP=$(mktemp -d)
PY=${PYTHON:-python3}
KEEP=""
[ "${1:-}" = "--keep" ] && KEEP=1
dc() { docker compose --env-file /dev/null "$@"; }
finish() {
  code=$?
  [ $code -ne 0 ] && dc logs --tail 40 seed api web || true
  [ -n "$KEEP" ] || dc down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit $code
}
trap finish EXIT
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }                  # HTTP status only
post() { curl -fsS -H 'content-type: application/json' "$@"; }
as() { local jar="$TMP/$1"; shift; curl -fsS -b "$jar" "$@"; }           # as <jar> URL: request with that session
demo() { post -c "$TMP/$1" -d "{\"role\":\"$1\"}" "$URL/api/demo-login" >/dev/null; }

echo "1. start"
dc down -v --remove-orphans >/dev/null 2>&1 || true     # a stack left by --keep has another password
dc up -d --build --wait --quiet-pull
curl -fsS "$URL/api/health" | grep -q '"ok":true'
curl -fsS "$URL/api/config.json" | grep -q '"server":true,"demo":true'
curl -fsS -o /dev/null "$URL/"

echo "2. data.json: full for technique = static build; anonymous = without raw readings and quality report"
for r in admin technique elu public; do demo $r; done
"$PY" tools/import_rive_claire.py --out "$TMP/static.json" >/dev/null
as technique --compressed "$URL/data.json?v=check" -o "$TMP/full.json"
curl -fsS --compressed "$URL/data.json?v=check" -o "$TMP/anon.json"
as elu --compressed "$URL/data.json?v=check" -o "$TMP/elu.json"
"$PY" - "$TMP" <<'EOF'
import json, sys
p = sys.argv[1] + "/"
full, static, anon, elu = (json.load(open(p + n + ".json", encoding="utf-8")) for n in ("full", "static", "anon", "elu"))
assert full == static, "full data.json differs: " + ", ".join(k for k in static if full.get(k) != static[k])
assert anon["meters"] == {} and anon["quality"] is None, "anonymous data.json has raw readings or the quality report"
assert anon["meta"].pop("restricted") == ["meters", "quality"]
assert {k: v for k, v in anon.items() if k not in ("meters", "quality")} == {k: v for k, v in static.items() if k not in ("meters", "quality")}
assert elu["meters"] == {} and elu["quality"] is None, "elu data.json has raw readings"
print("   full equal:", len(full["sites"]), "sites,", sum(len(m) for m in full["meters"].values()), "meters; anonymous and elu restricted")
EOF

echo "3. re-import adds nothing"
out=$(dc exec -T api python -m server.cli import)
echo "   $out"
echo "$out" | grep -q "added 0, unchanged 9436, changed 0"
as technique --compressed "$URL/data.json" | cmp -s - "$TMP/full.json" || { echo "data.json changed after re-import"; exit 1; }

echo "4. roles"
[ "$(code "$URL/api/imports")" = 401 ]
[ "$(code -b "$TMP/public" "$URL/api/imports")" = 403 ]
[ "$(code -b "$TMP/elu" "$URL/api/rejected")" = 403 ]
[ "$(code -b "$TMP/technique" "$URL/api/users")" = 403 ]
as technique "$URL/api/imports" | grep -q '"added":0'
as technique "$URL/api/rejected" | grep -q '"reason":"duplicate"'
as technique "$URL/api/readings?meter=S01-EL" | grep -q '"mois":"2021-01"'
as elu "$URL/api/me" | grep -q '"role":"elu"'
as admin "$URL/api/users" | grep -q '"username":"a.martin"'
put() { code -b "$TMP/$1" -X PUT -H 'content-type: application/json' -d "{\"role\":\"$3\"}" "$URL/api/users/$2"; }
[ "$(put admin c.rochat technique)" = 200 ]                    # demo admin re-assigns a fictional staff account
[ "$(put admin demo-public admin)" = 403 ]                     # one-click demo accounts keep their role
[ "$(put admin demo-admin public)" = 403 ]                     # nobody changes their own role
[ "$(put technique c.rochat elu)" = 403 ]                      # only admins change roles
[ "$(code -H 'content-type: application/json' -d '{"username":"demo-admin","password":"!"}' "$URL/api/login")" = 401 ]
PW="check-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
echo "$PW" | dc exec -T api python -m server.cli adduser check --role admin --password-stdin >/dev/null
[ "$(code -H 'content-type: application/json' -d '{"username":"check","password":"wrong-password"}' "$URL/api/login")" = 401 ]
post -c "$TMP/real" -d "{\"username\":\"check\",\"password\":\"$PW\"}" "$URL/api/login" | grep -q '"role":"admin"'
[ "$(put admin check public)" = 403 ]                          # a demo admin cannot touch real accounts
[ "$(put real c.rochat elu)" = 200 ]
as real -X POST "$URL/api/logout" >/dev/null
[ "$(as real "$URL/api/me")" = null ]
[ "$(code -b "$TMP/real" "$URL/api/users")" = 401 ]

echo "stack check OK"

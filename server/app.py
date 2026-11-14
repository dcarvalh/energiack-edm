"""openEDM API (FastAPI). Machine-readable description: /api/openapi.json

Public     GET  /api/config.json
           GET  /api/health, GET /api/data.json, POST /api/login, POST /api/logout
           POST /api/demo-login, GET /api/me, GET /api/localities
technique, POST /api/localities/{slug}/import/preview   analyse a ZIP, return detected tables (no DB write)
admin      POST /api/localities/{slug}/import           import ZIP or reload demo data
           GET  /api/localities/{slug}/quality|imports|rejected
           GET  /api/localities/{slug}/data             list tables with row counts
           GET  /api/localities/{slug}/data/{table}     paginated rows (?page=1&per_page=50&q=)
           DELETE /api/localities/{slug}/data/{table}/{key}  delete one row (key = natural id)
           POST /api/localities/{slug}/data/{table}/replace  replace one table with a new CSV
admin      GET  /api/users  PUT /api/users/{username}

Roles: server/auth.py. The web server sends /data.json to /api/data.json.
"""
import hashlib
import json
import os

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from . import auth, store

DEMO = os.environ.get("DEMO_LOGIN", "0") == "1"
app = FastAPI(title="openEDM API", version="2", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
_cache = {}                                            # (locality_id, full): bool -> {run, body, etag}; rebuilt after import


def db():
    with store.connect() as conn:
        yield conn


def current(request: Request, conn=Depends(db)):
    return auth.user_for(conn, request.cookies.get(auth.COOKIE))


def user(u=Depends(current)):
    if not u:
        raise HTTPException(401, "login required")
    return u


def need(*roles):
    def check(u=Depends(user)):
        if u["role"] not in roles:
            raise HTTPException(403, "your role does not give access to this")
        return u
    return check


class Login(BaseModel):
    username: str
    password: str


class Role(BaseModel):
    role: str


class NewLocality(BaseModel):
    slug: str
    name: str
    country: str = "CH"


def _start(request, response, conn, token):
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, token, max_age=auth.HOURS * 3600, httponly=True, samesite="lax", secure=https, path="/")
    return auth.user_for(conn, token)


def _loc(slug, conn, u):
    """Resolve locality by slug; if None, use user's first (or the first in DB for public)."""
    if slug:
        loc = store.locality_by_slug(conn, slug)
        if not loc:
            raise HTTPException(404, "locality not found")
        return loc
    if u:
        locs = store.localities(conn, u)
        if locs:
            return locs[0]
    # Public / unauthenticated: fall back to the first locality in DB
    loc = conn.execute(
        "SELECT id, slug, name, country, map_config FROM locality ORDER BY id LIMIT 1"
    ).fetchone()
    if not loc:
        raise HTTPException(503, "no data loaded yet")
    return loc


def _check_loc_access(loc, u, min_roles=("admin", "manager")):
    """Raise 403 if u doesn't have required role in this locality (platform admin bypasses)."""
    if not u:
        raise HTTPException(401, "login required")
    if u["role"] == "admin":  # platform admin
        return
    # For simplicity in the demo: technique/admin platform role = access to all
    if u["role"] not in ("admin", "technique"):
        raise HTTPException(403, "your role does not give access to this")


@app.get("/api/config.json")
def config():
    # prototype/api/config.json says {"server": false} on a static host; here the API answers instead.
    return {"server": True, "demo": DEMO, "roles": auth.ROLES}


@app.get("/api/health")
def health(conn=Depends(db)):
    r = conn.execute("SELECT id, at, loaded FROM import_run WHERE report IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    n = conn.execute("SELECT count(*) AS n FROM locality").fetchone()["n"]
    return {"ok": True, "last_import": r, "localities": n}


@app.get("/api/localities")
def list_localities(u=Depends(current), conn=Depends(db)):
    if u:
        return store.localities(conn, u)
    # Public: only localities that have imported data, so the default is always usable
    return conn.execute(
        "SELECT l.id, l.slug, l.name, l.country, l.map_config, l.demo, 'viewer' AS role "
        "FROM locality l WHERE EXISTS (SELECT 1 FROM import_run WHERE locality_id = l.id AND report IS NOT NULL) "
        "ORDER BY l.name"
    ).fetchall()


@app.post("/api/localities")
def create_locality(body: NewLocality, u=Depends(need("admin")), conn=Depends(db)):
    return store.create_locality(conn, body.slug, body.name, body.country)


@app.delete("/api/localities/{slug}")
def delete_locality(slug: str, u=Depends(need("admin")), conn=Depends(db)):
    """Delete a locality and all its data (cascade). Admin only. Cannot delete the last locality."""
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    remaining = conn.execute(
        "SELECT count(*) AS n FROM locality WHERE id <> %s", (loc["id"],)).fetchone()["n"]
    if remaining == 0:
        raise HTTPException(422, "cannot delete the last locality")
    conn.execute("DELETE FROM locality WHERE id = %s", (loc["id"],))
    conn.commit()
    _cache.clear()
    return {"deleted": slug}


@app.post("/api/localities/{slug}/import")
async def import_locality(slug: str, file: UploadFile = File(None),
                           u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    if file:
        import csv
        import io
        import zipfile
        content = await file.read()
        z = zipfile.ZipFile(io.BytesIO(content))
        T = {}
        for name in store.rc.TABLES:
            # Accept both generic "{name}.csv" and legacy "rive-claire-{name}.csv"
            matches = [n for n in z.namelist()
                       if n.endswith(f"{name}.csv") or n.endswith(f"rive-claire-{name}.csv")]
            if matches:
                with z.open(matches[0]) as f:
                    T[name] = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"))
            else:
                T[name] = []
        source = f"{slug} (uploaded: {file.filename})"
    elif loc.get("demo"):
        # Bundled demo dataset — only available for municipalities flagged as demo
        T = store.rc.read_guide()
        source = f"{slug} (demo dataset reloaded)"
    else:
        raise HTTPException(422, "A ZIP file is required. Only demo municipalities can use the bundled dataset.")
    result = store.load(conn, T, source, loc["id"])
    _cache.clear()
    return dict(result)


@app.get("/api/localities/{slug}/quality")
def locality_quality(slug: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    run_id = store.last_run(conn, loc["id"])
    if run_id is None:
        raise HTTPException(503, "no data for this locality")
    return conn.execute("SELECT report FROM import_run WHERE id = %s", (run_id,)).fetchone()["report"]


@app.get("/api/localities/{slug}/imports")
def locality_imports(slug: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    return conn.execute(
        "SELECT id, at, source, rows_read, loaded, rejected, added, unchanged, changed "
        "FROM import_run WHERE report IS NOT NULL AND locality_id = %s ORDER BY id DESC LIMIT 100",
        (loc["id"],)).fetchall()


@app.get("/api/localities/{slug}/rejected")
def locality_rejected(slug: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    run_id = store.last_run(conn, loc["id"])
    if run_id is None:
        raise HTTPException(503, "no data for this locality")
    return conn.execute(
        "SELECT pos, reason, row FROM rejected_row WHERE import_id = %s ORDER BY pos",
        (run_id,)).fetchall()


# ── Staging (sas de chargement) ──────────────────────────────────────────────

def _load_csv_detect():
    import sys
    from pathlib import Path
    p = str(Path(__file__).resolve().parent.parent / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import csv_detect
    return csv_detect


@app.post("/api/localities/{slug}/staging")
async def staging_upload(slug: str, file: UploadFile = File(...),
                          u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Upload a ZIP → create a staged import with quality check. No production write."""
    import csv, io, zipfile
    csv_detect = _load_csv_detect()

    loc = _get_loc(slug, conn)
    content = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(422, "not a valid ZIP file")

    sid = store.staging_create(conn, loc["id"], u["id"] if u else None, file.filename)

    unrecognised = []
    for entry in z.namelist():
        if not entry.lower().endswith(".csv") or entry.startswith("__"):
            continue
        with z.open(entry) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";")
            try:
                rows = list(reader)
            except Exception:
                continue
        if not rows:
            continue
        table_name, confidence, _ = csv_detect.detect(list(rows[0].keys()))
        if table_name:
            store.staging_add_file(conn, sid, table_name, entry, confidence, rows)
        else:
            unrecognised.append({"filename": entry, "rows": len(rows)})

    conn.commit()
    # Run quality check immediately
    try:
        report, _ = store.staging_check(conn, sid, loc["id"])
        quality_summary = {
            "loaded": report.get("loaded"), "rejected": report.get("rejected"),
            "flagged": report.get("flagged"), "excluded": report.get("excluded"),
        }
    except Exception:
        quality_summary = None

    files = store.staging_files(conn, sid)
    return {
        "staging_id": sid,
        "files": [dict(f) for f in files],
        "unrecognised": unrecognised,
        "quality": quality_summary,
    }


@app.get("/api/localities/{slug}/staging")
def staging_list(slug: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = _get_loc(slug, conn)
    return store.staging_list(conn, loc["id"])


@app.get("/api/localities/{slug}/staging/{staging_id}")
def staging_detail(slug: str, staging_id: int, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = _get_loc(slug, conn)
    si = store.staging_get(conn, staging_id, loc["id"])
    if not si:
        raise HTTPException(404, "staging import not found")
    files = store.staging_files(conn, staging_id)
    return {**dict(si), "files": [dict(f) for f in files]}


@app.get("/api/localities/{slug}/staging/{staging_id}/files/{table}")
def staging_rows(slug: str, staging_id: int, table: str,
                 page: int = 1, per_page: int = 50,
                 u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = _get_loc(slug, conn)
    if not store.staging_get(conn, staging_id, loc["id"]):
        raise HTTPException(404, "staging import not found")
    return store.staging_rows(conn, staging_id, table, page, min(per_page, 200))


@app.get("/api/localities/{slug}/staging/{staging_id}/files/{table}/anomalies")
def staging_anomalies(slug: str, staging_id: int, table: str,
                       u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Return only the rows that have quality issues for this table (with their original row index)."""
    loc = _get_loc(slug, conn)
    si = store.staging_get(conn, staging_id, loc["id"])
    if not si:
        raise HTTPException(404, "staging import not found")

    quality = si.get("quality") or {}
    checks = quality.get("checks", [])

    # Build set of anomalous keys for this table
    anomalous = set()
    for ch in checks:
        for it in ch.get("items", []):
            if table == "mesures" and it.get("m") and it.get("mo"):
                anomalous.add((it["m"], it["mo"]))
            elif it.get("m") and not it.get("mo"):
                anomalous.add(it["m"])

    if not anomalous:
        return {"total": 0, "rows": []}

    # Scan ALL staged rows for this table and return matching ones with their index
    all_rows = store.staging_rows(conn, staging_id, table, 1, 20000)["rows"]
    result = []
    for idx, row in enumerate(all_rows):
        if table == "mesures":
            key = (row.get("id_compteur", ""), row.get("mois", ""))
        else:
            key = row.get("id_batiment") or row.get("id_compteur") or row.get("id_installation") or row.get("id_site", "")
        if key in anomalous:
            result.append({"_row_idx": idx, **row})

    return {"total": len(result), "rows": result}


@app.put("/api/localities/{slug}/staging/{staging_id}/files/{table}/{row_idx}")
def staging_update_row(slug: str, staging_id: int, table: str, row_idx: int,
                        body: dict, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = _get_loc(slug, conn)
    if not store.staging_get(conn, staging_id, loc["id"]):
        raise HTTPException(404, "staging import not found")
    store.staging_update_row(conn, staging_id, table, row_idx, body)
    return {"updated": row_idx}


@app.delete("/api/localities/{slug}/staging/{staging_id}/files/{table}/{row_idx}")
def staging_delete_row(slug: str, staging_id: int, table: str, row_idx: int,
                        u=Depends(need(*auth.FULL)), conn=Depends(db)):
    loc = _get_loc(slug, conn)
    if not store.staging_get(conn, staging_id, loc["id"]):
        raise HTTPException(404, "staging import not found")
    store.staging_delete_row(conn, staging_id, table, row_idx)
    return {"deleted": row_idx}


@app.post("/api/localities/{slug}/staging/{staging_id}/check")
def staging_check(slug: str, staging_id: int, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Re-run quality checks on the staged data."""
    loc = _get_loc(slug, conn)
    if not store.staging_get(conn, staging_id, loc["id"]):
        raise HTTPException(404, "staging import not found")
    report, _ = store.staging_check(conn, staging_id, loc["id"])
    return report


@app.post("/api/localities/{slug}/staging/{staging_id}/commit")
def staging_commit(slug: str, staging_id: int, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Move staged data to production. Invalidates data cache."""
    loc = _get_loc(slug, conn)
    try:
        result = store.staging_commit(conn, staging_id, loc["id"])
    except (LookupError, ValueError) as e:
        raise HTTPException(422, str(e))
    _cache.clear()
    return dict(result)


@app.delete("/api/localities/{slug}/staging/{staging_id}")
def staging_discard(slug: str, staging_id: int, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Discard a staged import without touching production."""
    loc = _get_loc(slug, conn)
    store.staging_discard(conn, staging_id, loc["id"])
    return {"discarded": staging_id}


# ── Import preview (no DB write) ─────────────────────────────────────────────

@app.post("/api/localities/{slug}/import/preview")
async def preview_import(slug: str, file: UploadFile = File(...),
                          u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Analyse a ZIP without writing to the DB. Returns detected tables + per-file stats."""
    import csv, io, zipfile, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import csv_detect

    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")

    content = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(422, "not a valid ZIP file")

    files_info, detected = [], {}
    for entry in z.namelist():
        if not entry.lower().endswith(".csv") or entry.startswith("__"):
            continue
        with z.open(entry) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";")
            try:
                rows = list(reader)
            except Exception:
                files_info.append({"filename": entry, "detected_as": None, "confidence": 0,
                                    "columns": [], "row_count": 0, "sample": [], "error": "parse error"})
                continue
        if not rows:
            continue
        columns = list(rows[0].keys())
        table, confidence, label = csv_detect.detect(columns)
        files_info.append({
            "filename": entry,
            "detected_as": table,
            "label": label,
            "confidence": confidence,
            "columns": columns,
            "row_count": len(rows),
            "sample": [{k: v for k, v in r.items()} for r in rows[:3]],
        })
        if table and table not in detected:
            detected[table] = True

    core = {"batiments", "installations", "compteurs", "mesures"}
    missing = [t for t in store.rc.TABLES if t not in detected]
    missing_core = [t for t in core if t not in detected]

    return {
        "files": files_info,
        "detected": sorted(detected.keys()),
        "missing": missing,
        "ready": len(missing_core) == 0,
    }


# ── Per-table data access ─────────────────────────────────────────────────────

_DATA_TABLES = {
    "batiments":     ("building",      "id_batiment",      "pos"),
    "installations": ("installation",  "id_installation",  "pos"),
    "compteurs":     ("meter",         "id_compteur",      "pos"),
    "mesures":       ("reading",       None,               "mois"),   # composite PK
}


def _get_loc(slug, conn):
    loc = store.locality_by_slug(conn, slug)
    if not loc:
        raise HTTPException(404, "locality not found")
    return loc


@app.get("/api/localities/{slug}/data")
def locality_data_tables(slug: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """List data tables loaded for this locality with row counts."""
    loc = _get_loc(slug, conn)
    lid = loc["id"]
    result = []
    for api_name, (db_table, _, _ord) in _DATA_TABLES.items():
        n = conn.execute(f"SELECT count(*) AS n FROM {db_table} WHERE locality_id=%s", (lid,)).fetchone()["n"]
        result.append({"name": api_name, "rows": n})
    for ref_name in store.LOOKUPS:
        n = conn.execute("SELECT count(*) AS n FROM reference WHERE locality_id=%s AND name=%s",
                         (lid, ref_name)).fetchone()["n"]
        result.append({"name": ref_name, "rows": n})
    return result


@app.get("/api/localities/{slug}/data/{table}")
def locality_data_rows(slug: str, table: str, page: int = 1, per_page: int = 50,
                        q: str = None, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Paginated rows for a data table. q= filters any text column (ILIKE)."""
    loc = _get_loc(slug, conn)
    lid = loc["id"]
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page

    if table in _DATA_TABLES:
        db_table, pk, order_col = _DATA_TABLES[table]
        where = "WHERE locality_id=%s"
        params: list = [lid]
        if q:
            where += " AND (locality_id::text || ' ' || " + db_table + ".*::text) ILIKE %s"
            params.append(f"%{q}%")
        total = conn.execute(f"SELECT count(*) AS n FROM {db_table} {where}", params).fetchone()["n"]
        rows = conn.execute(f"SELECT * FROM {db_table} {where} ORDER BY {order_col} LIMIT %s OFFSET %s",
                            params + [per_page, offset]).fetchall()
        return {"total": total, "page": page, "per_page": per_page, "rows": rows}

    if table in store.LOOKUPS:
        total = conn.execute("SELECT count(*) AS n FROM reference WHERE locality_id=%s AND name=%s",
                             (lid, table)).fetchone()["n"]
        raw = conn.execute("SELECT pos, row FROM reference WHERE locality_id=%s AND name=%s "
                           "ORDER BY pos LIMIT %s OFFSET %s", (lid, table, per_page, offset)).fetchall()
        rows = [{"pos": r["pos"], **r["row"]} for r in raw]
        return {"total": total, "page": page, "per_page": per_page, "rows": rows}

    raise HTTPException(404, f"unknown table '{table}'")


@app.delete("/api/localities/{slug}/data/{table}/{key}")
def delete_data_row(slug: str, table: str, key: str,
                    u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Delete one row. key = natural id (id_batiment, id_compteur, etc.) or 'meter:mois' for mesures."""
    loc = _get_loc(slug, conn)
    lid = loc["id"]
    if table not in _DATA_TABLES:
        raise HTTPException(404, f"unknown table '{table}'")
    db_table, pk, _ = _DATA_TABLES[table]
    if table == "mesures":
        # key format: "S01-EL:2024-01"
        parts = key.split(":", 1)
        if len(parts) != 2:
            raise HTTPException(422, "mesures key must be 'id_compteur:mois'")
        conn.execute(f"DELETE FROM {db_table} WHERE locality_id=%s AND id_compteur=%s AND mois=%s",
                     (lid, parts[0], parts[1]))
    else:
        conn.execute(f"DELETE FROM {db_table} WHERE locality_id=%s AND {pk}=%s", (lid, key))
    conn.commit()
    _cache.clear()
    return {"deleted": key}


@app.post("/api/localities/{slug}/data/{table}/replace")
async def replace_table(slug: str, table: str, file: UploadFile = File(...),
                         u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Replace one table's data for this locality with a new CSV file."""
    import csv, io, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import csv_detect

    loc = _get_loc(slug, conn)
    lid = loc["id"]
    content = await file.read()
    reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig"), delimiter=";")
    rows = list(reader)
    if not rows:
        raise HTTPException(422, "empty CSV")
    detected, confidence, _ = csv_detect.detect(list(rows[0].keys()))
    if detected != table:
        raise HTTPException(422, f"CSV detected as '{detected}' (confidence {confidence:.0%}), not '{table}'")

    if table in _DATA_TABLES:
        db_table, pk, _ = _DATA_TABLES[table]
        conn.execute(f"DELETE FROM {db_table} WHERE locality_id=%s", (lid,))
        store._upsert_table(conn, table, rows, lid)
    elif table in store.LOOKUPS:
        from psycopg.types.json import Jsonb
        conn.execute("DELETE FROM reference WHERE locality_id=%s AND name=%s", (lid, table))
        conn.executemany("INSERT INTO reference (locality_id, name, pos, row) VALUES (%s,%s,%s,%s)",
                         [(lid, table, n, Jsonb(r)) for n, r in enumerate(rows)])
    else:
        raise HTTPException(404, f"unknown table '{table}'")

    conn.commit()
    _cache.clear()
    return {"replaced": table, "rows": len(rows)}


@app.get("/api/data.json")
def data(request: Request, locality: str = None, u=Depends(current), conn=Depends(db)):
    loc = _loc(locality, conn, u)
    run = store.last_run(conn, loc["id"])
    if run is None:
        raise HTTPException(503, "no data imported yet")
    full = bool(u) and u["role"] in auth.FULL
    cache_key = (loc["id"], full)
    c = _cache.get(cache_key)
    if not c or c["run"] != run:
        d = store.dataset(conn, loc["id"])
        if not full:
            d["meters"], d["quality"] = {}, None
            d["meta"]["restricted"] = ["meters", "quality"]
        body = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()
        c = _cache[cache_key] = {"run": run, "body": body, "etag": '"%s"' % hashlib.sha256(body).hexdigest()[:16]}
    headers = {"ETag": c["etag"], "Cache-Control": "private, no-cache", "Vary": "Cookie"}
    if request.headers.get("if-none-match") == c["etag"]:
        return Response(status_code=304, headers=headers)
    return Response(c["body"], media_type="application/json", headers=headers)


@app.post("/api/login")
def login(body: Login, request: Request, response: Response, conn=Depends(db)):
    token = auth.login(conn, body.username, body.password)
    if not token:
        raise HTTPException(401, "wrong username or password, or account locked for a few minutes")
    return _start(request, response, conn, token)


@app.post("/api/demo-login")
def demo_login(body: Role, request: Request, response: Response, conn=Depends(db)):
    if not DEMO:
        raise HTTPException(404, "demo logins are off on this server")
    token = auth.demo_login(conn, body.role)
    if not token:
        raise HTTPException(400, "unknown role")
    return _start(request, response, conn, token)


@app.post("/api/logout")
def logout(request: Request, response: Response, conn=Depends(db)):
    auth.logout(conn, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(u=Depends(current)):
    return u                                           # null when not logged in (no 401: the app asks on every load)


@app.post("/api/import")
def trigger_import(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Re-run the bundled Rive-Claire import (backward compat: uses the user's first locality)."""
    loc = _loc(None, conn, u)
    result = store.reimport_bundled(conn, loc["id"])
    _cache.clear()
    return dict(result)


@app.get("/api/quality")
def quality_report(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Full quality report from the last import (backward compat: uses the user's first locality)."""
    loc = _loc(None, conn, u)
    run_id = store.last_run(conn, loc["id"])
    if run_id is None:
        raise HTTPException(503, "no data imported yet")
    return conn.execute("SELECT report FROM import_run WHERE id = %s", (run_id,)).fetchone()["report"]


@app.get("/api/imports")
def imports(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Import history (backward compat: uses the user's first locality)."""
    loc = _loc(None, conn, u)
    return conn.execute(
        "SELECT id, at, source, rows_read, loaded, rejected, added, unchanged, changed FROM import_run "
        "WHERE report IS NOT NULL AND locality_id = %s ORDER BY id DESC LIMIT 100",
        (loc["id"],)).fetchall()


@app.get("/api/rejected")
def rejected(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    """Rejected rows from the last import (backward compat: uses the user's first locality)."""
    loc = _loc(None, conn, u)
    run_id = store.last_run(conn, loc["id"])
    return conn.execute("SELECT pos, reason, row FROM rejected_row WHERE import_id = %s ORDER BY pos",
                        (run_id,)).fetchall()


@app.get("/api/readings")
def readings(meter: str, u=Depends(need(*auth.FULL)), conn=Depends(db)):
    return conn.execute("SELECT mois, valeur, unite, energie_kwh, qualite FROM reading WHERE id_compteur = %s ORDER BY mois",
                        (meter,)).fetchall()


@app.get("/api/users")
def users(u=Depends(need("admin")), conn=Depends(db)):
    return auth.users(conn)


@app.put("/api/users/{username}")
def set_role(username: str, body: Role, u=Depends(need("admin")), conn=Depends(db)):
    try:
        auth.set_role(conn, u, username, body.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"username": username, "role": body.role}

"""Storage: the dataset in PostgreSQL.

load()     one import, in one transaction: reference tables and accepted readings are upserted on their natural keys
           (re-importing the same file adds 0 rows), rejected rows are kept apart with the check that refused them.
dataset()  the same dict as prototype/data.json, rebuilt from the database with the importer's own build().

Connection settings come from the standard PG* environment variables (PGHOST, PGUSER, PGPASSWORD, PGDATABASE).
"""
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_rive_claire as rc  # noqa: E402  (build(), check(), read_guide(): shared with the static build)

# dataset table -> (database table, key, columns in the source order)
REF = {
    "batiments": ("building", "id_batiment", [
        "id_batiment", "id_site", "nom_site", "quartier", "typologie", "nom_batiment", "annee_construction",
        "annee_renovation", "sre_m2", "niveaux", "label", "logements", "ouverture", "x_km", "y_km", "remarque"]),
    "installations": ("installation", "id_installation", [
        "id_installation", "id_site", "type", "libelle", "vecteur", "puissance_kw", "mise_en_service", "retrait", "remarque"]),
    "compteurs": ("meter", "id_compteur", [
        "id_compteur", "id_site", "libelle", "fluide", "unite", "niveau", "mesure", "parent", "fournisseur_donnee",
        "releve", "debut", "fin"]),
}
READING = ["mois", "id_compteur", "id_site", "fluide", "mesure", "valeur", "unite", "energie_kwh", "qualite"]
LOOKUPS = [t for t in rc.TABLES if t.startswith("ref-")]

null = lambda s: None if s in (None, "") else s        # empty cell -> NULL
text = lambda v: "" if v is None else str(v)           # and back: rows come out as csv.DictReader gave them


def connect():
    return psycopg.connect("", row_factory=dict_row)


def init(conn):
    conn.execute((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    conn.commit()


# --- locality helpers ---

def localities(conn, user=None):
    """List localities accessible to user. Platform admin sees all."""
    if user and user["role"] == "admin":
        return conn.execute(
            "SELECT l.id, l.slug, l.name, l.country, l.map_config, l.demo, 'admin' AS role "
            "FROM locality l ORDER BY l.name").fetchall()
    if user:
        return conn.execute(
            "SELECT l.id, l.slug, l.name, l.country, l.map_config, l.demo, ul.role "
            "FROM locality l JOIN user_locality ul ON l.id = ul.locality_id "
            "WHERE ul.user_id = %s ORDER BY l.name", (user["id"],)).fetchall()
    return []


def locality_by_slug(conn, slug):
    return conn.execute(
        "SELECT id, slug, name, country, map_config, demo FROM locality WHERE slug = %s",
        (slug,)).fetchone()


def create_locality(conn, slug, name, country="CH"):
    loc = conn.execute(
        "INSERT INTO locality (slug, name, country) VALUES (%s, %s, %s) "
        "RETURNING id, slug, name, country", (slug, name, country)).fetchone()
    # Grant all existing users access (admins=admin, technique=manager, others=viewer)
    conn.execute(
        "INSERT INTO user_locality (user_id, locality_id, role) "
        "SELECT id, %s, CASE role WHEN 'admin' THEN 'admin' WHEN 'technique' THEN 'manager' ELSE 'viewer' END "
        "FROM app_user ON CONFLICT DO NOTHING",
        (loc["id"],))
    conn.commit()
    return loc


def grant_access(conn, user_id, locality_id, role="viewer"):
    conn.execute(
        "INSERT INTO user_locality (user_id, locality_id, role) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, locality_id) DO UPDATE SET role = EXCLUDED.role",
        (user_id, locality_id, role))
    conn.commit()


def last_run(conn, locality_id=None):
    if locality_id is not None:
        return conn.execute(
            "SELECT max(id) AS id FROM import_run WHERE report IS NOT NULL AND locality_id = %s",
            (locality_id,)).fetchone()["id"]
    return conn.execute(
        "SELECT max(id) AS id FROM import_run WHERE report IS NOT NULL").fetchone()["id"]


def _upsert(cur, table, key, cols, rows):
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
    cur.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {sets}", rows)


def load(conn, T, source, locality_id):
    """Import the tables T ({name: [row dicts]}). Returns the import_run row. All or nothing."""
    report, rej = rc.check(T)
    why = {}                                           # (meter, month) -> check that rejected the row
    for ch in report["checks"]:
        if ch["kind"] == "rejected":
            for it in ch["items"]:
                why.setdefault((it.get("m"), it.get("mo")), ch["code"])
    with conn.transaction(), conn.cursor() as cur:
        run = cur.execute(
            "INSERT INTO import_run (source, locality_id) VALUES (%s, %s) RETURNING id",
            (source, locality_id)).fetchone()["id"]
        for name, (table, key, cols) in REF.items():
            _upsert(cur, table, ["locality_id", key], cols + ["pos", "locality_id"],
                    [[null(r.get(c)) for c in cols] + [n, locality_id] for n, r in enumerate(T[name])])
        cur.execute("DELETE FROM reference WHERE name = ANY(%s) AND locality_id = %s", (LOOKUPS, locality_id))
        cur.executemany("INSERT INTO reference (name, pos, row, locality_id) VALUES (%s, %s, %s, %s)",
                        [(name, n, Jsonb(r), locality_id) for name in LOOKUPS for n, r in enumerate(T[name])])

        have = {(r["id_compteur"], r["mois"]): (text(r["valeur"]), text(r["energie_kwh"]), text(r["qualite"]))
                for r in cur.execute(
                    "SELECT id_compteur, mois, valeur, energie_kwh, qualite FROM reading WHERE locality_id = %s",
                    (locality_id,)).fetchall()}
        added = same = changed = 0
        rows, refused = [], []
        for n, r in enumerate(T["mesures"]):
            if n in rej:
                k = (r.get("id_compteur"), r.get("mois"))
                refused.append((run, n, why.get(k) or why.get((k[0], None)) or "rejected", Jsonb(r)))
                continue
            k, v = (r["id_compteur"], r["mois"]), (r["valeur"], r["energie_kwh"], r["qualite"])
            if k not in have:
                added += 1
            elif have[k] == v:
                same += 1
            else:
                changed += 1
            rows.append([null(r.get(c)) for c in READING] + [run, n, locality_id])
        _upsert(cur, "reading", ["locality_id", "id_compteur", "mois"], READING + ["import_id", "pos", "locality_id"], rows)
        cur.executemany(
            "INSERT INTO rejected_row (import_id, pos, reason, row) VALUES (%s, %s, %s, %s)",
            refused)
        return cur.execute(
            "UPDATE import_run SET rows_read = %s, loaded = %s, rejected = %s, added = %s, unchanged = %s, changed = %s, "
            "report = %s WHERE id = %s RETURNING id, at, source, rows_read, loaded, rejected, added, unchanged, changed",
            (len(T["mesures"]), len(rows), len(refused), added, same, changed, Jsonb(report), run)).fetchone()


def tables(conn, locality_id):
    """The database content in the shape the importer reads: (T, quality report, rejected row indexes)."""
    run = last_run(conn, locality_id)
    T = {}
    for name, (table, _, cols) in REF.items():
        T[name] = [{c: text(r[c]) for c in cols}
                   for r in conn.execute(
                       f"SELECT * FROM {table} WHERE locality_id = %s ORDER BY pos",
                       (locality_id,)).fetchall()]
    for name in LOOKUPS:
        T[name] = [r["row"] for r in conn.execute(
            "SELECT row FROM reference WHERE name = %s AND locality_id = %s ORDER BY pos",
            (name, locality_id)).fetchall()]
    mes = [((r["import_id"], r["pos"]), {c: text(r[c]) for c in READING}, False)
           for r in conn.execute(
               "SELECT * FROM reading WHERE locality_id = %s", (locality_id,)).fetchall()]
    mes += [((run, r["pos"]), r["row"], True)
            for r in conn.execute(
                "SELECT pos, row FROM rejected_row WHERE import_id = %s", (run,)).fetchall()]
    mes.sort(key=lambda x: x[0])                       # file order: the importer keeps the first of two duplicates
    T["mesures"] = [m[1] for m in mes]
    report = conn.execute("SELECT report FROM import_run WHERE id = %s", (run,)).fetchone()["report"]
    return T, report, {n for n, m in enumerate(mes) if m[2]}


def dataset(conn, locality_id):
    return rc.build(*tables(conn, locality_id))


# ── staging (sas de chargement) ───────────────────────────────────────────────

def staging_create(conn, locality_id, user_id, source):
    sid = conn.execute(
        "INSERT INTO staged_import (locality_id, uploaded_by, source) VALUES (%s,%s,%s) RETURNING id",
        (locality_id, user_id, source)).fetchone()["id"]
    conn.commit()
    return sid


def staging_add_file(conn, staging_id, table_name, filename, confidence, rows):
    conn.execute(
        "INSERT INTO staged_file (staged_import_id, table_name, filename, confidence, row_count, rows) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (staged_import_id, table_name) DO UPDATE "
        "SET filename=EXCLUDED.filename, confidence=EXCLUDED.confidence, "
        "    row_count=EXCLUDED.row_count, rows=EXCLUDED.rows",
        (staging_id, table_name, filename, confidence, len(rows), Jsonb(rows)))


def staging_list(conn, locality_id):
    return conn.execute(
        "SELECT si.id, si.uploaded_at, si.source, si.status, si.quality, "
        "       (SELECT count(*) FROM staged_file WHERE staged_import_id=si.id) AS files "
        "FROM staged_import si WHERE si.locality_id=%s ORDER BY si.uploaded_at DESC LIMIT 20",
        (locality_id,)).fetchall()


def staging_get(conn, staging_id, locality_id):
    return conn.execute(
        "SELECT id, locality_id, uploaded_at, uploaded_by, source, status, quality "
        "FROM staged_import WHERE id=%s AND locality_id=%s",
        (staging_id, locality_id)).fetchone()


def staging_files(conn, staging_id):
    return conn.execute(
        "SELECT id, table_name, filename, confidence, row_count "
        "FROM staged_file WHERE staged_import_id=%s ORDER BY table_name",
        (staging_id,)).fetchall()


def staging_rows(conn, staging_id, table_name, page=1, per_page=50):
    r = conn.execute(
        "SELECT row_count, rows FROM staged_file WHERE staged_import_id=%s AND table_name=%s",
        (staging_id, table_name)).fetchone()
    if not r:
        return {"total": 0, "page": page, "per_page": per_page, "rows": []}
    offset = (page - 1) * per_page
    all_rows = r["rows"]   # list from JSONB
    return {"total": r["row_count"], "page": page, "per_page": per_page,
            "rows": all_rows[offset: offset + per_page]}


def staging_update_row(conn, staging_id, table_name, row_idx, row_data):
    conn.execute(
        "UPDATE staged_file SET rows=jsonb_set(rows, %s::text[], %s::jsonb) "
        "WHERE staged_import_id=%s AND table_name=%s",
        ([str(row_idx)], Jsonb(row_data), staging_id, table_name))
    conn.commit()


def staging_delete_row(conn, staging_id, table_name, row_idx):
    conn.execute(
        "UPDATE staged_file "
        "SET rows = rows - %s::int, row_count = row_count - 1 "
        "WHERE staged_import_id=%s AND table_name=%s",
        (row_idx, staging_id, table_name))
    conn.commit()


def _staging_to_T(conn, staging_id):
    """Build the T dict (table_name → [row dicts]) from staged files."""
    T = {name: [] for name in rc.TABLES}
    for f in staging_files(conn, staging_id):
        rows_raw = conn.execute(
            "SELECT rows FROM staged_file WHERE staged_import_id=%s AND table_name=%s",
            (staging_id, f["table_name"])).fetchone()
        if rows_raw:
            T[f["table_name"]] = rows_raw["rows"]
    return T


def staging_check(conn, staging_id, locality_id):
    """Run rc_quality on the staged data and persist the report. Returns (report, rejected_set)."""
    T = _staging_to_T(conn, staging_id)
    report, rej = rc.check(T)
    conn.execute(
        "UPDATE staged_import SET quality=%s WHERE id=%s AND locality_id=%s",
        (Jsonb(report), staging_id, locality_id))
    conn.commit()
    return report, rej


def staging_commit(conn, staging_id, locality_id):
    """Move staged data to production tables. Returns import_run row."""
    si = staging_get(conn, staging_id, locality_id)
    if not si:
        raise LookupError("staging import not found")
    if si["status"] != "pending":
        raise ValueError(f"cannot commit: status is '{si['status']}'")
    T = _staging_to_T(conn, staging_id)
    result = load(conn, T, f"{si['source']} (committed from staging #{staging_id})", locality_id)
    conn.execute("UPDATE staged_import SET status='committed' WHERE id=%s", (staging_id,))
    conn.commit()
    return result


def staging_discard(conn, staging_id, locality_id):
    """Discard a staged import without touching production."""
    conn.execute(
        "UPDATE staged_import SET status='discarded' WHERE id=%s AND locality_id=%s",
        (staging_id, locality_id))
    conn.commit()


def _upsert_table(conn, table_name, rows, locality_id):
    """Upsert a single reference table (batiments/installations/compteurs) for a locality."""
    if table_name not in REF:
        return
    db_table, key, cols = REF[table_name]
    with conn.cursor() as cur:
        _upsert(cur, db_table, ["locality_id", key], cols + ["pos", "locality_id"],
                [[null(r.get(c)) for c in cols] + [n, locality_id] for n, r in enumerate(rows)])


def reimport_bundled(conn, locality_id):
    """Re-run the bundled Rive-Claire import from the guide file. Returns the import_run row dict."""
    T = rc.read_guide()
    return load(conn, T, "rive-claire (bundled guide, re-imported via API)", locality_id)

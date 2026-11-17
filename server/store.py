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
import fetch_swiss_map as geomap  # noqa: E402  (fetch(), geocode(): the national Swiss geo platform)
import fetch_france_map as geomap_fr  # noqa: E402  (fetch(): the IGN Géoplateforme, for French zones)

# dataset table -> (database table, key, columns in the source order)
REF = {
    "batiments": ("building", "id_batiment", [
        "id_batiment", "id_site", "nom_site", "quartier", "typologie", "nom_batiment", "annee_construction",
        "annee_renovation", "sre_m2", "niveaux", "label", "logements", "ouverture", "x_km", "y_km", "remarque", "egid"]),  # egid: optional, the public building id
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


# --- admin settings (map import preferences) ---

SETTINGS_DEFAULTS = {"osm_footprints": True, "country_ch": True, "country_fr": False}


def get_settings(conn):
    """All admin settings, with defaults filled in."""
    out = dict(SETTINGS_DEFAULTS)
    for r in conn.execute("SELECT key, value FROM setting").fetchall():
        out[r["key"]] = r["value"]
    return out


def set_settings(conn, updates):
    """Upsert the given settings (only known keys)."""
    with conn.cursor() as cur:
        for k, v in updates.items():
            if k in SETTINGS_DEFAULTS:
                cur.execute("INSERT INTO setting (key, value) VALUES (%s, %s) "
                            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (k, Jsonb(v)))
    conn.commit()
    return get_settings(conn)


# --- locality helpers ---

def localities(conn, user=None):
    """List localities accessible to user. Platform admin sees all."""
    if user and user["role"] == "admin":
        return conn.execute(
            "SELECT l.id, l.slug, l.name, l.country, l.map_config, l.demo, l.simulated, 'admin' AS role "
            "FROM locality l ORDER BY l.id").fetchall()
    if user:
        return conn.execute(
            "SELECT l.id, l.slug, l.name, l.country, l.map_config, l.demo, l.simulated, ul.role "
            "FROM locality l JOIN user_locality ul ON l.id = ul.locality_id "
            "WHERE ul.user_id = %s ORDER BY l.id", (user["id"],)).fetchall()
    return []


def locality_by_slug(conn, slug):
    return conn.execute(
        "SELECT id, slug, name, country, map_config, demo, simulated FROM locality WHERE slug = %s",
        (slug,)).fetchone()


# The 3D maps this server ships (folders under prototype/). A municipality points to one, or to none.
MAPS = {"rc": {"key": "rc", "dir": "map-rc/"}, "ge": {"key": "ge", "dir": "map/"}}


def create_locality(conn, slug, name, country="CH", map_key=None):
    mc = Jsonb(MAPS[map_key]) if map_key else None
    loc = conn.execute(
        "INSERT INTO locality (slug, name, country, map_config) VALUES (%s, %s, %s, %s) "
        "RETURNING id, slug, name, country, map_config", (slug, name, country, mc)).fetchone()
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


def load(conn, T, source, locality_id, replace=False):
    """Import the tables T ({name: [row dicts]}). Returns the import_run row. All or nothing.
    replace: first remove the locality's sites, meters and readings (a regenerated, fully simulated dataset whose
    sites may differ from the stored ones); added/unchanged/changed still compare with what was stored."""
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
        have = {(r["id_compteur"], r["mois"]): (text(r["valeur"]), text(r["energie_kwh"]), text(r["qualite"]))
                for r in cur.execute(
                    "SELECT id_compteur, mois, valeur, energie_kwh, qualite FROM reading WHERE locality_id = %s",
                    (locality_id,)).fetchall()}
        if replace:
            for table in ("reading", "meter", "installation", "building"):
                cur.execute(f"DELETE FROM {table} WHERE locality_id = %s", (locality_id,))
        for name, (table, key, cols) in REF.items():
            _upsert(cur, table, ["locality_id", key], cols + ["pos", "locality_id"],
                    [[null(r.get(c)) for c in cols] + [n, locality_id] for n, r in enumerate(T[name])])
        cur.execute("DELETE FROM reference WHERE name = ANY(%s) AND locality_id = %s", (LOOKUPS, locality_id))
        cur.executemany("INSERT INTO reference (name, pos, row, locality_id) VALUES (%s, %s, %s, %s)",
                        [(name, n, Jsonb(r), locality_id) for name in LOOKUPS for n, r in enumerate(T[name])])

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


def dataset(conn, locality_id, slug=None):
    return rc.build(*tables(conn, locality_id), slug)


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


# ── imported 3D map (Swiss geo platform / France IGN) ─────────────────────────

def map_import(conn, locality_id, bbox, step=16, px=1.0, tiles=1, name=None, progress=None, osm=True, country="CH"):
    """Fetch a zone from the national platform for `country` (CH: geo.admin.ch, FR: IGN), store it (replacing any
    existing map), auto-match, return a summary. progress(pct, step) runs through the fetch and the save."""
    src = geomap_fr if (country or "CH").upper() == "FR" else geomap
    result = src.fetch(bbox, step=step, px=px, tiles=tiles, name=name, progress=progress, osm=osm)
    if progress:
        progress(97, "save")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM map_import WHERE locality_id = %s", (locality_id,))
        mid = cur.execute(
            "INSERT INTO map_import (locality_id, bbox, meta, terrain, n_buildings) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (locality_id, ",".join(f"{v:.0f}" for v in bbox), Jsonb(result["meta"]),
             result["terrain"], len(result["buildings"]))).fetchone()["id"]
        cur.executemany(
            "INSERT INTO map_building (map_import_id, egid, rings, h, z, attrs) VALUES (%s,%s,%s,%s,%s,%s)",
            [(mid, b["egid"], Jsonb(b["rings"]), b["h"], b["z"],
              Jsonb({"use": b["use"], "year": b["year"], "levels": b["levels"], "addr": b["addr"]}))
             for b in result["buildings"]])
        cur.executemany(
            "INSERT INTO map_tile (map_import_id, i, j, jpg) VALUES (%s,%s,%s,%s)",
            [(mid, i, j, jpg) for i, j, jpg in result["tiles"]])
    if progress:
        progress(99, "match")
    matched = map_automatch(conn, locality_id)
    n = len(result["buildings"])
    return {"n": n, "matched": matched, "unmatched": n - matched, "bbox": bbox}


def _ring_centroid_area(ring):
    """Centroid (x, y) and |area| of a map-local ring (last point == first)."""
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cr = x0 * y1 - x1 * y0
        a += cr; cx += (x0 + x1) * cr; cy += (y0 + y1) * cr
    if a == 0:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    a *= 0.5
    return cx / (6 * a), cy / (6 * a), abs(a)


def map_enhance_footprints(conn, locality_id, progress=None):
    """Background pass (after a fast square-block import): fetch real OSM footprints and replace each block's shape
    in place, BIGGEST building first so the most visible blocks get their true shape first. Swiss zones only
    (France already imports real BD TOPO footprints). Returns the number of blocks given a real footprint."""
    mi = conn.execute("SELECT id, meta, bbox FROM map_import WHERE locality_id = %s", (locality_id,)).fetchone()
    if not mi or (mi["meta"].get("crs") != "EPSG:2056"):
        return 0
    xmin, ymin = mi["meta"]["origin"]
    bbox = tuple(float(v) for v in mi["bbox"].split(","))
    rows = conn.execute("SELECT id, rings FROM map_building WHERE map_import_id = %s", (mi["id"],)).fetchall()
    items = []                                                # (area, id, E, N) in LV95, biggest first
    for r in rows:
        cx, cy, area = _ring_centroid_area(r["rings"][0])
        items.append((area, r["id"], xmin + cx, ymin + cy))
    items.sort(reverse=True)

    find, nf = geomap._osm_footprints(bbox)                   # cached per 1 km cell; find(E,N) -> LV95 ring | None
    if not nf:
        return 0
    updated, batch = 0, []
    for k, (area, bid, e, n) in enumerate(items):
        ring = find(e, n)
        if ring:
            ml = [[round(px - xmin, 1), round(py - ymin, 1)] for px, py in ring]
            if ml[0] != ml[-1]:
                ml.append(ml[0])
            batch.append((Jsonb([ml]), bid))
            updated += 1
        if len(batch) >= 100 or k == len(items) - 1:
            if batch:
                with conn.cursor() as cur:
                    cur.executemany("UPDATE map_building SET rings = %s WHERE id = %s", batch)
                conn.commit()
                batch = []
            if progress:
                progress(int(100 * (k + 1) / len(items)))
    return updated


def map_automatch(conn, locality_id):
    """Link map buildings to our sites by the federal EGID (stable across re-imports). Two durable sources:
       1) a building row in our data carrying the same EGID -> that building's site
       2) a saved manual match (map_match)                  -> its site  (wins over 1)
    Returns the number of buildings matched."""
    # 1) buildings in our dataset that already carry an EGID
    conn.execute(
        "UPDATE map_building mb SET id_site = b.id_site, match_kind = 'egid' "
        "FROM map_import mi, building b "
        "WHERE mb.map_import_id = mi.id AND mi.locality_id = %s "
        "  AND b.locality_id = %s AND b.egid IS NOT NULL AND b.id_site IS NOT NULL AND mb.egid = b.egid::text",
        (locality_id, locality_id))
    # 2) saved manual matches override
    conn.execute(
        "UPDATE map_building mb SET id_site = mm.id_site, match_kind = 'manual' "
        "FROM map_import mi, map_match mm "
        "WHERE mb.map_import_id = mi.id AND mi.locality_id = %s "
        "  AND mm.locality_id = %s AND mb.egid = mm.egid",
        (locality_id, locality_id))
    conn.commit()
    n = conn.execute(
        "SELECT count(*) AS n FROM map_building mb JOIN map_import mi ON mi.id = mb.map_import_id "
        "WHERE mi.locality_id = %s AND mb.id_site IS NOT NULL", (locality_id,)).fetchone()["n"]
    return n


def map_get(conn, locality_id):
    """Rebuild buildings.json (meta + buildings with id_site) for this locality, or None if no map."""
    mi = conn.execute(
        "SELECT id, meta, n_buildings FROM map_import WHERE locality_id = %s", (locality_id,)).fetchone()
    if not mi:
        return None
    rows = conn.execute(
        "SELECT id, egid, rings, h, z, attrs, id_site, match_kind FROM map_building "
        "WHERE map_import_id = %s ORDER BY id", (mi["id"],)).fetchall()
    buildings = []
    for r in rows:
        a = r["attrs"] or {}
        buildings.append({
            "id": r["id"], "egid": r["egid"], "rings": r["rings"],
            "h": float(r["h"]) if r["h"] is not None else 6.0,
            "z": float(r["z"]) if r["z"] is not None else 0.0,
            "use": a.get("use"), "year": a.get("year"), "levels": a.get("levels"), "addr": a.get("addr"),
            "id_site": r["id_site"], "match_kind": r["match_kind"],
        })
    return {"meta": mi["meta"], "buildings": buildings}


def map_terrain(conn, locality_id):
    r = conn.execute("SELECT terrain FROM map_import WHERE locality_id = %s", (locality_id,)).fetchone()
    return bytes(r["terrain"]) if r and r["terrain"] is not None else None


def map_tile(conn, locality_id, i, j):
    r = conn.execute(
        "SELECT t.jpg FROM map_tile t JOIN map_import mi ON mi.id = t.map_import_id "
        "WHERE mi.locality_id = %s AND t.i = %s AND t.j = %s", (locality_id, i, j)).fetchone()
    return bytes(r["jpg"]) if r else None


def map_set_site(conn, locality_id, building_id, id_site):
    """Manual match: assign (or clear) the site of one map building, and persist it by EGID so it
    survives a re-import (map_match). Clearing removes the saved match."""
    r = conn.execute(
        "UPDATE map_building mb SET id_site = %s, match_kind = %s "
        "FROM map_import mi WHERE mb.map_import_id = mi.id AND mi.locality_id = %s AND mb.id = %s "
        "RETURNING mb.egid",
        (id_site, "manual" if id_site else None, locality_id, building_id)).fetchone()
    if r is None:
        return False
    egid = r["egid"]
    if egid:
        if id_site:
            conn.execute(
                "INSERT INTO map_match (locality_id, egid, id_site) VALUES (%s, %s, %s) "
                "ON CONFLICT (locality_id, egid) DO UPDATE SET id_site = EXCLUDED.id_site, at = now()",
                (locality_id, egid, id_site))
        else:
            conn.execute("DELETE FROM map_match WHERE locality_id = %s AND egid = %s", (locality_id, egid))
    conn.commit()
    return True


def map_register_building(conn, locality_id, map_building_id, mode, id_site=None, site_name=None):
    """Register a map block as a real building in this municipality, then match it durably by EGID.
       mode='existing' -> add the building under an existing site (id_site required)
       mode='new'      -> create a new site (site_name) with this one building
    Returns {id_site, id_batiment, egid}."""
    mb = conn.execute(
        "SELECT mb.egid, mb.attrs FROM map_building mb JOIN map_import mi ON mi.id = mb.map_import_id "
        "WHERE mi.locality_id = %s AND mb.id = %s", (locality_id, map_building_id)).fetchone()
    if not mb:
        raise LookupError("map building not found")
    egid = mb["egid"]
    a = mb["attrs"] or {}
    addr = a.get("addr") or (f"EGID {egid}" if egid else "Bâtiment")
    levels = a.get("levels")
    year = a.get("year")
    sre = None  # GWR area is footprint, not SRE; leave blank (user can edit in the Data module)

    with conn.transaction(), conn.cursor() as cur:
        if mode == "new":
            if not site_name:
                raise ValueError("site_name required for a new site")
            # next free site id in this locality: Gnn / Snn style -> use "M" prefix to avoid clashes
            n = cur.execute("SELECT count(*) AS n FROM building WHERE locality_id = %s", (locality_id,)).fetchone()["n"]
            sid = f"MAP{n + 1:03d}"
            typologie = "Autre"
            pos = n
        else:
            if not id_site:
                raise ValueError("id_site required for an existing site")
            sid = id_site
            exist = cur.execute(
                "SELECT nom_site, typologie, quartier, max(pos) OVER () AS maxpos FROM building "
                "WHERE locality_id = %s AND id_site = %s LIMIT 1", (locality_id, sid)).fetchone()
            if not exist:
                raise LookupError("site not found")
            typologie = exist["typologie"]
            site_name = exist["nom_site"]
            pos = (exist["maxpos"] or 0) + 1

        # a free building id under this site
        k = cur.execute("SELECT count(*) AS n FROM building WHERE locality_id = %s AND id_site = %s",
                        (locality_id, sid)).fetchone()["n"]
        id_batiment = f"{sid}-B{k + 1}"
        cur.execute(
            "INSERT INTO building (locality_id, id_batiment, id_site, nom_site, quartier, typologie, nom_batiment, "
            "annee_construction, sre_m2, niveaux, egid, pos) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (locality_id, id_batiment) DO UPDATE SET egid = EXCLUDED.egid",
            (locality_id, id_batiment, sid, site_name, a.get("quartier") or (None if mode == "new" else None),
             typologie, addr, year, sre, levels, egid, pos))
        # durable match + colour the block now
        if egid:
            cur.execute(
                "INSERT INTO map_match (locality_id, egid, id_site) VALUES (%s,%s,%s) "
                "ON CONFLICT (locality_id, egid) DO UPDATE SET id_site = EXCLUDED.id_site, at = now()",
                (locality_id, egid, sid))
        cur.execute(
            "UPDATE map_building SET id_site = %s, match_kind = 'manual' WHERE id = %s", (sid, map_building_id))
    return {"id_site": sid, "id_batiment": id_batiment, "egid": egid, "site_name": site_name}


def map_delete(conn, locality_id):
    conn.execute("DELETE FROM map_import WHERE locality_id = %s", (locality_id,))
    conn.commit()


def geocode(text, country="CH"):
    """Place name -> candidate zones, searched on the right national platform (CH: geo.admin.ch, FR: BAN)."""
    return geomap.geocode_fr(text) if (country or "CH").upper() == "FR" else geomap.geocode(text)

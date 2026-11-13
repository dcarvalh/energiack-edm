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


def last_run(conn):
    return conn.execute("SELECT max(id) AS id FROM import_run WHERE report IS NOT NULL").fetchone()["id"]


def _upsert(cur, table, key, cols, rows):
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
    cur.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {sets}", rows)


def load(conn, T, source):
    """Import the tables T ({name: [row dicts]}). Returns the import_run row. All or nothing."""
    report, rej = rc.check(T)
    why = {}                                           # (meter, month) -> check that rejected the row
    for ch in report["checks"]:
        if ch["kind"] == "rejected":
            for it in ch["items"]:
                why.setdefault((it.get("m"), it.get("mo")), ch["code"])
    with conn.transaction(), conn.cursor() as cur:
        run = cur.execute("INSERT INTO import_run (source) VALUES (%s) RETURNING id", (source,)).fetchone()["id"]
        for name, (table, key, cols) in REF.items():
            _upsert(cur, table, [key], cols + ["pos"], [[null(r.get(c)) for c in cols] + [n] for n, r in enumerate(T[name])])
        cur.execute("DELETE FROM reference WHERE name = ANY(%s)", (LOOKUPS,))
        cur.executemany("INSERT INTO reference (name, pos, row) VALUES (%s, %s, %s)",
                        [(name, n, Jsonb(r)) for name in LOOKUPS for n, r in enumerate(T[name])])

        have = {(r["id_compteur"], r["mois"]): (text(r["valeur"]), text(r["energie_kwh"]), text(r["qualite"]))
                for r in cur.execute("SELECT id_compteur, mois, valeur, energie_kwh, qualite FROM reading").fetchall()}
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
            rows.append([null(r.get(c)) for c in READING] + [run, n])
        _upsert(cur, "reading", ["id_compteur", "mois"], READING + ["import_id", "pos"], rows)
        cur.executemany("INSERT INTO rejected_row (import_id, pos, reason, row) VALUES (%s, %s, %s, %s)", refused)
        return cur.execute(
            "UPDATE import_run SET rows_read = %s, loaded = %s, rejected = %s, added = %s, unchanged = %s, changed = %s, "
            "report = %s WHERE id = %s RETURNING id, at, source, rows_read, loaded, rejected, added, unchanged, changed",
            (len(T["mesures"]), len(rows), len(refused), added, same, changed, Jsonb(report), run)).fetchone()


def tables(conn):
    """The database content in the shape the importer reads: (T, quality report, rejected row indexes)."""
    run = last_run(conn)
    T = {}
    for name, (table, _, cols) in REF.items():
        T[name] = [{c: text(r[c]) for c in cols} for r in conn.execute(f"SELECT * FROM {table} ORDER BY pos").fetchall()]
    for name in LOOKUPS:
        T[name] = [r["row"] for r in conn.execute("SELECT row FROM reference WHERE name = %s ORDER BY pos", (name,)).fetchall()]
    mes = [((r["import_id"], r["pos"]), {c: text(r[c]) for c in READING}, False)
           for r in conn.execute("SELECT * FROM reading").fetchall()]
    mes += [((run, r["pos"]), r["row"], True)
            for r in conn.execute("SELECT pos, row FROM rejected_row WHERE import_id = %s", (run,)).fetchall()]
    mes.sort(key=lambda x: x[0])                       # file order: the importer keeps the first of two duplicates
    T["mesures"] = [m[1] for m in mes]
    report = conn.execute("SELECT report FROM import_run WHERE id = %s", (run,)).fetchone()["report"]
    return T, report, {n for n, m in enumerate(mes) if m[2]}


def dataset(conn):
    return rc.build(*tables(conn))

"""Background 3D-map import jobs.

A map import (fetch from geo.admin.ch + store + auto-match) is slow (tens of seconds to minutes), so it runs in a
daemon thread instead of blocking the request. Progress is kept in memory (one job per locality). Only the user who
started a job sees it: their page asks `GET /api/map/jobs` every few seconds while it runs (no connection kept open).
Single-process only — fine for this prototype; a multi-worker deploy would need shared state.
"""
import json
import threading
import time

from . import store

JOBS = {}                     # locality_id -> {user, slug, name, state, pct, step, n, matched, unmatched, error, started, updated}
_LOCK = threading.Lock()


def _set(lid, **kw):
    with _LOCK:
        j = JOBS.setdefault(lid, {})
        j.update(kw)
        j["updated"] = time.time()


def busy(j):
    return bool(j) and (j.get("state") == "running" or j.get("fp") == "running")


def mine(user_id):
    """The jobs this user started, keyed by locality id (without the user id)."""
    with _LOCK:
        return {lid: {k: v for k, v in j.items() if k != "user"} for lid, j in JOBS.items() if j.get("user") == user_id}


def start(locality_id, user_id, slug, bbox, tiles, px, name, osm=True, country="CH"):
    """Launch the import in a daemon thread and return at once. False if one is already running for this locality."""
    name = " ".join((name or "").split())[:120]              # one line, bounded length
    with _LOCK:
        if busy(JOBS.get(locality_id)):                      # also wait for a previous job's footprint phase
            return False
        JOBS[locality_id] = {"user": user_id, "slug": slug, "name": name, "state": "running", "pct": 0, "step": "queued",
                             "started": time.time(), "updated": time.time()}

    is_ch = (country or "CH").upper() == "CH"

    def run():
        conn = store.connect()
        try:
            def prog(pct, step):
                _set(locality_id, state="running", pct=pct, step=step)
            # Phase 1 — fast square-block map (no OSM for CH): ready to explore as soon as this finishes.
            summary = store.map_import(conn, locality_id, bbox, tiles=tiles, px=px, name=name, progress=prog,
                                       osm=(osm and not is_ch), country=country)
            conn.execute("UPDATE locality SET map_config = %s WHERE id = %s",
                         (json.dumps({"key": "imported", "dir": f"api/localities/{slug}/map/"}), locality_id))
            conn.commit()
            enhance = osm and is_ch
            _set(locality_id, state="done", pct=100, step="done", n=summary["n"], matched=summary["matched"],
                 unmatched=summary["unmatched"], fp=("running" if enhance else "none"), fp_pct=0, fp_n=0, fp_total=summary["n"])
            # Phase 2 — progressively replace blocks with real OSM footprints, biggest building first.
            if enhance:
                def fprog(pct, done, total):
                    _set(locality_id, fp="running", fp_pct=pct, fp_n=done, fp_total=total)
                try:
                    nfp = store.map_enhance_footprints(conn, locality_id, fprog)
                except Exception:
                    nfp = 0
                _set(locality_id, fp="done", fp_pct=100, fp_n=nfp)
        except Exception as e:                       # noqa: BLE001 - surface any failure to the client
            try:
                conn.rollback()
            except Exception:
                pass
            _set(locality_id, state="error", step="error", error=str(e))
        finally:
            conn.close()

    threading.Thread(target=run, daemon=True, name=f"mapimport-{slug}").start()
    return True


def start_footprints(locality_id, user_id, slug, name=""):
    """Re-run just the OSM footprint resolution for an existing (CH) map, in the background. Resumable: it only tries
    blocks still 'pending', so it continues where a partial OSM outage left off. False if a job is already running."""
    with _LOCK:
        j = JOBS.get(locality_id) or {}
        if busy(j):
            return False
        JOBS[locality_id] = {"user": user_id, "slug": slug, "name": name or j.get("name") or slug, "state": "done", "pct": 100,
                             "step": "done", "fp": "running", "fp_pct": 0, "fp_n": 0, "fp_total": 0,
                             "started": time.time(), "updated": time.time()}

    def run():
        conn = store.connect()
        try:
            def fprog(pct, done, total):
                _set(locality_id, fp="running", fp_pct=pct, fp_n=done, fp_total=total)
            try:
                nfp = store.map_enhance_footprints(conn, locality_id, fprog)
            except Exception:
                nfp = 0
            _set(locality_id, fp="done", fp_pct=100, fp_n=nfp)
        finally:
            conn.close()

    threading.Thread(target=run, daemon=True, name=f"mapfp-{slug}").start()
    return True


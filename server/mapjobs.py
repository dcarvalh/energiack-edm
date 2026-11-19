"""Background 3D-map import jobs.

A map import (fetch from geo.admin.ch + store + auto-match) is slow (tens of seconds to minutes), so it runs in a
daemon thread instead of blocking the request. Progress is kept in memory (one job per locality) and pushed to clients
over Server-Sent Events. Single-process only — fine for this prototype; a multi-worker deploy would need shared state.
"""
import json
import threading
import time

from . import store

JOBS = {}                     # locality_id -> {slug, name, state, pct, step, n, matched, unmatched, error, started, updated}
_LOCK = threading.Lock()


def _set(lid, **kw):
    with _LOCK:
        j = JOBS.setdefault(lid, {})
        j.update(kw)
        j["updated"] = time.time()


def get(lid):
    with _LOCK:
        return dict(JOBS[lid]) if lid in JOBS else None


def running(lid):
    with _LOCK:
        return (JOBS.get(lid) or {}).get("state") == "running"


def snapshot(lids):
    with _LOCK:
        return {lid: dict(JOBS[lid]) for lid in lids if lid in JOBS}


def start(locality_id, slug, bbox, tiles, px, name, osm=True, country="CH"):
    """Launch the import in a daemon thread and return at once. False if one is already running for this locality."""
    name = " ".join((name or "").split())[:120]              # strip newlines/control chars so the SSE JSON stays valid
    with _LOCK:
        if (JOBS.get(locality_id) or {}).get("state") == "running":
            return False
        JOBS[locality_id] = {"slug": slug, "name": name, "state": "running", "pct": 0, "step": "queued",
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


def start_footprints(locality_id, slug, name=""):
    """Re-run just the OSM footprint resolution for an existing (CH) map, in the background. Resumable: it only tries
    blocks still 'pending', so it continues where a partial OSM outage left off. False if a job is already running."""
    with _LOCK:
        j = JOBS.get(locality_id) or {}
        if j.get("state") == "running" or j.get("fp") == "running":
            return False
        JOBS[locality_id] = {"slug": slug, "name": name or j.get("name") or slug, "state": "done", "pct": 100,
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


def sse_stream(lids):
    """Yield Server-Sent Events for the given localities' jobs: one event whenever a job changes, plus heartbeats.
    Runs until the client disconnects (the generator is then dropped). lids is captured once at subscription time."""
    sent = {}                                        # locality_id -> last 'updated' timestamp pushed
    # initial state so a client that connects mid-import (or after) sees it immediately
    for lid, j in snapshot(lids).items():
        sent[lid] = j["updated"]
        yield f"data: {json.dumps({'locality_id': lid, **j})}\n\n"
    last_beat = time.time()
    while True:
        changed = False
        for lid, j in snapshot(lids).items():
            if sent.get(lid) != j["updated"]:
                sent[lid] = j["updated"]
                changed = True
                yield f"data: {json.dumps({'locality_id': lid, **j})}\n\n"
        now = time.time()
        if not changed and now - last_beat > 15:
            last_beat = now
            yield ": heartbeat\n\n"                   # keep the connection alive through proxies
        time.sleep(1)

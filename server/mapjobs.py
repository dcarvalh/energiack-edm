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


def start(locality_id, slug, bbox, tiles, px, name):
    """Launch the import in a daemon thread and return at once. False if one is already running for this locality."""
    with _LOCK:
        if (JOBS.get(locality_id) or {}).get("state") == "running":
            return False
        JOBS[locality_id] = {"slug": slug, "name": name, "state": "running", "pct": 0, "step": "queued",
                             "started": time.time(), "updated": time.time()}

    def run():
        conn = store.connect()
        try:
            def prog(pct, step):
                _set(locality_id, state="running", pct=pct, step=step)
            summary = store.map_import(conn, locality_id, bbox, tiles=tiles, px=px, name=name, progress=prog)
            conn.execute("UPDATE locality SET map_config = %s WHERE id = %s",
                         (json.dumps({"key": "imported", "dir": f"api/localities/{slug}/map/"}), locality_id))
            conn.commit()
            _set(locality_id, state="done", pct=100, step="done",
                 n=summary["n"], matched=summary["matched"], unmatched=summary["unmatched"])
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

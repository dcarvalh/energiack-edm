"""openEDM API (FastAPI). Machine-readable description: /api/openapi.json

Public     GET  /api/config.json  {"server": true, "demo": true if one-click demo logins are on}
           GET  /api/health       database reachable, last import
           GET  /api/data.json    the dataset in the app's open format, rebuilt from the database. Without the
                                  technique or admin role, raw meter readings ("meters") and the quality report are left out.
           POST /api/login        {"username", "password"} -> session cookie      POST /api/logout
           POST /api/demo-login   {"role"} -> session as demo-<role> (only with DEMO_LOGIN=1)
           GET  /api/me           username, role, demo; null when not logged in
technique, GET  /api/imports      import history (rows read, loaded, rejected, added, unchanged, changed)
admin      GET  /api/rejected     the rows the last import refused, with the reason
           GET  /api/readings?meter=S01-EL    raw monthly readings of one meter
admin      GET  /api/users        PUT /api/users/{username} {"role"}

Roles: server/auth.py. The web server sends /data.json to /api/data.json, so the app in prototype/ runs on the database.
"""
import hashlib
import json
import os

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth, store

DEMO = os.environ.get("DEMO_LOGIN", "0") == "1"
app = FastAPI(title="openEDM API", version="2", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
_cache = {}                                            # full: bool -> {run, body, etag}; rebuilt after a new import


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


def _start(request, response, conn, token):
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, token, max_age=auth.HOURS * 3600, httponly=True, samesite="lax", secure=https, path="/")
    return auth.user_for(conn, token)


@app.get("/api/config.json")
def config():
    # prototype/api/config.json says {"server": false} on a static host; here the API answers instead.
    return {"server": True, "demo": DEMO, "roles": auth.ROLES}


@app.get("/api/health")
def health(conn=Depends(db)):
    r = conn.execute("SELECT id, at, loaded FROM import_run WHERE report IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return {"ok": True, "last_import": r}


@app.get("/api/data.json")
def data(request: Request, u=Depends(current), conn=Depends(db)):
    run = store.last_run(conn)
    if run is None:
        raise HTTPException(503, "no data imported yet")
    full = bool(u) and u["role"] in auth.FULL
    c = _cache.get(full)
    if not c or c["run"] != run:
        d = store.dataset(conn)
        if not full:
            d["meters"], d["quality"] = {}, None
            d["meta"]["restricted"] = ["meters", "quality"]
        body = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()
        c = _cache[full] = {"run": run, "body": body, "etag": '"%s"' % hashlib.sha256(body).hexdigest()[:16]}
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


@app.get("/api/imports")
def imports(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    return conn.execute("SELECT id, at, source, rows_read, loaded, rejected, added, unchanged, changed FROM import_run "
                        "WHERE report IS NOT NULL ORDER BY id DESC LIMIT 100").fetchall()


@app.get("/api/rejected")
def rejected(u=Depends(need(*auth.FULL)), conn=Depends(db)):
    return conn.execute("SELECT pos, reason, row FROM rejected_row WHERE import_id = %s ORDER BY pos",
                        (store.last_run(conn),)).fetchall()


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

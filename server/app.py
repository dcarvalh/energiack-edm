"""openEDM API (FastAPI). Machine-readable description: /api/openapi.json

Public     GET  /api/health       database reachable, last import
           GET  /api/data.json    the dataset in the app's open format, rebuilt from the database
           POST /api/login        {"username", "password"} -> session cookie      POST /api/logout
Logged in  GET  /api/me           who am I
           GET  /api/imports      import history (rows read, loaded, rejected, added, unchanged, changed)
           GET  /api/rejected     the rows the last import refused, with the reason
           GET  /api/readings?meter=S01-EL    raw monthly readings of one meter

The web server sends /data.json to /api/data.json, so the app in prototype/ runs unchanged on top of the database.
"""
import hashlib
import json

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth, store

app = FastAPI(title="openEDM API", version="1", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
_cache = {"run": None}                                 # data.json is rebuilt only after a new import


def db():
    with store.connect() as conn:
        yield conn


def user(request: Request, conn=Depends(db)):
    u = auth.user_for(conn, request.cookies.get(auth.COOKIE))
    if not u:
        raise HTTPException(401, "login required")
    return u


class Login(BaseModel):
    username: str
    password: str


@app.get("/api/health")
def health(conn=Depends(db)):
    r = conn.execute("SELECT id, at, loaded FROM import_run WHERE report IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return {"ok": True, "last_import": r}


@app.get("/api/data.json")
def data(request: Request, conn=Depends(db)):
    global _cache
    run = store.last_run(conn)
    if run is None:
        raise HTTPException(503, "no data imported yet")
    c = _cache
    if c["run"] != run:
        body = json.dumps(store.dataset(conn), ensure_ascii=False, separators=(",", ":")).encode()
        c = _cache = {"run": run, "body": body, "etag": '"%s"' % hashlib.sha256(body).hexdigest()[:16]}
    headers = {"ETag": c["etag"], "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == c["etag"]:
        return Response(status_code=304, headers=headers)
    return Response(c["body"], media_type="application/json", headers=headers)


@app.post("/api/login")
def login(body: Login, request: Request, response: Response, conn=Depends(db)):
    token = auth.login(conn, body.username, body.password)
    if not token:
        raise HTTPException(401, "wrong username or password, or account locked for a few minutes")
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, token, max_age=auth.HOURS * 3600, httponly=True, samesite="lax", secure=https, path="/")
    return auth.user_for(conn, token)


@app.post("/api/logout")
def logout(request: Request, response: Response, conn=Depends(db)):
    auth.logout(conn, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(u=Depends(user)):
    return u


@app.get("/api/imports")
def imports(u=Depends(user), conn=Depends(db)):
    return conn.execute("SELECT id, at, source, rows_read, loaded, rejected, added, unchanged, changed FROM import_run "
                        "WHERE report IS NOT NULL ORDER BY id DESC LIMIT 100").fetchall()


@app.get("/api/rejected")
def rejected(u=Depends(user), conn=Depends(db)):
    return conn.execute("SELECT pos, reason, row FROM rejected_row WHERE import_id = %s ORDER BY pos",
                        (store.last_run(conn),)).fetchall()


@app.get("/api/readings")
def readings(meter: str, u=Depends(user), conn=Depends(db)):
    return conn.execute("SELECT mois, valeur, unite, energie_kwh, qualite FROM reading WHERE id_compteur = %s ORDER BY mois",
                        (meter,)).fetchall()

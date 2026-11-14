"""Accounts, roles and sessions, with the standard library only.

Roles (issue #15) and what they see. The app mirrors this table (ACCESS in prototype/index.html) to hide menus; the API
enforces it on the data:
  public     Welcome, Citizens, 3D map, How it works, site pages without raw readings. Also every visitor not logged in.
  elu        + Manage
  technique  + Data quality, raw meter readings, CSV exports (data.json in full)
  admin      + Users (assign roles)

Passwords: scrypt with a random salt per user. Sessions: a random token in an HttpOnly cookie; the database only keeps
its SHA-256. Five wrong passwords lock the account for five minutes.
Demo accounts (demo-admin, demo-technique, demo-elu, demo-public): no usable password, one-click login only when the
server runs with DEMO_LOGIN=1. Their roles are reset at every start.
"""
import hashlib
import hmac
import secrets

COOKIE = "edm_session"
HOURS = 12
ROLES = ("admin", "technique", "elu", "public")
FULL = ("admin", "technique")                         # see raw readings and the quality report
DEMO_PREFIX = "demo-"
N, R, P = 2 ** 15, 8, 1


def _scrypt(password, salt, n, r, p):
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=2 ** 26, dklen=32)


def hash_password(password):
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_scrypt(password, salt, N, R, P).hex()}"


def verify(password, stored):
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), h)


_DUMMY = hash_password("-")                           # so an unknown user costs the same time as a wrong password
_sha = lambda token: hashlib.sha256(token.encode()).hexdigest()


def add_user(conn, username, password, role):
    """Create the account, or reset its password and role."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if len(password) < 10:
        raise ValueError("password: at least 10 characters")
    if username.startswith(DEMO_PREFIX):
        raise ValueError(f"names starting with {DEMO_PREFIX} are reserved for the demo accounts")
    conn.execute("INSERT INTO app_user (username, pw_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO UPDATE "
                 "SET pw_hash = EXCLUDED.pw_hash, role = EXCLUDED.role, failed = 0, locked_until = NULL",
                 (username, hash_password(password), role))
    conn.execute("DELETE FROM session WHERE user_id = (SELECT id FROM app_user WHERE username = %s)", (username,))
    conn.commit()


DEMO_STAFF = {"a.martin": "technique", "c.rochat": "elu", "l.favre": "public"}   # fictional, for the demo admin to re-assign


def ensure_demo(conn):
    """The four one-click demo accounts (fixed roles) and three fictional staff accounts, all reset.
    The password hash "!" never verifies, so none of them can log in with a password."""
    for name, role in [(DEMO_PREFIX + r, r) for r in ROLES] + list(DEMO_STAFF.items()):
        conn.execute("INSERT INTO app_user (username, pw_hash, role, demo) VALUES (%s, '!', %s, true) "
                     "ON CONFLICT (username) DO UPDATE SET role = EXCLUDED.role, demo = true, pw_hash = '!'", (name, role))
    conn.commit()


def _session(conn, user_id):
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM session WHERE expires_at < now()")
    conn.execute("INSERT INTO session (token_hash, user_id, expires_at) VALUES (%s, %s, now() + %s * interval '1 hour')",
                 (_sha(token), user_id, HOURS))
    conn.commit()
    return token


def login(conn, username, password):
    """A new session token, or None."""
    u = conn.execute("SELECT id, pw_hash, demo, coalesce(locked_until > now(), false) AS locked FROM app_user "
                     "WHERE username = %s", (username,)).fetchone()
    ok = verify(password, u["pw_hash"] if u else _DUMMY)
    if not u or u["locked"] or u["demo"]:
        return None
    if not ok:
        conn.execute("UPDATE app_user SET failed = failed + 1, locked_until = CASE WHEN failed + 1 >= 5 "
                     "THEN now() + interval '5 minutes' ELSE locked_until END WHERE id = %s", (u["id"],))
        conn.commit()
        return None
    conn.execute("UPDATE app_user SET failed = 0, locked_until = NULL WHERE id = %s", (u["id"],))
    return _session(conn, u["id"])


def demo_login(conn, role):
    """A session for the demo account of this role, or None. The caller checks that DEMO_LOGIN is on."""
    if role not in ROLES:
        return None
    u = conn.execute("SELECT id FROM app_user WHERE username = %s AND demo", (DEMO_PREFIX + role,)).fetchone()
    return _session(conn, u["id"]) if u else None


def user_for(conn, token):
    if not token:
        return None
    return conn.execute("SELECT u.username, u.role, u.demo FROM session s JOIN app_user u ON u.id = s.user_id "
                        "WHERE s.token_hash = %s AND s.expires_at > now()", (_sha(token),)).fetchone()


def logout(conn, token):
    if token:
        conn.execute("DELETE FROM session WHERE token_hash = %s", (_sha(token),))
        conn.commit()


def users(conn):
    return conn.execute("SELECT username, role, demo, created_at FROM app_user ORDER BY demo, username").fetchall()


def set_role(conn, actor, username, role):
    """Change a user's role. Rules: valid role, not your own role, the one-click demo accounts keep their role,
    a demo admin only changes demo accounts."""
    if role not in ROLES:
        raise ValueError("unknown role")
    if username == actor["username"]:
        raise PermissionError("you cannot change your own role")
    if username.startswith(DEMO_PREFIX):
        raise PermissionError("the demo login accounts keep their role")
    target = conn.execute("SELECT demo FROM app_user WHERE username = %s", (username,)).fetchone()
    if not target:
        raise LookupError("unknown user")
    if actor["demo"] and not target["demo"]:
        raise PermissionError("a demo account can only change demo accounts")
    conn.execute("UPDATE app_user SET role = %s WHERE username = %s", (role, username))
    conn.commit()

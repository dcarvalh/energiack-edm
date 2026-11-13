"""Accounts and sessions, with the standard library only.

Passwords: scrypt with a random salt per user. Sessions: a random token in an HttpOnly cookie; the database only keeps
its SHA-256. Five wrong passwords lock the account for five minutes.
"""
import hashlib
import hmac
import secrets

COOKIE = "edm_session"
HOURS = 12
ROLES = ("admin", "manager")
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
    conn.execute("INSERT INTO app_user (username, pw_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO UPDATE "
                 "SET pw_hash = EXCLUDED.pw_hash, role = EXCLUDED.role, failed = 0, locked_until = NULL",
                 (username, hash_password(password), role))
    conn.execute("DELETE FROM session WHERE user_id = (SELECT id FROM app_user WHERE username = %s)", (username,))
    conn.commit()


def login(conn, username, password):
    """A new session token, or None."""
    u = conn.execute("SELECT id, pw_hash, coalesce(locked_until > now(), false) AS locked FROM app_user WHERE username = %s",
                     (username,)).fetchone()
    ok = verify(password, u["pw_hash"] if u else _DUMMY)
    if not u or u["locked"]:
        return None
    if not ok:
        conn.execute("UPDATE app_user SET failed = failed + 1, locked_until = CASE WHEN failed + 1 >= 5 "
                     "THEN now() + interval '5 minutes' ELSE locked_until END WHERE id = %s", (u["id"],))
        conn.commit()
        return None
    token = secrets.token_urlsafe(32)
    conn.execute("UPDATE app_user SET failed = 0, locked_until = NULL WHERE id = %s", (u["id"],))
    conn.execute("DELETE FROM session WHERE expires_at < now()")
    conn.execute("INSERT INTO session (token_hash, user_id, expires_at) VALUES (%s, %s, now() + %s * interval '1 hour')",
                 (_sha(token), u["id"], HOURS))
    conn.commit()
    return token


def user_for(conn, token):
    if not token:
        return None
    return conn.execute("SELECT u.username, u.role FROM session s JOIN app_user u ON u.id = s.user_id "
                        "WHERE s.token_hash = %s AND s.expires_at > now()", (_sha(token),)).fetchone()


def logout(conn, token):
    if token:
        conn.execute("DELETE FROM session WHERE token_hash = %s", (_sha(token),))
        conn.commit()

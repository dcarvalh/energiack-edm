"""Admin commands, run inside the api container:

  docker compose exec api python -m server.cli import      load the Rive-Claire dataset shipped in the image (repeatable)
  docker compose exec api python -m server.cli adduser NAME --role admin|technique|elu|public      asks for the password
  docker compose exec api python -m server.cli users

`seed` is what the stack runs at every start: create the tables, load the demo dataset unless SEED_DEMO=0, and reset
the demo accounts when DEMO_LOGIN=1.
"""
import argparse
import getpass
import os
import sys

from . import auth, store


def do_import(conn):
    r = store.load(conn, store.rc.read_guide(), "rive-claire (bundled guide)")
    print(f"import {r['id']}: read {r['rows_read']}, loaded {r['loaded']}, rejected {r['rejected']} · "
          f"added {r['added']}, unchanged {r['unchanged']}, changed {r['changed']}")


def main():
    ap = argparse.ArgumentParser(prog="python -m server.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    sub.add_parser("import")
    sub.add_parser("users")
    a = sub.add_parser("adduser")
    a.add_argument("username")
    a.add_argument("--role", choices=auth.ROLES, default="technique")
    a.add_argument("--password-stdin", action="store_true", help="read the password from standard input (for scripts)")
    A = ap.parse_args()
    with store.connect() as conn:
        store.init(conn)
        if A.cmd == "import" or (A.cmd == "seed" and os.environ.get("SEED_DEMO", "1") != "0"):
            do_import(conn)
        if A.cmd == "seed" and os.environ.get("DEMO_LOGIN", "0") == "1":
            auth.ensure_demo(conn)
            print("demo accounts reset")
        elif A.cmd == "users":
            for u in auth.users(conn):
                print(f"{u['username']}\t{u['role']}\t{'demo' if u['demo'] else ''}\t{u['created_at']:%Y-%m-%d}")
        elif A.cmd == "adduser":
            pw = sys.stdin.readline().rstrip("\n") if A.password_stdin else getpass.getpass("Password (10 characters or more): ")
            try:
                auth.add_user(conn, A.username, pw, A.role)
            except ValueError as e:
                sys.exit(str(e))
            print(f"user {A.username} ({A.role}) saved")


if __name__ == "__main__":
    main()

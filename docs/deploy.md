# Running openEDM with a database

The public demo (GitHub Pages) is static: `prototype/` with `data.json`. It keeps working as it is.
`compose.yaml` runs the same app on top of PostgreSQL, with accounts, on any machine with Docker.

```
browser ──► web (Caddy: HTTPS, the app's files) ──► api (FastAPI) ──► db (PostgreSQL)
                                                     ▲
                                  seed: creates the tables and loads the demo dataset at every start
```

| Service | What | Image |
|---|---|---|
| `db` | PostgreSQL 18. Reference tables (buildings, installations, meters) apart from monthly readings; readings keyed on (meter, month), so re-importing adds 0 rows; refused rows kept with their reason; import history; accounts | `postgres:18-alpine` |
| `api` | `server/`: `/api/data.json` rebuilt from the database with the same code as the static build (`tools/import_rive_claire.py`), login, import history, refused rows, raw readings | built from `server/Dockerfile` |
| `web` | serves `prototype/`, sends `/api/*` and `/data.json` to the API, gets and renews the HTTPS certificate by itself | `caddy:2-alpine` |

The app needs no change: it fetches `data.json`, which now comes from the database.

## Run it on your machine

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD (openssl rand -hex 24)
docker compose up -d --build  # open http://127.0.0.1:8088/
docker compose exec api python -m server.cli adduser alice --role admin     # asks for the password
tools/check_stack.sh          # full check in a throwaway copy of the stack (removed at the end)
```

Other commands: `python -m server.cli import` (re-import the bundled dataset), `python -m server.cli users`.
API description: `/api/openapi.json`.

## Accounts

Built in, no extra service: users and roles (`admin`, `manager`) in PostgreSQL, scrypt password hashes, a session
cookie (HttpOnly, Secure over HTTPS, 12 h), lock for 5 minutes after 5 wrong passwords. Accounts are created on the
server with the command above (no self sign-up).

**Nothing is really protected yet.** Accounts and sessions work, and `/api/imports`, `/api/rejected` and
`/api/readings` require a session, but `/data.json` is public and already contains every meter's raw readings. There
is no login screen in the app. Which pages need a login is an open decision (see `plan.md`); once decided, the API must
serve a public `data.json` without the restricted parts and the rest only to a session, not just hide it in the page.

When a commune wants its own single sign-on (Microsoft Entra, a cantonal IdP), add an OpenID Connect server
such as Keycloak, Authentik or Zitadel in front, instead of growing this one.

## Put it online for the team

Recommended: **one small Linux server running this same Compose stack**, deployed by GitHub Actions on every merge.

- It is exactly what a commune would run on its own server, so the demo proves the "sovereign, runs anywhere" claim.
- 2 GB of RAM is enough (PostgreSQL + API + Caddy). Any provider works: a Swiss one for the data-residency story,
  or AWS Lightsail with the team's credit (the 2 GB Linux bundle is listed at $12/month; check the price and
  regions on AWS's page before choosing).
- Managed services (RDS + ECS/App Runner + a load balancer) cost several times more each month, take longer to set
  up, and tie the project to one cloud. Worth it only when there are many communes and someone on call.

### Who can deploy

Nobody deploys by hand and nobody needs server access. Teammates open a pull request: the **Stack** workflow
(`.github/workflows/stack.yml`) builds the stack and runs `tools/check_stack.sh`. When the PR is merged into `main`,
the same workflow connects to the server over SSH and runs `git checkout <commit> && docker compose up -d --build --wait`.
GitHub Pages keeps deploying the static demo as before.

### One-time server setup (about 20 minutes)

1. Create an Ubuntu server with 2 GB of RAM. Open ports 22, 80 and 443 only.
2. Point a DNS name (for example `edm.example.ch`) at its address.
3. On the server: install Docker (docs.docker.com/engine/install/ubuntu), create a user `deploy` in the `docker`
   group, then as `deploy`:
   ```bash
   git clone https://github.com/dcarvalh/energiack-edm.git openedm && cd openedm
   cp .env.example .env    # POSTGRES_PASSWORD=..., SITE_ADDRESS=edm.example.ch, HTTP_BIND=80, HTTPS_BIND=443
   docker compose up -d --build
   docker compose exec api python -m server.cli adduser <name> --role admin
   ```
4. Make a key only for GitHub: `ssh-keygen -t ed25519 -f openedm-deploy -N ''`; append `openedm-deploy.pub` to
   `~deploy/.ssh/authorized_keys` on the server.
5. In GitHub › Settings › Secrets and variables › Actions:
   secrets `DEPLOY_SSH_KEY` (content of `openedm-deploy`) and `DEPLOY_KNOWN_HOSTS` (output of `ssh-keyscan <server>`);
   variable `DEPLOY_HOST` (the server's name or address). Optional: `DEPLOY_USER` (default `deploy`),
   `DEPLOY_DIR` (default `openedm`). Until `DEPLOY_HOST` is set, the deploy job is skipped.
6. Settings › Environments › `production`: add required reviewers if a merge should wait for approval before it deploys.

### Backups

The database is in the Docker volume `openedm_db`. A nightly dump, to copy off the server:

```bash
docker compose exec -T db pg_dump -U openedm -Fc openedm > openedm-$(date +%F).dump
# restore: docker compose exec -T db pg_restore -U openedm -d openedm --clean < openedm-YYYY-MM-DD.dump
```

## Not done yet

- Import a new file through the app (upload): today the import runs on the server (`server.cli import`).
- Login screen in the app, and pages that need a login (decision pending).
- Partial or monthly imports: `data.json` takes the quality report and the replaced values from the latest import
  only, which is right while every import is the whole dataset. Incremental files would drop earlier flags.
- Several communes on one install (one database per commune is the simplest: one stack per commune).

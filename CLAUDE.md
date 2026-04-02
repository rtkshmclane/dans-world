# CLAUDE.md -- Dan's World of AI Magic

Docker app platform with centralized auth, per-app containers, and nginx gateway.

## Architecture

```
gateway (nginx)  -->  auth_request to admin
                 -->  proxy to per-app containers on dw-net
admin (Flask 5050)    -- auth, landing page, user management, drop zone
ticketmaker (5000)    -- ticket analysis (Flask)
detection-catalog (5555) -- detection browser (Flask)
integration-adoption (8501) -- adoption analytics (Streamlit)
integration-catalog (5001) -- catalog dashboard (Flask + Vite)
cloud-live (5004)     -- cloud security (Flask)
network-graph (3334)  -- entity graphs (Node/Express)
okta-is (5005)        -- JWT inspector (Flask)
analytic-stories (8089) -- MITRE stories (FastAPI + Vite)
reports (5010)        -- report browser (Flask)
```

All services on `dw-net` bridge network. Gateway is the only public-facing container.

## Key Files

| File | Purpose |
|------|---------|
| `registry.yaml` | Single source of truth for all apps and demos |
| `docker-compose.yml` | Service definitions, uses `${VAR_PATH}` build contexts |
| `paths.env` | Machine-specific app source paths (gitignored) |
| `paths.env.example` | Template for paths.env |
| `.env` | Auth secrets, memory limits (gitignored) |
| `Makefile` | deploy, build, restart, logs, status, health |
| `gateway/conf.d/default.conf` | nginx routing, auth, upstreams |
| `admin/app.py` | Auth server, landing page, admin UI |

## Two-Repo Model

App source code stays in its original location (CTOWorkspace, prototypes, collaborator repos).
This repo is the **orchestration layer** -- it does NOT contain app source code.

- Each app has a Dockerfile in its OWN source directory
- `docker-compose.yml` references app source via `${VAR_PATH}` environment variables
- `paths.env` maps those variables to local paths (different per machine)
- On the server, `scripts/sync-sources.sh` clones/pulls repos and generates paths.env
- Builtin apps (okta_is, reports) live in `apps/` within this repo

## Commands

```bash
# Local development
source paths.env && docker compose up --build -d
docker compose logs -f ticketmaker
docker compose restart detection-catalog

# Server deploy
make deploy          # git pull + sync-sources + docker compose up --build

# Single app rebuild
make build-app APP=ticketmaker

# Health check
make health
```

## Adding a New App

See CONTRIBUTING.md for the full walkthrough. Short version:

1. Add a Dockerfile to your app's source directory (use templates in `dockerfiles/`)
2. Add an entry to `registry.yaml`
3. Add a service to `docker-compose.yml`
4. Add an nginx location block in `gateway/conf.d/default.conf`
5. Add path to `paths.env.example`

## Rules

- **NO EMOJIS** in docs
- Never commit `.env`, `paths.env`, or customer data
- All apps must have a `/health` endpoint
- registry.yaml is the single source of truth -- admin reads it at startup
- App source code does NOT go in this repo (except builtin apps in `apps/`)

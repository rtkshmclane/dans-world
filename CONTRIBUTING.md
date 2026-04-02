# Contributing to Dan's World

This guide covers how to add a new app, update an existing app, and deploy.

## How It Works

Dan's World is an orchestration layer. Your app's source code stays in its own repo or directory. This repo provides:
- Docker Compose service definitions
- nginx routing configuration
- Centralized auth (JWT cookies)
- The admin UI and landing page

## Adding a New App

### Step 1: Add a Dockerfile to Your App

Copy the appropriate template from `dockerfiles/` into your app's root:

| App Type | Template | Default Port |
|----------|----------|-------------|
| Flask | `dockerfiles/flask.Dockerfile` | 5000 |
| FastAPI | `dockerfiles/fastapi.Dockerfile` | 8000 |
| Node.js | `dockerfiles/node.Dockerfile` | 3000 |
| Streamlit | `dockerfiles/streamlit.Dockerfile` | 8501 |

Customize the port, entry point, and base URL path.

Test locally:
```bash
docker build -t my-app .
docker run -p PORT:PORT my-app
```

### Step 2: Add a .dockerignore

Create `.dockerignore` in your app root:
```
__pycache__
*.pyc
.git
.env
node_modules
.venv
```

### Step 3: Add a Health Endpoint

Your app MUST expose a health check endpoint that returns HTTP 200. Examples:

**Flask:**
```python
@app.route("/health")
def health():
    return jsonify({"status": "ok"})
```

**FastAPI:**
```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

**Express:**
```javascript
app.get('/health', (req, res) => res.json({ status: 'ok' }));
```

### Step 4: Register Your App

Add an entry to `registry.yaml`:

```yaml
  - id: my-app                    # URL-safe identifier
    name: My App                   # Display name on landing page
    description: "What it does"
    url: /apps/my-app/             # nginx location path
    icon: app                      # Icon key for landing page
    groups: [analytics, admin]     # Who can see it
    author: Your Name
    port: 5000                     # Internal container port
    health: /health                # Health check path
    memory: 512m                   # Container memory limit
    source:
      repo: rtkshmclane/your-repo  # GitHub repo (for sync-sources.sh)
      path: path/within/repo       # Subpath if app isn't at root
      local: ${MY_APP_PATH}        # env var from paths.env
    container: dw-my-app           # Docker container name
```

### Step 5: Add Docker Compose Service

In `docker-compose.yml`:

```yaml
  my-app:
    build: ${MY_APP_PATH:-./_placeholder}
    container_name: dw-my-app
    env_file:
      - .env
    restart: unless-stopped
    mem_limit: ${MY_APP_MEMORY_LIMIT:-512m}
    networks:
      - dw-net
```

### Step 6: Add nginx Location

In `gateway/conf.d/default.conf`:

1. Add upstream:
```nginx
upstream app_my_app {
    server my-app:5000;
}
```

2. Add location block:
```nginx
    location /apps/my-app/ {
        auth_request /_auth;
        proxy_pass http://app_my_app/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Script-Name /apps/my-app;
    }
```

### Step 7: Update paths.env

Add to `paths.env.example`:
```bash
MY_APP_PATH=/path/to/your/app/source
```

Add to your local `paths.env` with your actual path.

### Step 8: Update sync-sources.sh

If your app lives in a separate repo, add it to the `APPS` array in `scripts/sync-sources.sh`.

### Step 9: Test and Deploy

```bash
source paths.env
docker compose up --build my-app    # Build just your app
docker compose up -d                # Start everything
curl http://localhost/apps/my-app/  # Test through gateway (needs auth)
```

## Updating an Existing App

1. Make changes in your app's source directory
2. Rebuild: `docker compose up --build -d my-app`
3. Or on the server: `make build-app APP=my-app`

## Subpath Deployment Notes

Apps run behind nginx at `/apps/<name>/`. Your app needs to handle this:

**Flask:** Use PrefixMiddleware that reads `X-Script-Name` header.

**FastAPI:** Same WSGI/ASGI middleware approach.

**Streamlit:** Use `--server.baseUrlPath=/apps/my-app/` in CMD.

**Vite/React:** Set `base: '/apps/my-app/'` in vite.config and `basename="/apps/my-app"` on BrowserRouter.

**Node/Express:** Serve static files and API from root; nginx rewrites the path.

## Server Deploy

Anyone with SSH access to the server can deploy:

```bash
ssh octo.rtkwlf.io
cd /opt/dans-world
make deploy
```

This runs: `git pull && ./scripts/sync-sources.sh && docker compose up --build -d`

## Groups

Apps are visible to users in matching groups:

| Group | Access |
|-------|--------|
| admin | All apps + admin panel |
| analytics | Analytics and tool apps |
| demos | Demo sites |
| engineering | Engineering tools |

## Questions?

Check the CLAUDE.md in this repo, or ask Sam.

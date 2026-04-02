# Dan's World -- App Integration Guide

How to make your Dockerized app deployable inside Dan's World.

## Architecture

Dan's World is a Docker Compose stack with three layers:

```
[Browser] --> [nginx gateway :80] --> [your app :XXXX]
                    |
                    +--> auth_request to admin container
                         (JWT cookie check before every request)
```

Your app runs as a Docker service on an internal network. Users never hit your app directly -- nginx proxies to it after verifying authentication.

## What You Need to Provide

### 1. A Dockerfile that exposes a single HTTP port

Your app must listen on a known port. If you have multiple services (e.g., FastAPI backend + React frontend), either:
- **Option A**: Use a multi-stage Dockerfile that builds the frontend and serves it from the backend (simplest)
- **Option B**: Provide separate Dockerfiles for each, and we'll wire both into compose

Example for a FastAPI + React app:

```dockerfile
# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend serving the built frontend
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2. No built-in authentication

Dan's World handles auth centrally. Your app should NOT:
- Have its own login page
- Require API keys from the browser
- Redirect unauthenticated users

nginx will reject unauthenticated requests before they reach your app. If you need to know WHO is logged in, read these headers that nginx forwards:
- `X-Auth-User` -- username
- `X-Auth-Groups` -- comma-separated group list (e.g., `analytics,admin`)

### 3. Support for reverse proxy path prefixes

Your app will be served at `/apps/your-app-name/`, not `/`. This means:
- All asset URLs must be relative (not absolute `/style.css`)
- API calls should use relative paths (`api/data` not `/api/data`)
- If using React Router, set `basename` to the prefix

nginx sends `X-Script-Name` header with the prefix for frameworks that support it (Flask, FastAPI).

For FastAPI, add a root_path:
```python
app = FastAPI(root_path="/apps/your-app-name")
```

For React (Vite), set `base` in vite.config.ts:
```ts
export default defineConfig({
  base: '/apps/your-app-name/',
})
```

### 4. A requirements summary

Tell us:
- **Port(s)** your app listens on
- **Environment variables** it needs (we'll add to `.env`)
- **Volumes** for persistent data (databases, uploads, etc.)
- **Memory estimate** (we set `mem_limit` per container)
- **WebSocket?** If yes, which path (nginx needs special config for WS)

## What We Add on Our Side

Once you hand us the above, we add:

**docker-compose.yml** -- new service:
```yaml
  your-app:
    build: ./apps/your-app
    container_name: dw-your-app
    env_file:
      - .env
    restart: unless-stopped
    mem_limit: ${YOUR_APP_MEMORY_LIMIT:-2g}
    networks:
      - dw-net
```

**gateway/conf.d/default.conf** -- upstream + location:
```nginx
upstream app_your_app {
    server your-app:8000;
}

location /apps/your-app/ {
    auth_request /_auth;
    proxy_pass http://app_your_app/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Script-Name /apps/your-app;
    proxy_set_header X-Auth-User $auth_user;
    proxy_set_header X-Auth-Groups $auth_groups;
}
```

**admin/app.py** -- APP_REGISTRY entry:
```python
{
    "id": "your-app",
    "name": "Your App Display Name",
    "description": "One-line description",
    "url": "/apps/your-app/",
    "icon": "shield",  # ticket, shield, chart, catalog, cloud, demo, compliance, churn
    "groups": ["analytics", "admin"],  # who can see it
    "author": "Your Name",
},
```

## Streamlit Apps

If you have a Streamlit component, it needs extra nginx config for WebSocket support:

```nginx
location /apps/your-app-demo/ {
    auth_request /_auth;
    proxy_pass http://your-app-streamlit:8501/apps/your-app-demo/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

And run Streamlit with the base URL:
```bash
streamlit run app.py --server.baseUrlPath /apps/your-app-demo --server.port 8501
```

## Quick Checklist

- [ ] Dockerfile builds and runs with `docker build . && docker run -p 8000:8000 .`
- [ ] App works when accessed at a sub-path (not just `/`)
- [ ] No built-in auth (no login pages, no API key prompts)
- [ ] All asset/API URLs are relative
- [ ] Environment variables documented
- [ ] Memory usage estimated

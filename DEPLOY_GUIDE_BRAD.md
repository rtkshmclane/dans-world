# Dan's World -- Deploy Guide for Brad Bierman

## Quick Reference

| What | Value |
|------|-------|
| Server | `octo.rtkwlf.io` |
| SSH port | `2222` |
| SSH user | `bbierman` |
| Web login | `bbierman` / `changeme` (change on first login) |
| Your app | Analytic Stories (`dw-analytic-stories`) |
| App URL | `https://octo.rtkwlf.io/apps/analytic-stories/` |
| Source on server | `/opt/app-sources/analytic_stories/` |
| Orchestration | `/opt/dans-world/` |

## One-Time Setup

### 1. Generate an SSH key (if you don't have one)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_octo -C "bbierman@octo"
```

### 2. Send Sam your public key

```bash
cat ~/.ssh/id_octo.pub
```

Send that output to Sam. He'll add it to your server account.

### 3. Add SSH config for convenience

Add to `~/.ssh/config`:

```
Host octo
    HostName octo.rtkwlf.io
    Port 2222
    User bbierman
    IdentityFile ~/.ssh/id_octo
```

Now you can just `ssh octo` instead of the full command.

### 4. Test connection

```bash
ssh octo "echo connected"
```

### 5. Change your web password

Log in at `https://octo.rtkwlf.io` with `bbierman` / `changeme`, then change your password from the user menu.

## Deploying Your App (Analytic Stories)

Your app source lives at `/opt/app-sources/analytic_stories/` on the server. The deploy process syncs your code there and rebuilds the container.

### Option A: Quick deploy (most common)

```bash
# SSH in and sync your local code to the server
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'node_modules' \
  -e "ssh -p 2222 -i ~/.ssh/id_octo" \
  /path/to/your/analytic_stories/ \
  bbierman@octo.rtkwlf.io:/opt/app-sources/analytic_stories/

# Then rebuild and restart just your container
ssh octo "cd /opt/dans-world && docker compose up -d --build analytic-stories"
```

### Option B: If you pushed to the dans-world repo

```bash
ssh octo "cd /opt/dans-world && git pull && docker compose up -d --build analytic-stories"
```

### Option C: Full stack redeploy (rarely needed)

```bash
ssh octo "cd /opt/dans-world && git pull && docker compose up -d --build"
```

## Useful Commands

```bash
# Check your container status
ssh octo "docker ps --filter name=dw-analytic-stories"

# View your app logs (last 50 lines)
ssh octo "docker logs --tail 50 dw-analytic-stories"

# Follow logs in real-time
ssh octo "docker logs -f dw-analytic-stories"

# Restart without rebuilding
ssh octo "docker restart dw-analytic-stories"

# Check health endpoint
ssh octo "curl -s http://localhost:8089/api/v1/stats | head -20"

# See all running containers
ssh octo "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Check disk usage
ssh octo "df -h / && echo '---' && docker system df"
```

## Your Dockerfile

Your app builds from the Dockerfile at `/opt/app-sources/analytic_stories/Dockerfile`. If you need to change dependencies, build steps, etc., edit that file in your source and rsync it up.

Current Dockerfile expects:
- FastAPI app
- Port 8089
- Health endpoint at `/api/v1/stats`

## Adding a New App

If you build a new app and want it on Dan's World:

1. Create the app with a Dockerfile in its root
2. Tell Sam (or PR to `rtkshmclane/dans-world`) to add:
   - Entry in `registry.yaml`
   - Service in `docker-compose.yml`
   - Nginx location block in `gateway/conf.d/30-apps.conf`
3. Sam will set up the source path and deploy

## Claude Code Users

If you use Claude Code, add this to a `CLAUDE.md` in your app's root:

```markdown
# Analytic Stories

## Deploy

Deploy to Dan's World (octo.rtkwlf.io):

\```bash
# Sync code to server
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'node_modules' \
  -e "ssh -p 2222" \
  ./ bbierman@octo.rtkwlf.io:/opt/app-sources/analytic_stories/

# Rebuild container
ssh octo "cd /opt/dans-world && docker compose up -d --build analytic-stories"
\```

## Architecture

- FastAPI on port 8089
- Container: dw-analytic-stories
- Health: /api/v1/stats
- Runs behind nginx reverse proxy with auth_request to admin service
```

This way Claude Code will know how to deploy for you when you ask it to.

## Troubleshooting

**Container won't start**: Check logs with `docker logs dw-analytic-stories`. Usually a missing dependency or port conflict.

**Build fails**: The Dockerfile runs in the context of `/opt/app-sources/analytic_stories/`. Make sure all files referenced in COPY commands exist.

**502 Bad Gateway**: Your container is either not running or not listening on the expected port (8089). Check `docker ps` and logs.

**Permission denied on rsync**: Make sure your SSH key is set up and you're using port 2222.

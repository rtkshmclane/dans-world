import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import close_db
from routers import detections, search, stats, stories, tactics


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_db()


app = FastAPI(
    title="Analytic Stories Platform",
    description="Detection COE — Attack chain and detection coverage explorer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# API routes under /api/v1
app.include_router(stories.router, prefix="/api/v1")
app.include_router(detections.router, prefix="/api/v1")
app.include_router(tactics.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")

# Serve React static files if available
static_dir = Path(os.getenv("STATIC_DIR", "/app/static"))
if static_dir.exists():
    # Serve static assets (JS, CSS, images) at /assets
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA catch-all: serve index.html for any non-API route
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # If a static file exists at that path, serve it
        file_path = static_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(static_dir / "index.html")

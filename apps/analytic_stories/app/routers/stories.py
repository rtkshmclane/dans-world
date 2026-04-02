from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import get_db
from models.responses import (
    DetectionSummary,
    PaginatedResponse,
    StoryDetail,
    StorySummary,
    TacticResponse,
)

router = APIRouter(prefix="/stories", tags=["stories"])


async def _enrich_story(db, story: dict) -> dict:
    """Add tactics, products, and detection count to a story dict."""
    story_id = story["id"]

    # Tactics
    tactics = []
    async with db.execute(
        """SELECT t.id, t.name, t.url FROM tactics t
           JOIN story_tactics st ON t.id = st.tactic_id
           WHERE st.story_id = ?""",
        (story_id,),
    ) as cur:
        async for row in cur:
            tactics.append(TacticResponse(id=row["id"], name=row["name"], url=row["url"]))

    # Products
    products = []
    async with db.execute(
        """SELECT p.name FROM products p
           JOIN story_products sp ON p.id = sp.product_id
           WHERE sp.story_id = ?""",
        (story_id,),
    ) as cur:
        async for row in cur:
            products.append(row["name"])

    # Detection count
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM story_detections WHERE story_id = ?",
        (story_id,),
    ) as cur:
        row = await cur.fetchone()
        detection_count = row["cnt"]

    return {**story, "tactics": tactics, "products": products, "detection_count": detection_count}


@router.get("", response_model=PaginatedResponse)
async def list_stories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tactic: Optional[str] = None,
    category: Optional[str] = None,
    use_case: Optional[str] = None,
    product: Optional[str] = None,
    q: Optional[str] = None,
):
    db = await get_db()
    conditions = []
    params: list = []

    if category:
        conditions.append("s.category = ?")
        params.append(category)
    if use_case:
        conditions.append("s.use_case = ?")
        params.append(use_case)
    if tactic:
        conditions.append("s.id IN (SELECT story_id FROM story_tactics WHERE tactic_id = ?)")
        params.append(tactic)
    if product:
        conditions.append(
            "s.id IN (SELECT sp.story_id FROM story_products sp JOIN products p ON sp.product_id = p.id WHERE p.name = ?)"
        )
        params.append(product)
    if q:
        conditions.append("s.id IN (SELECT rowid FROM stories_fts WHERE stories_fts MATCH ?)")
        params.append(q)

    where = " AND ".join(conditions)
    where_clause = f"WHERE {where}" if where else ""

    # Count
    async with db.execute(f"SELECT COUNT(*) as cnt FROM stories s {where_clause}", params) as cur:
        total = (await cur.fetchone())["cnt"]

    # Fetch
    offset = (page - 1) * page_size
    async with db.execute(
        f"""SELECT s.id, s.name, s.slug, s.description, s.category, s.use_case,
                   s.status, s.author, s.date_published, s.date_updated
            FROM stories s {where_clause}
            ORDER BY s.name
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ) as cur:
        rows = [dict(row) async for row in cur]

    items = []
    for row in rows:
        enriched = await _enrich_story(db, row)
        items.append(StorySummary(**enriched))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=StoryDetail)
async def get_story(slug: str):
    db = await get_db()

    async with db.execute(
        "SELECT * FROM stories WHERE slug = ?", (slug,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Story not found")

    story = dict(row)
    story["references"] = json.loads(story.pop("references_json", "[]"))
    enriched = await _enrich_story(db, story)

    # Detections
    detections = []
    async with db.execute(
        """SELECT d.id, d.name, d.slug, d.description, d.type, d.severity,
                  d.status, d.author, d.date_published, d.date_updated
           FROM detections d
           JOIN story_detections sd ON d.id = sd.detection_id
           WHERE sd.story_id = ?
           ORDER BY d.name""",
        (story["id"],),
    ) as cur:
        async for drow in cur:
            detections.append(DetectionSummary(**dict(drow)))

    enriched["detections"] = detections
    return StoryDetail(**enriched)

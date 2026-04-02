from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import get_db
from models.responses import (
    DataSourceResponse,
    DetectionDetail,
    DetectionSummary,
    PaginatedResponse,
    StorySummaryBrief,
    TechniqueResponse,
)

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=PaginatedResponse)
async def list_detections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    severity: Optional[str] = None,
    technique: Optional[str] = None,
):
    db = await get_db()
    conditions = []
    params: list = []

    if type:
        conditions.append("d.type = ?")
        params.append(type)
    if severity:
        conditions.append("d.severity = ?")
        params.append(severity)
    if technique:
        conditions.append("d.id IN (SELECT detection_id FROM detection_techniques WHERE technique_id = ?)")
        params.append(technique)

    where = " AND ".join(conditions)
    where_clause = f"WHERE {where}" if where else ""

    async with db.execute(f"SELECT COUNT(*) as cnt FROM detections d {where_clause}", params) as cur:
        total = (await cur.fetchone())["cnt"]

    offset = (page - 1) * page_size
    async with db.execute(
        f"""SELECT d.id, d.name, d.slug, d.description, d.type, d.severity,
                   d.status, d.author, d.date_published, d.date_updated
            FROM detections d {where_clause}
            ORDER BY d.name
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ) as cur:
        items = [DetectionSummary(**dict(row)) async for row in cur]

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=DetectionDetail)
async def get_detection(slug: str):
    db = await get_db()

    async with db.execute("SELECT * FROM detections WHERE slug = ?", (slug,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Detection not found")

    det = dict(row)
    det["references"] = json.loads(det.pop("references_json", "[]"))

    # Techniques
    techniques = []
    async with db.execute(
        """SELECT t.id, t.name, t.tactic_id, t.url FROM techniques t
           JOIN detection_techniques dt ON t.id = dt.technique_id
           WHERE dt.detection_id = ?""",
        (det["id"],),
    ) as cur:
        async for trow in cur:
            techniques.append(TechniqueResponse(**dict(trow)))

    # Data sources
    data_sources = []
    async with db.execute(
        """SELECT ds.id, ds.name, ds.platform FROM data_sources ds
           JOIN detection_data_sources dds ON ds.id = dds.data_source_id
           WHERE dds.detection_id = ?""",
        (det["id"],),
    ) as cur:
        async for dsrow in cur:
            data_sources.append(DataSourceResponse(**dict(dsrow)))

    # Stories this detection belongs to
    stories = []
    async with db.execute(
        """SELECT s.id, s.name, s.slug FROM stories s
           JOIN story_detections sd ON s.id = sd.story_id
           WHERE sd.detection_id = ?""",
        (det["id"],),
    ) as cur:
        async for srow in cur:
            stories.append(StorySummaryBrief(**dict(srow)))

    det["techniques"] = techniques
    det["data_sources"] = data_sources
    det["stories"] = stories
    return DetectionDetail(**det)

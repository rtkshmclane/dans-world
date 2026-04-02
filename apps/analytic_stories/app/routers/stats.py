from __future__ import annotations

from fastapi import APIRouter

from database import get_db
from models.responses import StatsResponse, TacticResponse

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    db = await get_db()

    counts = {}
    for table in ["stories", "detections", "tactics", "techniques", "data_sources", "products"]:
        async with db.execute(f"SELECT COUNT(*) as cnt FROM {table}") as cur:
            counts[table] = (await cur.fetchone())["cnt"]

    # Detections by severity
    by_severity = {}
    async with db.execute("SELECT severity, COUNT(*) as cnt FROM detections GROUP BY severity") as cur:
        async for row in cur:
            by_severity[row["severity"]] = row["cnt"]

    # Detections by type
    by_type = {}
    async with db.execute("SELECT type, COUNT(*) as cnt FROM detections GROUP BY type") as cur:
        async for row in cur:
            by_type[row["type"]] = row["cnt"]

    # Stories by category
    by_category = {}
    async with db.execute("SELECT category, COUNT(*) as cnt FROM stories GROUP BY category") as cur:
        async for row in cur:
            by_category[row["category"]] = row["cnt"]

    # Tactic coverage
    tactic_coverage = []
    async with db.execute(
        """SELECT t.id, t.name, t.url,
                  (SELECT COUNT(*) FROM story_tactics st WHERE st.tactic_id = t.id) as story_count
           FROM tactics t ORDER BY t.id"""
    ) as cur:
        async for row in cur:
            tactic_coverage.append(TacticResponse(**dict(row)))

    return StatsResponse(
        total_stories=counts["stories"],
        total_detections=counts["detections"],
        total_tactics=counts["tactics"],
        total_techniques=counts["techniques"],
        total_data_sources=counts["data_sources"],
        total_products=counts["products"],
        detections_by_severity=by_severity,
        detections_by_type=by_type,
        stories_by_category=by_category,
        tactic_coverage=tactic_coverage,
    )

from __future__ import annotations

from fastapi import APIRouter, Query

from database import get_db
from models.responses import SearchResult

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[SearchResult])
async def search_stories(q: str = Query(..., min_length=1)):
    db = await get_db()
    results = []
    async with db.execute(
        """SELECT s.id, s.name, s.slug, s.description, rank
           FROM stories_fts
           JOIN stories s ON stories_fts.rowid = s.id
           WHERE stories_fts MATCH ?
           ORDER BY rank
           LIMIT 50""",
        (q,),
    ) as cur:
        async for row in cur:
            results.append(SearchResult(**dict(row)))
    return results

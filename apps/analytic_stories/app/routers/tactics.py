from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from database import get_db
from models.responses import DataSourceResponse, ProductResponse, TacticResponse, TechniqueResponse

router = APIRouter(tags=["reference"])


@router.get("/tactics", response_model=list[TacticResponse])
async def list_tactics():
    db = await get_db()
    results = []
    async with db.execute(
        """SELECT t.id, t.name, t.url,
                  (SELECT COUNT(*) FROM story_tactics st WHERE st.tactic_id = t.id) as story_count
           FROM tactics t ORDER BY t.id"""
    ) as cur:
        async for row in cur:
            results.append(TacticResponse(**dict(row)))
    return results


@router.get("/techniques", response_model=list[TechniqueResponse])
async def list_techniques(tactic_id: Optional[str] = None):
    db = await get_db()
    if tactic_id:
        query = "SELECT id, name, tactic_id, url FROM techniques WHERE tactic_id = ? ORDER BY id"
        params = (tactic_id,)
    else:
        query = "SELECT id, name, tactic_id, url FROM techniques ORDER BY id"
        params = ()

    results = []
    async with db.execute(query, params) as cur:
        async for row in cur:
            results.append(TechniqueResponse(**dict(row)))
    return results


@router.get("/data-sources", response_model=list[DataSourceResponse])
async def list_data_sources(platform: Optional[str] = None):
    db = await get_db()
    if platform:
        query = "SELECT id, name, platform FROM data_sources WHERE platform = ? ORDER BY name"
        params = (platform,)
    else:
        query = "SELECT id, name, platform FROM data_sources ORDER BY name"
        params = ()

    results = []
    async with db.execute(query, params) as cur:
        async for row in cur:
            results.append(DataSourceResponse(**dict(row)))
    return results


@router.get("/products", response_model=list[ProductResponse])
async def list_products():
    db = await get_db()
    results = []
    async with db.execute("SELECT id, name FROM products ORDER BY name") as cur:
        async for row in cur:
            results.append(ProductResponse(**dict(row)))
    return results

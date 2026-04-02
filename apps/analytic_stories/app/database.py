from __future__ import annotations

import aiosqlite

from config import DB_PATH

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        try:
            _db = await aiosqlite.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        except Exception:
            _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None

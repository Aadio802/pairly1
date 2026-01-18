"""
Database initialization and connection management
"""
import aiosqlite
from config import settings
from pathlib import Path


async def get_connection():
    """Get database connection with WAL mode"""
    conn = await aiosqlite.connect(settings.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_database():
    """Initialize database schema"""
    schema_path = Path(__file__).parent / "schema.sql"

    conn = await get_connection()
    try:
        with open(schema_path, "r") as f:
            schema = f.read()

        await conn.executescript(schema)
        await conn.commit()
    finally:
        await conn.close()

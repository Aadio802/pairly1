"""
Pet system - Guardian angels for streak protection
"""
from typing import List, Tuple
from db import get_connection
from config import settings


async def add_pet(user_id: int, pet_type: str, saves: int = 1) -> bool:
    """
    Add pet to user
    Returns False if max pets reached
    """
    async with await get_connection() as conn:
        # Check current pet count
        result = await conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id = ?",
            (user_id,)
        )
        count = (await result.fetchone())[0]
        
        if count >= settings.MAX_PETS:
            return False
        
        # Add pet
        await conn.execute(
            """
            INSERT INTO pets (user_id, pet_type, saves_remaining)
            VALUES (?, ?, ?)
            """,
            (user_id, pet_type, saves)
        )
        await conn.commit()
        return True


async def use_pet(user_id: int) -> bool:
    """
    Use one pet to save streak
    Returns True if pet was used, False if no pets available
    """
    async with await get_connection() as conn:
        # Get oldest pet
        result = await conn.execute(
            """
            SELECT id, saves_remaining
            FROM pets
            WHERE user_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_id,)
        )
        row = await result.fetchone()
        
        if not row:
            return False
        
        pet_id, saves = row
        
        if saves > 1:
            # Decrement saves
            await conn.execute(
                "UPDATE pets SET saves_remaining = saves_remaining - 1 WHERE id = ?",
                (pet_id,)
            )
        else:
            # Remove pet
            await conn.execute(
                "DELETE FROM pets WHERE id = ?",
                (pet_id,)
            )
        
        await conn.commit()
        return True


async def get_pets(user_id: int) -> List[Tuple[int, str, int]]:
    """Get all pets for user (id, type, saves)"""
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT id, pet_type, saves_remaining
            FROM pets
            WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,)
        )
        return await result.fetchall()


async def get_pet_count(user_id: int) -> int:
    """Get total pet count"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id = ?",
            (user_id,)
        )
        return (await result.fetchone())[0]

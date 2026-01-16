"""
Sunflower ledger-based tracking
Sources: streak, game, gift, rating
"""
from typing import Dict
from db import get_connection


async def add_sunflowers(user_id: int, amount: int, source: str):
    """Add sunflowers to user's ledger"""
    if amount <= 0:
        return
    
    async with await get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO sunflower_ledger (user_id, source, amount)
            VALUES (?, ?, ?)
            """,
            (user_id, source, amount)
        )
        await conn.commit()


async def remove_sunflowers(user_id: int, amount: int, source: str) -> int:
    """
    Remove sunflowers from specific source
    Returns actual amount removed
    """
    if amount <= 0:
        return 0
    
    async with await get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO sunflower_ledger (user_id, source, amount)
            VALUES (?, ?, ?)
            """,
            (user_id, source, -amount)
        )
        await conn.commit()
        return amount


async def get_sunflower_balance(user_id: int) -> Dict[str, int]:
    """
    Get sunflower balance by source
    Returns: {source: amount, 'total': total}
    """
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT source, SUM(amount)
            FROM sunflower_ledger
            WHERE user_id = ?
            GROUP BY source
            """,
            (user_id,)
        )
        rows = await result.fetchall()
        
        balance = {'streak': 0, 'game': 0, 'gift': 0, 'rating': 0}
        
        for row in rows:
            source, amount = row
            balance[source] = max(0, amount)  # Never negative
        
        balance['total'] = sum(balance.values())
        return balance


async def deduct_sunflowers_smart(user_id: int, amount: int) -> bool:
    """
    Deduct sunflowers intelligently across sources
    Priority: game > gift > rating > streak
    Returns True if successful
    """
    balance = await get_sunflower_balance(user_id)
    
    if balance['total'] < amount:
        return False
    
    remaining = amount
    
    # Deduct from game first
    if balance['game'] > 0:
        deduct = min(balance['game'], remaining)
        await remove_sunflowers(user_id, deduct, 'game')
        remaining -= deduct
    
    # Then gift
    if remaining > 0 and balance['gift'] > 0:
        deduct = min(balance['gift'], remaining)
        await remove_sunflowers(user_id, deduct, 'gift')
        remaining -= deduct
    
    # Then rating
    if remaining > 0 and balance['rating'] > 0:
        deduct = min(balance['rating'], remaining)
        await remove_sunflowers(user_id, deduct, 'rating')
        remaining -= deduct
    
    # Finally streak
    if remaining > 0 and balance['streak'] > 0:
        deduct = min(balance['streak'], remaining)
        await remove_sunflowers(user_id, deduct, 'streak')
        remaining -= deduct
    
    return True


async def reset_streak_sunflowers(user_id: int):
    """Remove all streak-sourced sunflowers"""
    balance = await get_sunflower_balance(user_id)
    if balance['streak'] > 0:
        await remove_sunflowers(user_id, balance['streak'], 'streak')

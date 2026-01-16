"""
User state management with strict FSM transitions
States: NEW → AGREED → IDLE → SEARCHING → CHATTING → RATING → IDLE
"""
from typing import Optional
from datetime import datetime
from db import get_connection


class UserState:
    NEW = "NEW"
    AGREED = "AGREED"
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    CHATTING = "CHATTING"
    RATING = "RATING"


async def user_exists(user_id: int) -> bool:
    """Check if user exists"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await result.fetchone() is not None


async def create_user(user_id: int, gender: str):
    """Create new user in NEW state"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, gender, current_state)
            VALUES (?, ?, ?)
            """,
            (user_id, gender, UserState.NEW)
        )
        await conn.commit()


async def get_user_state(user_id: int) -> Optional[str]:
    """Get current user state"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT current_state FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await result.fetchone()
        return row[0] if row else None


async def transition_state(user_id: int, from_state: str, to_state: str) -> bool:
    """Atomic state transition with validation"""
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET current_state = ?, last_active = CURRENT_TIMESTAMP
            WHERE user_id = ? AND current_state = ?
            """,
            (to_state, user_id, from_state)
        )
        await conn.commit()
        return result.rowcount > 0


async def set_state(user_id: int, state: str):
    """Force set state (use with caution)"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            UPDATE users
            SET current_state = ?, last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (state, user_id)
        )
        await conn.commit()


async def get_user(user_id: int):
    """Get full user record"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await result.fetchone()


async def set_partner(user_id: int, partner_id: Optional[int]):
    """Set user's current partner"""
    async with await get_connection() as conn:
        await conn.execute(
            "UPDATE users SET partner_id = ? WHERE user_id = ?",
            (partner_id, user_id)
        )
        await conn.commit()


async def get_partner(user_id: int) -> Optional[int]:
    """Get user's current partner"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT partner_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await result.fetchone()
        return row[0] if row and row[0] else None


async def is_premium(user_id: int) -> bool:
    """Check if user has active premium"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT premium_until FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await result.fetchone()
        if row and row[0]:
            premium_until = datetime.fromisoformat(row[0])
            return premium_until > datetime.now()
        return False


async def update_premium(user_id: int, days: int):
    """Update premium status"""
    from datetime import timedelta
    premium_until = datetime.now() + timedelta(days=days)
    
    async with await get_connection() as conn:
        await conn.execute(
            "UPDATE users SET premium_until = ? WHERE user_id = ?",
            (premium_until.isoformat(), user_id)
        )
        await conn.commit()


async def get_premium_remaining_days(user_id: int) -> int:
    """Get remaining premium days"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT premium_until FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await result.fetchone()
        if row and row[0]:
            premium_until = datetime.fromisoformat(row[0])
            if premium_until > datetime.now():
                return (premium_until - datetime.now()).days
        return 0


async def can_use_temp_premium(user_id: int) -> bool:
    """Check if user can use temp premium"""
    from config import settings
    
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT temp_premium_last_used FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await result.fetchone()
        
        if not row or not row[0]:
            return True
        
        last_used = datetime.fromisoformat(row[0])
        days_since = (datetime.now() - last_used).days
        return days_since >= settings.TEMP_PREMIUM_COOLDOWN_DAYS


async def use_temp_premium(user_id: int):
    """Mark temp premium as used"""
    from config import settings
    
    async with await get_connection() as conn:
        await conn.execute(
            "UPDATE users SET temp_premium_last_used = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        await conn.commit()
    
    await update_premium(user_id, settings.TEMP_PREMIUM_DAYS)

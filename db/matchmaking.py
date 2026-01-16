"""
Matchmaking database operations
Table-backed waiting pool with atomic transactions
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from db import get_connection
from config import settings


async def join_waiting_pool(
    user_id: int,
    gender: str,
    is_premium: bool,
    rating: Optional[float] = None,
    rating_count: int = 0,
    gender_pref: Optional[str] = None
):
    """Add user to waiting pool"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            INSERT OR REPLACE INTO waiting_users 
            (user_id, gender, is_premium, rating, rating_count, gender_preference, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, gender, 1 if is_premium else 0, rating, rating_count, gender_pref)
        )
        await conn.commit()


async def leave_waiting_pool(user_id: int):
    """Remove user from waiting pool"""
    async with await get_connection() as conn:
        await conn.execute(
            "DELETE FROM waiting_users WHERE user_id = ?",
            (user_id,)
        )
        await conn.commit()


async def get_waiting_candidates(user_id: int, my_gender: str) -> list:
    """Get candidates from waiting pool excluding recent matches"""
    cutoff_time = datetime.now() - timedelta(seconds=settings.MATCH_HISTORY_WINDOW_SECONDS)
    
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT w.user_id, w.gender, w.is_premium, w.rating, w.rating_count, w.joined_at
            FROM waiting_users w
            WHERE w.user_id != ?
            AND w.user_id NOT IN (
                SELECT partner_id
                FROM match_history
                WHERE user_id = ?
                AND last_matched_at > ?
            )
            """,
            (user_id, user_id, cutoff_time.isoformat())
        )
        return await result.fetchall()


async def create_match_atomic(user_a: int, user_b: int) -> int:
    """
    Atomic match creation:
    1. Remove both from waiting pool
    2. Create active chat
    3. Update user states
    4. Record match history
    
    Returns chat_id on success, 0 on failure
    """
    async with await get_connection() as conn:
        try:
            # Start transaction
            await conn.execute("BEGIN IMMEDIATE")
            
            # Remove from waiting pool
            await conn.execute(
                "DELETE FROM waiting_users WHERE user_id IN (?, ?)",
                (user_a, user_b)
            )
            
            # Create active chat
            cursor = await conn.execute(
                """
                INSERT INTO active_chats (user_a, user_b, started_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (user_a, user_b)
            )
            chat_id = cursor.lastrowid
            
            # Update user states
            await conn.execute(
                """
                UPDATE users
                SET partner_id = ?, current_state = 'CHATTING'
                WHERE user_id = ?
                """,
                (user_b, user_a)
            )
            
            await conn.execute(
                """
                UPDATE users
                SET partner_id = ?, current_state = 'CHATTING'
                WHERE user_id = ?
                """,
                (user_a, user_b)
            )
            
            # Record match history (both directions)
            now = datetime.now().isoformat()
            await conn.execute(
                """
                INSERT OR REPLACE INTO match_history (user_id, partner_id, last_matched_at)
                VALUES (?, ?, ?)
                """,
                (user_a, user_b, now)
            )
            await conn.execute(
                """
                INSERT OR REPLACE INTO match_history (user_id, partner_id, last_matched_at)
                VALUES (?, ?, ?)
                """,
                (user_b, user_a, now)
            )
            
            # Commit transaction
            await conn.commit()
            return chat_id
            
        except Exception as e:
            # Rollback on any error
            await conn.rollback()
            print(f"Match creation failed: {e}")
            return 0


async def end_chat_atomic(user_a: int, user_b: int):
    """
    Atomic chat ending:
    1. End active game if exists
    2. Remove active chat
    3. Clear partner references
    4. Create pending ratings
    """
    async with await get_connection() as conn:
        try:
            await conn.execute("BEGIN IMMEDIATE")
            
            # Get chat_id
            result = await conn.execute(
                """
                SELECT chat_id FROM active_chats
                WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)
                """,
                (user_a, user_b, user_b, user_a)
            )
            chat_row = await result.fetchone()
            
            if chat_row:
                chat_id = chat_row[0]
                
                # End active game
                await conn.execute(
                    """
                    UPDATE active_games
                    SET ended_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ? AND winner_id IS NULL
                    """,
                    (chat_id,)
                )
                
                # Delete active chat
                await conn.execute(
                    "DELETE FROM active_chats WHERE chat_id = ?",
                    (chat_id,)
                )
            
            # Clear partners
            await conn.execute(
                "UPDATE users SET partner_id = NULL WHERE user_id IN (?, ?)",
                (user_a, user_b)
            )
            
            # Create pending ratings
            await conn.execute(
                """
                INSERT INTO pending_ratings (rater_id, rated_user_id)
                VALUES (?, ?), (?, ?)
                """,
                (user_a, user_b, user_b, user_a)
            )
            
            await conn.commit()
            
        except Exception as e:
            await conn.rollback()
            print(f"Chat end failed: {e}")


async def get_chat_id(user_id: int) -> Optional[int]:
    """Get active chat_id for user"""
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT chat_id FROM active_chats
            WHERE user_a = ? OR user_b = ?
            """,
            (user_id, user_id)
        )
        row = await result.fetchone()
        return row[0] if row else None


async def is_in_waiting_pool(user_id: int) -> bool:
    """Check if user is in waiting pool"""
    async with await get_connection() as conn:
        result = await conn.execute(
            "SELECT 1 FROM waiting_users WHERE user_id = ?",
            (user_id,)
        )
        return await result.fetchone() is not None

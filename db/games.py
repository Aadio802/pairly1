"""
Game state management - persistent game storage
"""
from typing import Optional, Dict, Any
import json
from db import get_connection


async def create_game(
    chat_id: int,
    game_type: str,
    player1_id: int,
    player2_id: int,
    bet_amount: int,
    initial_state: Dict[str, Any]
) -> int:
    """Create new game, returns game_id"""
    async with await get_connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO active_games 
            (chat_id, game_type, player1_id, player2_id, bet_amount, game_state, current_turn)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                game_type,
                player1_id,
                player2_id,
                bet_amount,
                json.dumps(initial_state),
                player1_id
            )
        )
        await conn.commit()
        return cursor.lastrowid


async def get_active_game(chat_id: int) -> Optional[Dict[str, Any]]:
    """Get active game for chat"""
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT game_id, game_type, player1_id, player2_id, bet_amount, game_state, current_turn
            FROM active_games
            WHERE chat_id = ? AND winner_id IS NULL
            """,
            (chat_id,)
        )
        row = await result.fetchone()
        
        if not row:
            return None
        
        return {
            'game_id': row[0],
            'game_type': row[1],
            'player1_id': row[2],
            'player2_id': row[3],
            'bet_amount': row[4],
            'state': json.loads(row[5]),
            'current_turn': row[6]
        }


async def update_game_state(game_id: int, new_state: Dict[str, Any], current_turn: int):
    """Update game state and current turn"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            UPDATE active_games
            SET game_state = ?, current_turn = ?
            WHERE game_id = ?
            """,
            (json.dumps(new_state), current_turn, game_id)
        )
        await conn.commit()


async def end_game(game_id: int, winner_id: Optional[int]):
    """Mark game as ended"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            UPDATE active_games
            SET winner_id = ?, ended_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
            """,
            (winner_id, game_id)
        )
        await conn.commit()


async def force_end_active_game(chat_id: int):
    """Force end any active game (when chat ends)"""
    async with await get_connection() as conn:
        await conn.execute(
            """
            UPDATE active_games
            SET ended_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND winner_id IS NULL
            """,
            (chat_id,)
        )
        await conn.commit()


async def get_game_by_id(game_id: int) -> Optional[Dict[str, Any]]:
    """Get game by ID"""
    async with await get_connection() as conn:
        result = await conn.execute(
            """
            SELECT game_type, player1_id, player2_id, bet_amount, game_state, current_turn, winner_id
            FROM active_games
            WHERE game_id = ?
            """,
            (game_id,)
        )
        row = await result.fetchone()
        
        if not row:
            return None
        
        return {
            'game_type': row[0],
            'player1_id': row[1],
            'player2_id': row[2],
            'bet_amount': row[3],
            'state': json.loads(row[4]),
            'current_turn': row[5],
            'winner_id': row[6]
        }

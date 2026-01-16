"""
Handler registration
"""
from aiogram import Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Import database modules
from db.users import (
    user_exists, create_user, get_user_state, 
    transition_state, UserState, get_partner, is_premium
)
from db.matchmaking import (
    join_waiting_pool, leave_waiting_pool, 
    is_in_waiting_pool, end_chat_atomic
)
from db.ratings import get_average_rating, get_pending_ratings, add_rating
from db.sunflowers import get_sunflower_balance, add_sunflowers
from db.streaks import update_streak, get_streak_days
from db.pets import get_pets, add_pet, get_pet_count
from services.matcher import find_best_match, create_match
from config import settings

# Create routers
start_router = Router()
matchmaking_router = Router()
rating_router = Router()


# ============ START HANDLER ============
@start_router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start - show welcome or act as /find"""
    user_id = message.from_user.id
    
    if not await user_exists(user_id):
        # NEW user - show welcome
        welcome_text = (
            "🌻 Welcome to Pairly! 🌻\n\n"
            "Anonymous chatting with strangers\n\n"
            "⚠️ Important:\n"
            "• You may encounter unfiltered content\n"
            "• All chats are monitored for safety\n"
            "• Premium users get priority matching\n"
            "• Earn Sunflowers 🌻 through:\n"
            "  - Maintaining streaks 🔥\n"
            "  - Winning games 🎮\n"
            "  - Good ratings ⭐\n"
            "  - Gifts from others\n\n"
            "By using /find or /next, you agree to these terms.\n\n"
            "First, select your gender:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="Male", callback_data="gender:male")
        builder.button(text="Female", callback_data="gender:female")
        builder.adjust(2)
        
        await message.answer(welcome_text, reply_markup=builder.as_markup())
    else:
        # Existing user - behave as /find
        await cmd_find(message)


@start_router.callback_query(F.data.startswith("gender:"))
async def select_gender(callback: CallbackQuery):
    """Handle gender selection"""
    user_id = callback.from_user.id
    gender = callback.data.split(":")[1]
    
    # Create user
    await create_user(user_id, gender)
    await transition_state(user_id, UserState.NEW, UserState.AGREED)
    await transition_state(user_id, UserState.AGREED, UserState.IDLE)
    
    await callback.message.edit_text(
        f"✅ Gender set to: {gender.capitalize()}\n\n"
        "Ready to chat! Use /find to start.\n\n"
        "Commands:\n"
        "/find - Find a partner\n"
        "/next - Skip partner\n"
        "/stop - Leave chat\n"
        "/how - Learn features"
    )
    await callback.answer()


# ============ MATCHMAKING HANDLERS ============
@matchmaking_router.message(Command("find"))
async def cmd_find(message: Message):
    """Find a chat partner"""
    user_id = message.from_user.id
    
    if not await user_exists(user_id):
        await message.answer("Please use /start first.")
        return
    
    state = await get_user_state(user_id)
    
    # State validation
    if state == UserState.CHATTING:
        await message.answer("You are already in a chat. Use /next or /stop.")
        return
    
    if state == UserState.SEARCHING:
        await message.answer("Already searching for a partner…")
        return
    
    # Update streak
    await update_streak(user_id)
    
    # Check for premium and gender preference
    user_is_premium = await is_premium(user_id)
    
    if user_is_premium:
        builder = InlineKeyboardBuilder()
        builder.button(text="Any Gender", callback_data="pref:any")
        builder.button(text="Male", callback_data="pref:male")
        builder.button(text="Female", callback_data="pref:female")
        builder.adjust(1)
        
        await message.answer(
            "🌟 Premium: Choose gender preference",
            reply_markup=builder.as_markup()
        )
    else:
        await start_matchmaking(message.bot, user_id, None)


@matchmaking_router.callback_query(F.data.startswith("pref:"))
async def select_preference(callback: CallbackQuery):
    """Handle premium gender preference"""
    user_id = callback.from_user.id
    pref = callback.data.split(":")[1]
    gender_pref = None if pref == "any" else pref
    
    await callback.message.delete()
    await start_matchmaking(callback.bot, user_id, gender_pref)
    await callback.answer()


async def start_matchmaking(bot, user_id: int, gender_pref: str = None):
    """Start matchmaking process"""
    from db.users import get_user
    
    # Transition to SEARCHING
    success = await transition_state(user_id, UserState.IDLE, UserState.SEARCHING)
    if not success:
        await bot.send_message(user_id, "Failed to start search. Try again.")
        return
    
    # Get user data
    user = await get_user(user_id)
    gender = user['gender']
    user_is_premium = await is_premium(user_id)
    rating_info = await get_average_rating(user_id)
    
    # Add to waiting pool
    await join_waiting_pool(
        user_id,
        gender,
        user_is_premium,
        rating_info[0] if rating_info else None,
        rating_info[1] if rating_info else 0,
        gender_pref
    )
    
    # Try to find match
    partner_id = await find_best_match(user_id, gender, gender_pref)
    
    if partner_id:
        # Create match
        success, chat_id = await create_match(user_id, partner_id)
        
        if success:
            await notify_match(bot, user_id, partner_id)
        else:
            await bot.send_message(user_id, "🔍 Searching for a partner…")
    else:
        await bot.send_message(user_id, "🔍 Searching for a partner…")


async def notify_match(bot, user_a: int, user_b: int):
    """Notify both users of match"""
    rating_a = await get_average_rating(user_a)
    rating_b = await get_average_rating(user_b)
    
    msg_a = "✅ Partner found — "
    msg_a += f"⭐ {rating_b[0]} rated by {rating_b[1]} users" if rating_b else "New user (no ratings yet)"
    
    msg_b = "✅ Partner found — "
    msg_b += f"⭐ {rating_a[0]} rated by {rating_a[1]} users" if rating_a else "New user (no ratings yet)"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Next Partner", callback_data="next")
    builder.button(text="Stop Chat", callback_data="stop")
    builder.adjust(2)
    
    await bot.send_message(user_a, msg_a, reply_markup=builder.as_markup())
    await bot.send_message(user_b, msg_b, reply_markup=builder.as_markup())


@matchmaking_router.message(Command("next"))
@matchmaking_router.callback_query(F.data == "next")
async def cmd_next(event):
    """Skip to next partner"""
    user_id = event.from_user.id
    message = event.message if hasattr(event, 'message') else event
    
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        await message.answer("You're not in a chat. Use /find.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    
    # End chat atomically
    await end_chat_atomic(user_id, partner_id)
    
    # Update states
    await transition_state(user_id, UserState.CHATTING, UserState.RATING)
    await transition_state(partner_id, UserState.CHATTING, UserState.RATING)
    
    # Notify partner
    await message.bot.send_message(partner_id, "👋 Partner left the chat.")
    
    # Show rating for both
    await show_rating_prompt(message.bot, user_id, partner_id)
    await show_rating_prompt(message.bot, partner_id, user_id)
    
    # Start new search
    await transition_state(user_id, UserState.RATING, UserState.IDLE)
    await start_matchmaking(message.bot, user_id)
    
    if isinstance(event, CallbackQuery):
        await event.answer()


@matchmaking_router.message(Command("stop"))
@matchmaking_router.callback_query(F.data == "stop")
async def cmd_stop(event):
    """Stop chatting"""
    user_id = event.from_user.id
    message = event.message if hasattr(event, 'message') else event
    
    state = await get_user_state(user_id)
    
    if state == UserState.CHATTING:
        partner_id = await get_partner(user_id)
        
        # End chat
        await end_chat_atomic(user_id, partner_id)
        
        # Update states
        await transition_state(user_id, UserState.CHATTING, UserState.RATING)
        await transition_state(partner_id, UserState.CHATTING, UserState.RATING)
        
        # Notify
        await message.bot.send_message(partner_id, "👋 Partner left the chat.")
        
        # Ratings
        await show_rating_prompt(message.bot, user_id, partner_id)
        await show_rating_prompt(message.bot, partner_id, user_id)
        
        # Back to idle
        await transition_state(user_id, UserState.RATING, UserState.IDLE)
        await message.answer("✅ Left chat. Use /find to start again.")
        
    elif state == UserState.SEARCHING:
        await leave_waiting_pool(user_id)
        await transition_state(user_id, UserState.SEARCHING, UserState.IDLE)
        await message.answer("✅ Search stopped.")
    
    if isinstance(event, CallbackQuery):
        await event.answer()


# ============ RATING HANDLERS ============
async def show_rating_prompt(bot, rater_id: int, rated_user_id: int):
    """Show rating prompt"""
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text=f"{i} ⭐", callback_data=f"rate:{rated_user_id}:{i}")
    builder.adjust(5)
    
    await bot.send_message(
        rater_id,
        "Please rate your last partner:",
        reply_markup=builder.as_markup()
    )


@rating_router.callback_query(F.data.startswith("rate:"))
async def handle_rating(callback: CallbackQuery):
    """Handle rating submission"""
    parts = callback.data.split(":")
    rated_user_id = int(parts[1])
    rating = int(parts[2])
    user_id = callback.from_user.id
    
    # Save rating
    await add_rating(rated_user_id, user_id, rating)
    
    # Award sunflowers
    if rating >= 4:
        await add_sunflowers(user_id, 10, 'rating')
        await add_sunflowers(rated_user_id, 20, 'rating')
    
    await callback.message.edit_text("✅ Thanks for your rating!")
    
    # Check if done rating
    pending = await get_pending_ratings(user_id)
    if not pending:
        await transition_state(user_id, UserState.RATING, UserState.IDLE)
    
    await callback.answer()


def register_all_handlers(dp: Dispatcher):
    """Register all handlers"""
    dp.include_router(start_router)
    dp.include_router(matchmaking_router)
    dp.include_router(rating_router)

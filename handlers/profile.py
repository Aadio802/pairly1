"""
Profile, pets, garden, and info handlers
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.users import get_user, is_premium
from db.sunflowers import get_sunflower_balance
from db.ratings import get_average_rating
from db.streaks import get_streak_days
from db.pets import get_pets, add_pet, get_pet_count
from services.garden import get_garden, create_garden, harvest_garden, has_garden
from services.premium import is_temp_premium_eligible
from config import settings

router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Show user profile"""
    user_id = message.from_user.id
    
    user = await get_user(user_id)
    if not user:
        await message.answer("Please use /start first.")
        return
    
    # Get stats
    balance = await get_sunflower_balance(user_id)
    rating_info = await get_average_rating(user_id)
    streak_days = await get_streak_days(user_id)
    pets = await get_pets(user_id)
    garden = await get_garden(user_id)
    
    # Build profile text
    gender = user['gender'].capitalize()
    
    # Premium status
    user_is_premium = await is_premium(user_id)
    if user_is_premium:
        from db.users import get_premium_remaining_days
        days = await get_premium_remaining_days(user_id)
        premium_text = f"✨ Premium ({days} days left)"
    else:
        premium_text = "Free"
    
    # Rating
    if rating_info:
        rating_text = f"⭐ {rating_info[0]} ({rating_info[1]} ratings)"
    else:
        rating_text = "⭐ No ratings yet"
    
    # Streak
    if streak_days >= 30:
        streak_text = f"🔥 {streak_days} days (2x multiplier)"
    elif streak_days >= 7:
        streak_text = f"🔥 {streak_days} days (1.5x multiplier)"
    else:
        streak_text = f"🔥 {streak_days} days"
    
    # Sunflowers
    sf_text = (
        f"🌻 Total: {balance['total']}\n"
        f"  • Streak: {balance['streak']}\n"
        f"  • Games: {balance['game']}\n"
        f"  • Gifts: {balance['gift']}\n"
        f"  • Ratings: {balance['rating']}"
    )
    
    # Pets
    if pets:
        pet_texts = [f"{p[1]} (×{p[2]})" for p in pets]
        pet_text = f"🐾 Pets: {', '.join(pet_texts)}"
    else:
        pet_text = "🐾 No pets"
    
    # Garden
    if garden:
        garden_text = f"🌱 Garden: Level {garden[0]}"
    else:
        garden_text = "🌱 No garden"
    
    profile_text = (
        f"👤 Your Profile\n\n"
        f"Gender: {gender}\n"
        f"Status: {premium_text}\n"
        f"{rating_text}\n"
        f"{streak_text}\n\n"
        f"{sf_text}\n\n"
        f"{pet_text}\n"
        f"{garden_text}"
    )
    
    # Buttons
    builder = InlineKeyboardBuilder()
    
    if user_is_premium:
        builder.button(text="🐾 Buy Pet", callback_data="buy_pet_menu")
        
        # Garden buttons
        if not await has_garden(user_id):
            # Check if temp premium
            is_temp = is_temp_premium_eligible(
                user_id,
                user['premium_until'],
                user['temp_premium_last_used']
            )
            if not is_temp:
                builder.button(text="🌱 Create Garden", callback_data="create_garden")
        else:
            builder.button(text="🌱 Harvest Garden", callback_data="harvest_garden")
    
    builder.adjust(1)
    
    await message.answer(profile_text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "buy_pet_menu")
async def buy_pet_menu_callback(callback: CallbackQuery):
    """Show pet purchase menu"""
    user_id = callback.from_user.id
    
    # Check pet count
    count = await get_pet_count(user_id)
    if count >= settings.MAX_PETS:
        await callback.answer(
            f"You already have maximum {settings.MAX_PETS} pets!",
            show_alert=True
        )
        return
    
    builder = InlineKeyboardBuilder()
    for pet_type in settings.PET_TYPES:
        builder.button(text=pet_type, callback_data=f"buy_pet:{pet_type}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "🐾 Choose a pet:\n\n"
        "Each pet saves your streak once when you miss a day.",
        reply_markup=builder.as_markup()
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("buy_pet:"))
async def buy_pet_callback(callback: CallbackQuery):
    """Purchase a pet"""
    pet_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    success = await add_pet(user_id, pet_type, 1)
    
    if success:
        await callback.message.edit_text(
            f"✅ You got a {pet_type}! 🐾\n\n"
            "Your pet will protect your streak once."
        )
    else:
        await callback.message.edit_text("❌ Failed to add pet. Maximum reached.")
    
    await callback.answer()


@router.callback_query(F.data == "create_garden")
async def create_garden_callback(callback: CallbackQuery):
    """Create a garden"""
    user_id = callback.from_user.id
    
    success = await create_garden(user_id)
    
    if success:
        await callback.message.edit_text(
            "🌱 Garden created!\n\n"
            "Level 1: Generates 20 🌻 per day\n\n"
            "Keep your streak to level up:\n"
            "• Level 2: 40 🌻/day\n"
            "• Level 3: 60 🌻/day\n\n"
            "⚠️ Missing a day downgrades your garden.\n"
            "Losing streak completely destroys it!"
        )
    else:
        await callback.message.edit_text("❌ Failed to create garden.")
    
    await callback.answer()


@router.callback_query(F.data == "harvest_garden")
async def harvest_garden_callback(callback: CallbackQuery):
    """Harvest garden"""
    user_id = callback.from_user.id
    
    reward = await harvest_garden(user_id)
    
    if reward:
        await callback.answer(f"Harvested {reward} 🌻!", show_alert=True)
    else:
        await callback.answer("Already harvested today!", show_alert=True)


@router.message(Command("how"))
async def cmd_how(message: Message):
    """Explain features"""
    text = (
        "🌻 Pairly Features Guide 🌻\n\n"
        
        "💰 SUNFLOWERS\n"
        "Virtual currency earned through:\n"
        "• Daily streaks 🔥\n"
        "• Winning games 🎮\n"
        "• Good ratings ⭐\n"
        "• Gifts from users\n\n"
        
        "🔥 STREAKS\n"
        "• Start after 3 consecutive days\n"
        "• 7 days: 1.5× sunflowers\n"
        "• 30 days: 2× sunflowers\n"
        "• Miss a day: streak resets\n"
        "• Pets can save your streak!\n\n"
        
        "🐾 PETS (Guardian Angels)\n"
        "• Protect from losing streaks\n"
        "• Max 7 pets per user\n"
        "• Auto-consumed when used\n"
        "• Premium users: buy anytime\n"
        "• Free users: only during temp premium\n\n"
        
        "🎮 GAMES (Premium)\n"
        "• Tic Tac Toe\n"
        "• Word Chain (Easy/Hard)\n"
        "• Hangman\n"
        "• Optional betting with sunflowers\n"
        "• Only playable during active chat\n\n"
        
        "⭐ PREMIUM\n"
        "• Priority matching\n"
        "• Gender preference\n"
        "• 5 links per day\n"
        "• Garden creation\n"
        "• Buy pets anytime\n"
        "• Fewer repeat matches\n\n"
        
        "🌱 GARDEN (Premium)\n"
        "• 3 levels: 20/40/60 🌻 per day\n"
        "• Passive sunflower generation\n"
        "• Downgrades if you miss a day\n"
        "• Destroyed on full streak loss\n\n"
        
        "⏰ TEMP PREMIUM\n"
        "• 3 days for 1000 🌻\n"
        "• Once every 15 days\n"
        "• Access games and pets\n"
        "• No garden creation\n\n"
        
        "Use /find to start chatting!"
    )
    
    await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Show bot statistics"""
    from db.admin import get_stats
    
    stats = await get_stats()
    
    text = (
        f"📊 Pairly Statistics\n\n"
        f"Total users: {stats['total_users']}\n"
        f"Premium users: {stats['premium_users']}\n"
        f"Active chats: {stats['active_chats']}\n"
        f"Searching: {stats['searching']}\n"
        f"Total ratings: {stats['total_ratings']}\n"
        f"Total games: {stats['total_games']}"
    )
    
    await message.answer(text)

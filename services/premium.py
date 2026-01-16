"""
Premium subscription handler
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import database as db
from datetime import datetime, timedelta
from config import settings

router = Router()


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    """Show premium options"""
    user_id = message.from_user.id
    
    # Check current premium status
    is_user_premium = await db.is_premium(user_id)
    
    if is_user_premium:
        user_data = await db.get_user(user_id)
        premium_until = datetime.fromisoformat(user_data[4])
        days_left = (premium_until - datetime.now()).days
        
        await message.answer(
            f"✨ You are a Premium member!\n\n"
            f"Days remaining: {days_left}\n\n"
            "Premium Benefits:\n"
            "• Priority matching with high-rated users\n"
            "• Choose gender preference\n"
            "• Share up to 5 links per day\n"
            "• Create a Garden (passive sunflowers)\n"
            "• Buy pets anytime\n"
            "• Better matching algorithm"
        )
        return
    
    # Show purchase options
    text = (
        "⭐ Become a Premium Member! ⭐\n\n"
        "Premium Benefits:\n"
        "• Priority matching with high-rated users\n"
        "• Choose gender preference\n"
        "• Share up to 5 links per day\n"
        "• Create a Garden (passive sunflowers)\n"
        "• Buy pets anytime\n"
        "• Better matching algorithm\n\n"
        "Select a plan:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"7 days - {settings.PREMIUM_7_DAYS} ⭐", callback_data="buy_premium:7")
    builder.button(text=f"30 days - {settings.PREMIUM_30_DAYS} ⭐", callback_data="buy_premium:30")
    builder.button(text=f"90 days - {settings.PREMIUM_90_DAYS} ⭐ (+14 days FREE)", callback_data="buy_premium:90")
    builder.button(text=f"365 days - {settings.PREMIUM_365_DAYS} ⭐ (+14 days FREE)", callback_data="buy_premium:365")
    builder.adjust(1)
    
    # Also show temp premium option
    sunflowers = await db.get_sunflowers(user_id)
    user_data = await db.get_user(user_id)
    temp_last_used = user_data[5]
    
    can_use_temp = True
    if temp_last_used:
        last_used = datetime.fromisoformat(temp_last_used)
        days_since = (datetime.now() - last_used).days
        if days_since < settings.TEMP_PREMIUM_COOLDOWN:
            can_use_temp = False
            days_left = settings.TEMP_PREMIUM_COOLDOWN - days_since
    
    if can_use_temp and sunflowers['total'] >= settings.TEMP_PREMIUM_COST:
        builder.button(
            text=f"🌻 3-day temp premium ({settings.TEMP_PREMIUM_COST} sunflowers)",
            callback_data="buy_temp_premium"
        )
    
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("buy_premium:"))
async def buy_premium(callback: CallbackQuery):
    """Handle premium purchase via Telegram Stars"""
    days = int(callback.data.split(":")[1])
    
    # Map days to prices
    price_map = {
        7: settings.PREMIUM_7_DAYS,
        30: settings.PREMIUM_30_DAYS,
        90: settings.PREMIUM_90_DAYS,
        365: settings.PREMIUM_365_DAYS
    }
    
    price = price_map.get(days, settings.PREMIUM_7_DAYS)
    
    # Add bonus days for longer plans
    actual_days = days + (14 if days >= 90 else 0)
    
    # Create invoice
    title = f"Pairly Premium - {days} days"
    description = f"Premium subscription for {actual_days} days"
    payload = f"premium_{days}_{callback.from_user.id}"
    
    prices = [LabeledPrice(label="Premium Subscription", amount=price)]
    
    try:
        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",  # Telegram Stars
            prices=prices
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("Failed to create invoice. Please try again.", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Handle pre-checkout"""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    """Handle successful payment"""
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    
    if parts[0] == "premium":
        days = int(parts[1])
        user_id = int(parts[2])
        
        # Add bonus days
        actual_days = days + (14 if days >= 90 else 0)
        
        # Update premium status
        await db.update_user_premium(user_id, actual_days)
        
        await message.answer(
            f"✨ Premium activated for {actual_days} days!\n\n"
            "Enjoy your premium benefits!"
        )


@router.callback_query(F.data == "buy_temp_premium")
async def buy_temp_premium(callback: CallbackQuery):
    """Buy temporary premium with sunflowers"""
    user_id = callback.from_user.id
    
    # Check sunflowers
    sunflowers = await db.get_sunflowers(user_id)
    if sunflowers['total'] < settings.TEMP_PREMIUM_COST:
        await callback.answer(
            f"You need {settings.TEMP_PREMIUM_COST} sunflowers. You have {sunflowers['total']}.",
            show_alert=True
        )
        return
    
    # Check cooldown
    user_data = await db.get_user(user_id)
    temp_last_used = user_data[5]
    
    if temp_last_used:
        last_used = datetime.fromisoformat(temp_last_used)
        days_since = (datetime.now() - last_used).days
        if days_since < settings.TEMP_PREMIUM_COOLDOWN:
            days_left = settings.TEMP_PREMIUM_COOLDOWN - days_since
            await callback.answer(
                f"You can buy temp premium again in {days_left} days.",
                show_alert=True
            )
            return
    
    # Deduct sunflowers (from games first, then gifts, then streak)
    remaining = settings.TEMP_PREMIUM_COST
    if sunflowers['games'] >= remaining:
        await db.remove_sunflowers(user_id, remaining, 'games')
    elif sunflowers['games'] > 0:
        await db.remove_sunflowers(user_id, sunflowers['games'], 'games')
        remaining -= sunflowers['games']
        if sunflowers['gifts'] >= remaining:
            await db.remove_sunflowers(user_id, remaining, 'gifts')
        else:
            await db.remove_sunflowers(user_id, sunflowers['gifts'], 'gifts')
            remaining -= sunflowers['gifts']
            await db.remove_sunflowers(user_id, remaining, 'streak')
    else:
        if sunflowers['gifts'] >= remaining:
            await db.remove_sunflowers(user_id, remaining, 'gifts')
        else:
            await db.remove_sunflowers(user_id, sunflowers['gifts'], 'gifts')
            remaining -= sunflowers['gifts']
            await db.remove_sunflowers(user_id, remaining, 'streak')
    
    # Activate temp premium
    await db.update_user_premium(user_id, settings.TEMP_PREMIUM_DAYS)
    await db.db.execute(
        "UPDATE users SET temp_premium_last_used = ? WHERE user_id = ?",
        (datetime.now(), user_id)
    )
    
    await callback.message.edit_text(
        f"✨ Temporary Premium activated for {settings.TEMP_PREMIUM_DAYS} days!\n\n"
        "You can now:\n"
        "• Buy pets\n"
        "• Play games\n"
        "• Use premium features\n\n"
        "Note: You cannot create a Garden with temp premium."
    )
    
    await callback.answer()

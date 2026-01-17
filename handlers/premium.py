"""
Premium subscription handlers
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.users import is_premium, get_premium_remaining_days
from db.sunflowers import get_sunflower_balance
from services.premium import (
    get_premium_plans, get_plan_by_duration,
    activate_premium, get_premium_status,
    can_buy_temp_premium, buy_temp_premium
)
from config import settings

router = Router()


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    """Show premium options"""
    user_id = message.from_user.id
    
    # Check current status
    is_active, days_left = await get_premium_status(user_id)
    
    if is_active:
        await message.answer(
            f"✨ You are a Premium member!\n\n"
            f"Days remaining: {days_left}\n\n"
            "Premium Benefits:\n"
            "• Priority matching\n"
            "• Gender preference\n"
            "• 5 links per day\n"
            "• Garden creation\n"
            "• Buy pets anytime\n"
            "• Fewer repeat matches"
        )
        return
    
    # Show purchase options
    text = (
        "⭐ Become Premium! ⭐\n\n"
        "Benefits:\n"
        "• Priority matching with high-rated users\n"
        "• Choose gender preference\n"
        "• Share up to 5 links/day\n"
        "• Create Garden (passive sunflowers)\n"
        "• Buy pets anytime\n"
        "• Better matching\n\n"
        "Select a plan:"
    )
    
    builder = InlineKeyboardBuilder()
    
    # Add premium plans
    builder.button(text=f"7 days - {settings.PREMIUM_7D} ⭐", callback_data="buy_premium:7")
    builder.button(text=f"30 days - {settings.PREMIUM_30D} ⭐", callback_data="buy_premium:30")
    builder.button(text=f"90 days - {settings.PREMIUM_90D} ⭐ (+14d)", callback_data="buy_premium:90")
    builder.button(text=f"365 days - {settings.PREMIUM_365D} ⭐ (+14d)", callback_data="buy_premium:365")
    
    # Add temp premium option
    can_buy, reason = await can_buy_temp_premium(user_id)
    if can_buy:
        balance = await get_sunflower_balance(user_id)
        builder.button(
            text=f"🌻 3-day temp ({settings.TEMP_PREMIUM_COST} sunflowers)",
            callback_data="buy_temp_premium"
        )
    
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("buy_premium:"))
async def buy_premium_callback(callback: CallbackQuery):
    """Handle premium purchase"""
    duration = int(callback.data.split(":")[1])
    plan = get_plan_by_duration(duration)
    
    if not plan:
        await callback.answer("Invalid plan", show_alert=True)
        return
    
    # Create invoice
    title = f"Pairly Premium - {duration} days"
    description = f"Premium subscription for {plan['actual_days']} days"
    payload = f"premium_{duration}_{callback.from_user.id}"
    
    prices = [LabeledPrice(label="Premium", amount=plan['price'])]
    
    try:
        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",
            prices=prices
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("Failed to create invoice", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """Handle pre-checkout"""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    """Handle successful payment"""
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    
    if parts[0] == "premium":
        duration = int(parts[1])
        user_id = int(parts[2])
        
        plan = get_plan_by_duration(duration)
        if plan:
            await activate_premium(user_id, plan['actual_days'])
            
            await message.answer(
                f"✨ Premium activated for {plan['actual_days']} days!\n\n"
                "Enjoy your premium benefits!"
            )


@router.callback_query(F.data == "buy_temp_premium")
async def buy_temp_premium_callback(callback: CallbackQuery):
    """Handle temp premium purchase"""
    user_id = callback.from_user.id
    
    # Double check
    can_buy, reason = await can_buy_temp_premium(user_id)
    
    if not can_buy:
        await callback.answer(reason, show_alert=True)
        return
    
    # Purchase
    success = await buy_temp_premium(user_id)
    
    if success:
        await callback.message.edit_text(
            f"✨ Temporary Premium activated for {settings.TEMP_PREMIUM_DAYS} days!\n\n"
            "You can now:\n"
            "• Buy pets\n"
            "• Play games\n"
            "• Use premium features\n\n"
            "Note: Garden creation requires full premium."
        )
    else:
        await callback.message.edit_text("❌ Failed to activate temp premium.")
    
    await callback.answer()

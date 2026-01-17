"""
Chat message handlers - forwarding and moderation
"""
from aiogram import Router, F
from aiogram.types import Message
import re
from db.users import get_partner, is_premium
from db.matchmaking import get_chat_id
from db.moderation import (
    log_violation, get_violation_count, ban_user,
    get_link_count_today, increment_link_count, log_monitored_message
)
from config import settings

router = Router()


def contains_link(text: str) -> bool:
    """Check if text contains links"""
    if not text:
        return False
    return bool(re.search(r'http|@', text, re.IGNORECASE))


async def check_and_handle_links(message: Message, text: str) -> bool:
    """
    Check for links and handle violations
    Returns True if message should be blocked
    """
    if not contains_link(text):
        return False
    
    user_id = message.from_user.id
    user_is_premium = await is_premium(user_id)
    
    if not user_is_premium:
        # Block for non-premium users
        await message.answer(
            "🚫 Links are not allowed for free users.\n"
            "Upgrade to Premium to share up to 5 links per day!"
        )
        
        # Log violation
        await log_violation(user_id, 'link')
        
        # Check violation count
        violations = await get_violation_count(user_id, 'link', 24)
        
        if violations >= 3:
            # Ban for 24 hours
            await ban_user(user_id, 24, "Repeated link violations")
            await message.answer(
                "🚫 You have been banned for 24 hours due to repeated link violations."
            )
        
        return True  # Block message
    
    # Premium user - check daily limit
    link_count = await get_link_count_today(user_id)
    
    if link_count >= settings.PREMIUM_DAILY_LINK_LIMIT:
        await message.answer(
            f"🚫 Daily link limit reached ({settings.PREMIUM_DAILY_LINK_LIMIT} links).\n"
            "Try again tomorrow!"
        )
        return True  # Block message
    
    # Increment counter
    await increment_link_count(user_id)
    
    return False  # Allow message


@router.message(F.text)
async def handle_text_message(message: Message):
    """Handle text messages in chat"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return  # Not in chat
    
    text = message.text
    
    # Check for links
    if await check_and_handle_links(message, text):
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        await log_monitored_message(chat_id, user_id, 'text', text)
    
    # Forward to partner
    try:
        await message.bot.send_message(partner_id, text)
    except Exception as e:
        await message.answer("❌ Failed to send message. Partner may have left.")


@router.message(F.photo)
async def handle_photo_message(message: Message):
    """Handle photo messages"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return
    
    # Check caption for links
    if message.caption and await check_and_handle_links(message, message.caption):
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        photo_id = message.photo[-1].file_id
        await log_monitored_message(chat_id, user_id, 'photo', message.caption, photo_id)
    
    # Forward to partner
    try:
        if message.caption:
            await message.bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        else:
            await message.bot.send_photo(partner_id, message.photo[-1].file_id)
    except:
        await message.answer("❌ Failed to send photo.")


@router.message(F.video)
async def handle_video_message(message: Message):
    """Handle video messages"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return
    
    # Check caption for links
    if message.caption and await check_and_handle_links(message, message.caption):
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        await log_monitored_message(chat_id, user_id, 'video', message.caption, message.video.file_id)
    
    # Forward to partner
    try:
        if message.caption:
            await message.bot.send_video(partner_id, message.video.file_id, caption=message.caption)
        else:
            await message.bot.send_video(partner_id, message.video.file_id)
    except:
        await message.answer("❌ Failed to send video.")


@router.message(F.voice)
async def handle_voice_message(message: Message):
    """Handle voice messages"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        await log_monitored_message(chat_id, user_id, 'voice', None, message.voice.file_id)
    
    # Forward to partner
    try:
        await message.bot.send_voice(partner_id, message.voice.file_id)
    except:
        await message.answer("❌ Failed to send voice message.")


@router.message(F.sticker)
async def handle_sticker_message(message: Message):
    """Handle sticker messages"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        await log_monitored_message(chat_id, user_id, 'sticker', None, message.sticker.file_id)
    
    # Forward to partner
    try:
        await message.bot.send_sticker(partner_id, message.sticker.file_id)
    except:
        await message.answer("❌ Failed to send sticker.")


@router.message(F.document)
async def handle_document_message(message: Message):
    """Handle document messages"""
    user_id = message.from_user.id
    partner_id = await get_partner(user_id)
    
    if not partner_id:
        return
    
    # Check caption for links
    if message.caption and await check_and_handle_links(message, message.caption):
        return
    
    # Log for admin
    chat_id = await get_chat_id(user_id)
    if chat_id:
        await log_monitored_message(chat_id, user_id, 'document', message.caption, message.document.file_id)
    
    # Forward to partner
    try:
        if message.caption:
            await message.bot.send_document(partner_id, message.document.file_id, caption=message.caption)
        else:
            await message.bot.send_document(partner_id, message.document.file_id)
    except:
        await message.answer("❌ Failed to send document.")

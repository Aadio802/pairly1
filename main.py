"""
Pairly - Production Anonymous Chat Bot
Main Entry Point
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from db import init_database
from handlers import register_all_handlers

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Initialize and start bot"""
    logger.info("Starting Pairly bot...")
    
    # Initialize database with WAL mode
    await init_database()
    logger.info("Database initialized with WAL mode")
    
    # Initialize bot
    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Register all handlers
    register_all_handlers(dp)
    logger.info("Handlers registered")
    
    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

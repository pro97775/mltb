from pyrogram import Client, enums
from pyrogram.errors import FloodPremiumWait, FloodWait
from pyrogram.types import LinkPreviewOptions
from asyncio import Lock, TimeoutError, sleep

from .. import LOGGER
from .config_manager import Config

START_RETRY_DELAY = 5
START_RETRY_MAX_DELAY = 60


class TgClient:
    _lock = Lock()
    bot = None
    user = None
    NAME = ""
    ID = 0
    IS_PREMIUM_USER = False
    MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def start_bot(cls):
        LOGGER.info("Creating client from BOT_TOKEN")
        if isinstance(Config.TG_PROXY, dict) and Config.TG_PROXY:
            LOGGER.info(
                "Using Telegram proxy "
                f"{Config.TG_PROXY.get('scheme', '')}://"
                f"{Config.TG_PROXY.get('host', '')}:"
                f"{Config.TG_PROXY.get('port', '')}"
            )
        cls.ID = Config.BOT_TOKEN.split(":", 1)[0]
        cls.bot = Client(
            cls.ID,
            Config.TELEGRAM_API,
            Config.TELEGRAM_HASH,
            proxy=Config.TG_PROXY or None,
            bot_token=Config.BOT_TOKEN,
            workdir="/app",
            parse_mode=enums.ParseMode.HTML,
            max_concurrent_transmissions=10,
            max_message_cache_size=15000,
            max_topic_cache_size=15000,
            sleep_threshold=0,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await cls._start_client(cls.bot, "Bot")
        cls.NAME = cls.bot.me.username

    @classmethod
    async def _start_client(cls, client, label):
        delay = START_RETRY_DELAY
        attempt = 0
        while True:
            attempt += 1
            try:
                await client.start()
                return
            except (FloodWait, FloodPremiumWait) as f:
                wait = int(getattr(f, "value", 0) or 0) + 1
                LOGGER.warning(
                    f"{label} client hit a Telegram flood wait: "
                    f"sleeping {wait}s before retrying."
                )
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await sleep(wait)
            except (TimeoutError, OSError) as e:
                LOGGER.warning(
                    f"{label} client failed to start (attempt {attempt}): "
                    f"{e}. Retrying in {delay}s."
                )
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await sleep(delay)
                delay = min(delay * 2, START_RETRY_MAX_DELAY)

    @classmethod
    async def start_user(cls):
        if Config.USER_SESSION_STRING:
            LOGGER.info("Creating client from USER_SESSION_STRING")
            try:
                cls.user = Client(
                    "user",
                    Config.TELEGRAM_API,
                    Config.TELEGRAM_HASH,
                    proxy=Config.TG_PROXY or None,
                    session_string=Config.USER_SESSION_STRING,
                    workdir="/app",
                    parse_mode=enums.ParseMode.HTML,
                    sleep_threshold=60,
                    max_concurrent_transmissions=10,
                    max_message_cache_size=15000,
                    max_topic_cache_size=15000,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                await cls.user.start()
                cls.IS_PREMIUM_USER = cls.user.me.is_premium
                if cls.IS_PREMIUM_USER:
                    cls.MAX_SPLIT_SIZE = 4194304000
            except Exception as e:
                LOGGER.error(f"Failed to start client from USER_SESSION_STRING. {e}")
                cls.IS_PREMIUM_USER = False
                cls.user = None

    @classmethod
    async def stop(cls):
        async with cls._lock:
            if cls.bot:
                await cls.bot.stop()
            if cls.user:
                await cls.user.stop()
            LOGGER.info("Client(s) stopped")

    @classmethod
    async def reload(cls):
        async with cls._lock:
            await cls.bot.restart()
            if cls.user:
                await cls.user.restart()
            LOGGER.info("Client(s) restarted")

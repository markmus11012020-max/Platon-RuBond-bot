from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiohttp import web

from bondbot.config import Settings, load_settings
from bondbot.db import Database
from bondbot.vk.client import VkClient
from bondbot.vk.handlers import BotHandlers
from bondbot.vk.longpoll import VkLongPoll

log = logging.getLogger("bondbot")


def setup_logging() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def start_health(settings: Settings, db: Database) -> web.AppRunner:
    app = web.Application()

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "bonds": len(db.list_bonds()),
                "positions": len(db.positions()),
                "vk": settings.vk_configured,
                "llm": settings.llm_configured,
            }
        )

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/health", healthz)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.health_port)
    await site.start()
    log.info("health server on :%s", settings.health_port)
    return runner


async def run() -> None:
    setup_logging()
    settings = load_settings()
    log.info(
        "started: db=%s vk=%s llm=%s model=%s",
        settings.db_path,
        settings.vk_configured,
        settings.llm_configured,
        settings.openai_model,
    )
    if not settings.vk_configured:
        log.error("BONDBOT_VK_GROUP_TOKEN / BONDBOT_VK_GROUP_ID are not configured")
        return

    db = Database(settings.db_path)
    vk = VkClient(settings)
    handlers = BotHandlers(settings, db, vk)
    longpoll = VkLongPoll(vk, db, handlers.handle_update)
    health = await start_health(settings, db)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    task = asyncio.create_task(longpoll.run_forever(), name="vk-longpoll")
    try:
        await stop.wait()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await health.cleanup()
        await vk.close()
        db.close()
        log.info("stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

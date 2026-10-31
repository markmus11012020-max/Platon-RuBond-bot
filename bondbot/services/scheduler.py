from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bondbot.config import Settings
from bondbot.db import Database
from bondbot.models import MSK
from bondbot.services.alerts import build_and_send, owner_peer
from bondbot.services.backup import backup_database
from bondbot.services.digest import build_digest
from bondbot.services.ideas import build_strategy_note
from bondbot.services.news import build_news_digest, refresh_news
from bondbot.services.refresh import (
    RefreshResult,
    refresh_details,
    refresh_key_rate,
    refresh_market,
)
from bondbot.services.review import save_portfolio_snapshot
from bondbot.vk.client import VkClient

log = logging.getLogger(__name__)


class BotScheduler:
    """Планировщик фоновых задач. Все jobs пишутся в job_runs."""

    def __init__(self, settings: Settings, db: Database, vk: VkClient) -> None:
        self.settings = settings
        self.db = db
        self.vk = vk
        self.scheduler = AsyncIOScheduler(timezone=MSK)

    @property
    def started(self) -> bool:
        return bool(self.scheduler.running)

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            log.info("scheduler disabled")
            return
        hour = self.settings.refresh_hour % 24
        minute = self.settings.refresh_minute % 60
        detail_hour = self.settings.detail_refresh_hour % 24
        detail_minute = self.settings.detail_refresh_minute % 60
        digest_hour = self.settings.digest_hour % 24
        digest_minute = self.settings.digest_minute % 60

        self.scheduler.add_job(
            self._market,
            CronTrigger(hour=hour, minute=minute, timezone=MSK),
            id="market_refresh",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self._details,
            CronTrigger(hour=detail_hour, minute=detail_minute, timezone=MSK),
            id="detail_refresh",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self._key_rate,
            IntervalTrigger(hours=6, timezone=MSK),
            id="key_rate",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(MSK) + timedelta(seconds=15),
        )
        self.scheduler.add_job(
            self._digest,
            CronTrigger(hour=digest_hour, minute=digest_minute, timezone=MSK),
            id="digest",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        if self.settings.news_enabled:
            self.scheduler.add_job(
                self._news,
                IntervalTrigger(minutes=max(5, self.settings.news_interval_minutes)),
                id="news_refresh",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                next_run_time=datetime.now(MSK) + timedelta(seconds=30),
            )
        self.scheduler.add_job(
            self._strategy,
            CronTrigger(day_of_week="fri", hour=19, minute=0, timezone=MSK),
            id="strategy_note",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        if self.settings.backup_enabled:
            self.scheduler.add_job(
                self._backup,
                CronTrigger(hour=3, minute=0, timezone=MSK),
                id="backup",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
        self.scheduler.start()
        log.info("scheduler started: market=%02d:%02d detail=%02d:%02d digest=%02d:%02d",
                 hour, minute, detail_hour, detail_minute, digest_hour, digest_minute)

    def shutdown(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            log.info("scheduler stopped")

    async def _run(self, name: str, func: Callable[[], Awaitable[Any]]) -> Any:
        job_id = self.db.start_job(name)
        try:
            result = await func()
        except Exception as exc:
            log.exception("job %s failed", name)
            self.db.finish_job(job_id, "error", {"error": str(exc)})
            return None
        details = asdict(result) if is_dataclass(result) else (
            result if isinstance(result, dict) else {"result": str(result)}
        )
        self.db.finish_job(job_id, "ok", details)
        return result

    async def _market(self) -> None:
        async def run() -> dict[str, Any]:
            refreshed: RefreshResult = await refresh_market(self.settings, self.db)
            snapshot = None
            try:
                snapshot = await refresh_key_rate(self.settings, self.db)
            except Exception as exc:
                log.warning("key rate refresh failed: %s", exc)
            sent = await build_and_send(self.settings, self.db, self.vk, snapshot)
            return {
                "source": refreshed.source,
                "seen": refreshed.seen,
                "upserted": refreshed.upserted,
                "new": len(refreshed.new_isins),
                "errors": list(refreshed.errors),
                "alerts_sent": sent,
            }

        await self._run("market_refresh", run)

    async def _details(self) -> None:
        async def run() -> dict[str, Any]:
            updated, errors = await refresh_details(self.settings, self.db)
            snapshot = None
            try:
                snapshot = await refresh_key_rate(self.settings, self.db)
            except Exception as exc:
                log.warning("key rate refresh failed: %s", exc)
            sent = await build_and_send(self.settings, self.db, self.vk, snapshot)
            save_portfolio_snapshot(self.settings, self.db)
            return {"updated": updated, "errors": errors, "alerts_sent": sent}

        await self._run("detail_refresh", run)

    async def _key_rate(self) -> None:
        async def run() -> dict[str, Any]:
            snapshot = await refresh_key_rate(self.settings, self.db)
            return {
                "value_pct": snapshot.value_pct,
                "as_of": snapshot.as_of.isoformat(),
                "stale": snapshot.stale,
            }

        await self._run("key_rate", run)

    async def _digest(self) -> None:
        async def run() -> dict[str, Any]:
            snapshot = await refresh_key_rate(self.settings, self.db)
            text = build_digest(self.settings, self.db, snapshot)
            peer_id = owner_peer(self.settings, self.db)
            if not peer_id:
                return {"sent": False, "reason": "owner peer is not configured"}
            await self.vk.send_message(peer_id, text)
            return {"sent": True, "chars": len(text)}

        await self._run("digest", run)

    async def _news(self) -> None:
        async def run() -> dict[str, Any]:
            result = await refresh_news(self.settings, self.db)
            return {
                "feeds": result.feeds,
                "fetched": result.fetched,
                "saved": result.saved,
                "errors": list(result.errors),
            }

        await self._run("news_refresh", run)

    async def _strategy(self) -> None:
        async def run() -> dict[str, Any]:
            snapshot = await refresh_key_rate(self.settings, self.db)
            text = build_strategy_note(self.settings, self.db, snapshot)
            peer_id = owner_peer(self.settings, self.db)
            if not peer_id:
                return {"sent": False, "reason": "owner peer is not configured"}
            await self.vk.send_message(peer_id, text)
            return {"sent": True, "chars": len(text)}

        await self._run("strategy_note", run)

    async def _backup(self) -> None:
        async def run() -> dict[str, Any]:
            path = backup_database(
                self.settings.db_path,
                self.settings.backup_dir,
                keep=self.settings.backup_keep,
            )
            return {"path": str(path)}

        await self._run("backup", run)


__all__ = ["BotScheduler"]

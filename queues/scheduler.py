import asyncio
from dataclasses import dataclass
import time
from queues.file_deletion import cleanup_files
from queues.post_deletion import cleanup_posts
import typing as t
from logging import getLogger

logger = getLogger("linkverse.scheduler")


@dataclass
class Scheduled:
    func: t.Callable[[], t.Awaitable[bool | None]]
    long_interval: int = 600
    short_interval: int = 60
    next_on: float = 0


scheduled = (
    Scheduled(
        func=cleanup_files,
        short_interval=15,
        long_interval=300
    ),
    Scheduled(
        func=cleanup_posts,
        long_interval=60,
        short_interval=60
    )
)


async def run_cycle() -> int:
    now = time.monotonic()
    next_wait = 1200

    for item in scheduled:
        if item.next_on < now:
            use_short: bool | None = False
            try:
                use_short = await item.func()
            except Exception as e:
                logger.exception(e)

            interval = (
                item.short_interval
                if use_short
                else item.long_interval
            )
            item.next_on = now + interval

        next_wait = min(next_wait, max(0, item.next_on - now))

    return next_wait


async def scheduler() -> None:
    while True:
        to_wait = await run_cycle()
        await asyncio.sleep(to_wait)


def start_scheduler() -> None:
    asyncio.create_task(scheduler())

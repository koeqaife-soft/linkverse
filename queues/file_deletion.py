import asyncio
from utils.storage import delete_object
from utils.database import AutoConnection
from core import get_proc_identity
from core import total_servers, server_id, worker_count
import aiohttp
from state import pool

BATCH_SIZE = 10000
MAX_CONCURRENCY = 100


async def cleanup_files() -> bool:
    worker_id = max(get_proc_identity() - 1, 0)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with AutoConnection(pool) as conn:
        db = await conn.create_conn()
        files_to_delete = await db.fetch(
            """
            SELECT context_id, objects
            FROM files
            WHERE reference_count = 0
                AND created_at < NOW() - INTERVAL '30 minutes'
                AND (context_id::bigint % $1) = $2  -- server
                AND (context_id::bigint % $3) = $4  -- worker
            LIMIT $5
            """,
            total_servers,
            server_id,
            worker_count,
            worker_id,
            BATCH_SIZE,
        )

        async with db.transaction():
            for record in files_to_delete:
                context_id: str = record["context_id"]
                objects: list[str] = record["objects"]

                async with aiohttp.ClientSession() as session:
                    async def bounded_delete(obj: str) -> None:
                        async with semaphore:
                            await delete_object(obj, session)

                    tasks = [bounded_delete(obj) for obj in objects]
                    await asyncio.gather(*tasks, return_exceptions=True)

                await db.execute(
                    "DELETE FROM files WHERE context_id = $1", context_id
                )

    return len(files_to_delete) != 0

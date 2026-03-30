"""
Shared thread-pool executor for offloading heavy agent work
off the main asyncio event loop.

Usage patterns
--------------

1) **BackgroundTasks** (FastAPI):
   Pass the *sync* wrapper to `background_tasks.add_task()`.
   FastAPI automatically runs sync callables in a thread pool.

       from utils.agent_executor import run_agent_in_background

       def _sync_my_task(arg1, arg2):
           run_agent_in_background(my_async_fn(arg1, arg2))

       @router.post("/endpoint")
       async def handler(background_tasks: BackgroundTasks):
           background_tasks.add_task(_sync_my_task, a, b)

2) **Inside an async request handler** (wrap a sync SDK call):

       from utils.agent_executor import AGENT_POOL
       import asyncio

       loop = asyncio.get_running_loop()
       result = await loop.run_in_executor(AGENT_POOL, sync_fn, arg1, arg2)

3) **APScheduler jobs** (offload from the event loop):

       from utils.agent_executor import submit_agent_task

       async def job_heavy(client_id):
           await submit_agent_task(actual_heavy_work, client_id)
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_pool_size = int(os.environ.get("AGENT_POOL_SIZE", "4"))

AGENT_POOL = ThreadPoolExecutor(
    max_workers=_pool_size,
    thread_name_prefix="agent-pool",
)

log.info("Agent thread pool created  workers=%d", _pool_size)


# ── helpers ────────────────────────────────────────────────────────────────────

def run_agent_in_background(coro, timeout: int = 900):
    """
    Synchronous wrapper that runs an async coroutine to completion
    inside a *new* event loop on the current thread.

    Designed to be called from a **sync** BackgroundTask function —
    FastAPI will automatically schedule sync callables on a thread pool,
    keeping the main event loop free.

    Parameters
    ----------
    coro : coroutine
        The awaitable to execute (e.g. ``my_async_fn(arg1, arg2)``).
    timeout : int
        Maximum seconds before the coroutine is cancelled (default 900 = 15 min).
    """
    try:
        asyncio.run(asyncio.wait_for(coro, timeout=timeout))
    except asyncio.TimeoutError:
        log.error("Agent task timed out after %ds: %s", timeout, coro)
    except Exception:
        log.exception("Agent task failed: %s", coro)


async def submit_agent_task(async_fn, *args, timeout: int = 900, **kwargs):
    """
    Submit heavy async work to the agent thread pool from an async context
    (e.g. an APScheduler async job).

    This creates a sync wrapper → ``asyncio.run()`` inside the thread pool,
    so the calling event loop is never blocked.

    Parameters
    ----------
    async_fn : callable
        An async function (not a coroutine — don't call it yet).
    *args, **kwargs
        Forwarded to ``async_fn``.
    timeout : int
        Maximum seconds (default 900).
    """
    loop = asyncio.get_running_loop()

    def _sync_wrapper():
        run_agent_in_background(async_fn(*args, **kwargs), timeout=timeout)

    await loop.run_in_executor(AGENT_POOL, _sync_wrapper)

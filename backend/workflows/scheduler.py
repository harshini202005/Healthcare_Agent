"""
Background asyncio task that fires the workflow engine every 60 seconds.
Started and stopped via FastAPI lifespan.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _loop():
    while True:
        try:
            from backend.workflows.engine import execute_pending_runs
            execute_pending_runs()
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}", exc_info=True)
        await asyncio.sleep(60)


def start():
    global _task
    _task = asyncio.create_task(_loop())
    logger.info("Workflow scheduler started")


def stop():
    global _task
    if _task:
        _task.cancel()
        _task = None
    logger.info("Workflow scheduler stopped")

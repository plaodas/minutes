import asyncio
import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("minutes.sse")

_lock = threading.Lock()
# list of asyncio.Queue instances
_queues: list[asyncio.Queue] = []

# Redis publish client (sync) lazily initialized when REDIS_URL is set
_redis_pub = None
# Asyncio task for redis subscriber
_redis_task: asyncio.Task | None = None


def register_queue() -> asyncio.Queue:
    q = asyncio.Queue()
    with _lock:
        _queues.append(q)
    return q


def unregister_queue(q: asyncio.Queue):
    with _lock:
        try:
            _queues.remove(q)
        except ValueError:
            pass


def _push_to_local_queues(event: dict[str, Any]):
    with _lock:
        queues = list(_queues)
    for q in queues:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                logger.exception("failed to push event to local queue")
        else:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.exception("failed to put event into queue without loop")


def publish_event(event: dict[str, Any]):
    """Publish an event locally and to Redis if configured.

    This function is safe to call from synchronous code.
    """
    # send to local subscribers
    _push_to_local_queues(event)

    # publish to redis channel for other instances
    try:
        # allow fallback to commonly-set broker/url env vars so worker processes
        # without explicit REDIS_URL still publish events (e.g., Celery uses REDIS)
        redis_url = (
            os.environ.get("REDIS_URL")
            or os.environ.get("CELERY_BROKER_URL")
            or os.environ.get("BROKER_URL")
        )
        if not redis_url:
            return
        global _redis_pub
        if _redis_pub is None:
            # Lazy import so environments without redis won't fail at module import
            import redis
            from redis.exceptions import RedisError

            try:
                _redis_pub = redis.from_url(redis_url, decode_responses=True)
            except (RedisError, OSError):
                logger.exception("failed to create redis publisher from %s", redis_url)
                _redis_pub = None
        if _redis_pub is not None:
            from redis.exceptions import RedisError

            try:
                _redis_pub.publish("minutes:events", json.dumps(event, default=str))
            except (RedisError, OSError):
                logger.exception("redis publish failed; resetting publisher")
                try:
                    _redis_pub.close()
                except (RedisError, OSError):
                    logger.exception("failed to close redis publisher")
                _redis_pub = None
    except (ImportError, RuntimeError, TypeError):
        # Narrowed top-level exceptions to common, recoverable errors
        logger.exception("publish_event top-level failure")


async def _redis_listener(redis_url: str):
    import redis.asyncio as aioredis
    from redis.exceptions import RedisError

    backoff_base = 0.5
    max_backoff = 30.0
    backoff = backoff_base
    client = None
    pubsub = None
    try:
        while True:
            try:
                client = aioredis.from_url(redis_url, decode_responses=True)
                pubsub = client.pubsub()
                await pubsub.subscribe("minutes:events")
                logger.info("Subscribed to Redis minutes:events")
                backoff = backoff_base

                while True:
                    # non-blocking get_message with timeout so we can check cancellation
                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if msg and "data" in msg:
                        data = msg["data"]
                        try:
                            ev = json.loads(data)
                        except json.JSONDecodeError:
                            ev = {"type": "redis.raw", "raw": data}
                        _push_to_local_queues(ev)
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                logger.info("Redis listener cancelled during subscribe/read")
                raise
            except (RedisError, OSError, RuntimeError):
                logger.exception(
                    "Redis listener connection/read failed; will retry with backoff"
                )
                # cleanup client/pubsub before retry
                try:
                    if pubsub is not None:
                        await pubsub.close()
                except (RedisError, OSError):
                    logger.exception("failed to close pubsub")
                try:
                    if client is not None:
                        await client.close()
                except (RedisError, OSError):
                    logger.exception("failed to close redis client")
                # exponential backoff with jitter
                await asyncio.sleep(
                    backoff
                    + (backoff * 0.1 * (0.5 - asyncio.get_event_loop().time() % 1))
                )
                backoff = min(backoff * 2, max_backoff)
                continue
    finally:
        try:
            if pubsub is not None:
                await pubsub.close()
        except (RedisError, OSError):
            logger.exception("failed to close pubsub on shutdown")
        try:
            if client is not None:
                await client.close()
        except (RedisError, OSError):
            logger.exception("failed to close redis client on shutdown")


def start_redis_listener(redis_url: str):
    """Start background asyncio task to listen for Redis-published events.

    Must be called from within an event loop (e.g. FastAPI startup handler).
    """
    global _redis_task
    if not redis_url:
        return
    if _redis_task is not None and not _redis_task.done():
        return
    loop = asyncio.get_event_loop()
    _redis_task = loop.create_task(_redis_listener(redis_url))


def stop_redis_listener():
    global _redis_task
    try:
        if _redis_task is not None:
            _redis_task.cancel()
            _redis_task = None
    except RuntimeError:
        logger.exception("failed to stop redis listener")

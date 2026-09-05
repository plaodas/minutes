import asyncio
import threading
import json
import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger('minutes.sse')

_lock = threading.Lock()
# list of asyncio.Queue instances
_queues: List[asyncio.Queue] = []

# Redis publish client (sync) lazily initialized when REDIS_URL is set
_redis_pub = None
# Asyncio task for redis subscriber
_redis_task: Optional[asyncio.Task] = None


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


def _push_to_local_queues(event: Dict[str, Any]):
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
            except Exception:
                logger.exception('failed to push event to local queue')
        else:
            try:
                q.put_nowait(event)
            except Exception:
                logger.exception('failed to put event into queue without loop')


def publish_event(event: Dict[str, Any]):
    """Publish an event locally and to Redis if configured.

    This function is safe to call from synchronous code.
    """
    # send to local subscribers
    try:
        _push_to_local_queues(event)
    except Exception:
        logger.exception('local push failed')

    # publish to redis channel for other instances
    try:
        redis_url = os.environ.get('REDIS_URL')
        if not redis_url:
            return
        global _redis_pub
        if _redis_pub is None:
            import redis
            try:
                _redis_pub = redis.from_url(redis_url, decode_responses=True)
            except Exception:
                logger.exception('failed to create redis publisher')
                _redis_pub = None
        if _redis_pub is not None:
            try:
                _redis_pub.publish('minutes:events', json.dumps(event, default=str))
            except Exception:
                logger.exception('redis publish failed; resetting publisher')
                try:
                    _redis_pub.close()
                except Exception:
                    pass
                _redis_pub = None
    except Exception:
        logger.exception('publish_event top-level failure')


async def _redis_listener(redis_url: str):
    import redis.asyncio as aioredis
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
                await pubsub.subscribe('minutes:events')
                logger.info('Subscribed to Redis minutes:events')
                backoff = backoff_base

                while True:
                    # non-blocking get_message with timeout so we can check cancellation
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg and 'data' in msg:
                        data = msg['data']
                        try:
                            ev = json.loads(data)
                        except Exception:
                            ev = {"type": "redis.raw", "raw": data}
                        _push_to_local_queues(ev)
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                logger.info('Redis listener cancelled during subscribe/read')
                raise
            except Exception:
                logger.exception('Redis listener connection/read failed; will retry with backoff')
                # cleanup client/pubsub before retry
                try:
                    if pubsub is not None:
                        await pubsub.close()
                except Exception:
                    logger.exception('failed to close pubsub')
                try:
                    if client is not None:
                        await client.close()
                except Exception:
                    logger.exception('failed to close redis client')
                # exponential backoff with jitter
                await asyncio.sleep(backoff + (backoff * 0.1 * (0.5 - asyncio.get_event_loop().time() % 1)))
                backoff = min(backoff * 2, max_backoff)
                continue
    finally:
        try:
            if pubsub is not None:
                await pubsub.close()
        except Exception:
            logger.exception('failed to close pubsub on shutdown')
        try:
            if client is not None:
                await client.close()
        except Exception:
            logger.exception('failed to close redis client on shutdown')


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
    except Exception:
        logger.exception('failed to stop redis listener')

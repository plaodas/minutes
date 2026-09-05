import asyncio
import threading
import json
from typing import Any, Dict, List

_lock = threading.Lock()
# list of asyncio.Queue instances
_queues: List[asyncio.Queue] = []


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


def publish_event(event: Dict[str, Any]):
    """Publish a JSON-serializable event to all registered client queues.

    This is safe to call from synchronous code: it schedules a thread-safe put
    on each asyncio.Queue so subscribers will receive events asynchronously.
    """
    # copy to avoid holding lock while scheduling
    with _lock:
        queues = list(_queues)

    for q in queues:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # no running loop in this thread — schedule via asyncio.new_event_loop()
            try:
                loop = asyncio.get_event_loop()
            except Exception:
                loop = None
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                # best-effort: ignore failures per subscriber
                pass
        else:
            # If no running loop is available (rare for background threads), try
            # to put without blocking using a temporary loop. This is a fallback
            # and may drop events under high load.
            try:
                q.put_nowait(event)
            except Exception:
                pass

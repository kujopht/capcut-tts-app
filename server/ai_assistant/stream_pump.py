"""
StreamPump — moves the gateway's SYNC provider generator off the event loop
and lets the SSE route notice SILENCE, so it can send a heartbeat.

Why not `iterate_in_threadpool` (the previous implementation): each
`next()` there is one opaque `await` that returns only when the provider
yields. While a provider is thinking (a slow first token, a long pause
mid-answer), the route can do nothing — no keepalive reaches the client,
and proxies/CDNs in front of Render (Cloudflare) drop an idle response
after ~100 s. Here a dedicated daemon thread iterates the generator and
hands each event to an `asyncio.Queue` on the loop; the route waits on that
queue with a timeout and gets `SILENCE` back when nothing arrived in time.

Guarantees (each covered by `server/tests/test_ai_heartbeat.py`):

* Events arrive in order and unchanged — the pump never merges, drops or
  re-orders provider events, so streaming chunks and stop semantics are
  exactly those of the gateway.
* No event-loop blocking and no shared threadpool slot is held while
  waiting: the only blocking call (`next(gen)`) runs on the pump's own
  thread; the route awaits a plain `asyncio.Queue`.
* The generator is iterated AND closed on the pump thread (a generator
  cannot be closed from another thread while it runs) — `contextlib.closing`
  semantics in `_run`'s `finally` — so the provider's httpx stream is
  released deterministically.
* `stop()` (called from the route's `finally` on every exit path: normal
  end, error, client disconnect) makes the thread exit at the provider's
  NEXT event. A provider blocked inside a network read wakes up at the
  latest when its own read timeout fires — the thread is bounded, never
  orphaned forever.
* An unexpected exception escaping the generator is delivered as
  `PumpError` (never re-raised on the loop thread), then `END`.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Iterator

import anyio

log = logging.getLogger("fanfic.ai_assistant")

#: The generator is exhausted (normally, after an error, or after `stop()`).
END = object()
#: `next()` timed out with no event — the caller should send a heartbeat.
SILENCE = object()


@dataclass(frozen=True)
class PumpError:
    """An exception that escaped the generator on the pump thread."""
    exc: BaseException


class StreamPump:
    def __init__(self, gen: Iterator[Any], *, name: str = "ai-stream-pump") -> None:
        # Must be constructed on the event-loop thread (inside the route).
        self._gen = gen
        self._loop = asyncio.get_running_loop()
        self._queue: "asyncio.Queue[Any]" = asyncio.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> "StreamPump":
        self._thread.start()
        return self

    def _push(self, item: Any) -> bool:
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
            return True
        except RuntimeError:
            # The loop is closed (server shutting down) — nobody is left to
            # read; stop pumping.
            return False

    def _run(self) -> None:
        try:
            for ev in self._gen:
                if self._stop.is_set() or not self._push(ev):
                    break
        except BaseException as exc:  # noqa: BLE001 — delivered, never swallowed silently
            self._push(PumpError(exc))
        finally:
            # `contextlib.closing` semantics, but tolerant of a plain
            # iterator (no `.close()`): a generator gets `GeneratorExit` at
            # its current `yield`, which unwinds the gateway's and the
            # provider's own `closing(...)` blocks (R3) right here.
            close = getattr(self._gen, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 — the stream is over; log, don't mask END
                    log.warning("ai_assistant: closing the provider stream failed", exc_info=True)
            self._push(END)

    async def next(self, timeout_s: float) -> Any:
        """The next event, `END`, a `PumpError`, or `SILENCE` after
        `timeout_s` seconds without one. Cancellation-safe: a cancel while
        waiting leaves the queue intact (nothing is lost or half-read)."""
        with anyio.move_on_after(timeout_s):
            return await self._queue.get()
        return SILENCE

    def stop(self) -> None:
        """Ask the pump thread to exit at the provider's next event. Idempotent,
        never blocks."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> bool:
        """Test/diagnostic helper — True when the pump thread has exited."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

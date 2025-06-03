"""
Utility helpers for running async functions from synchronous code.

1. If there is no running event loop, just `asyncio.run`.
2. If there is a running loop, spin up a background thread that has
   its own loop and execute the coroutine there.
3. If the caller passes in an `httpx.AsyncClient` (or any external
   resource bound to the outer loop) while a loop is already running,
   raise because that resource cannot be reused safely in the thread.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def run_sync(
    coro: Coroutine[Any, Any, T],
    *,
    session: object | None = None,
    _executor_factory: Callable[[], concurrent.futures.Executor] | None = None,
) -> T:
    """
    Run *coro* synchronously and return its result.

    Parameters
    ----------
    coro:
        Any awaitable (usually an async function call).
    session:
        Optional resource tied to the outer loop; if supplied while
        already inside a loop we refuse to continue.
    _executor_factory:
        *Test seam* - lets tests inject a dummy executor.

    Raises
    ------
    ValueError
        If called from inside an event loop *and* ``session`` is passed in.
    """
    # ──────────────────────────────
    # 1. No running loop
    # ──────────────────────────────
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # ──────────────────────────────
    # 2. Running loop
    # ──────────────────────────────
    if session is not None:
        raise ValueError(
            "run_sync called from within an async environment but a "
            "`session` bound to that loop was supplied.  Pass no session "
            "or call the async variant directly."
        )

    def _runner() -> T:
        return asyncio.run(coro)

    executor = (
        _executor_factory()
        if _executor_factory is not None
        else concurrent.futures.ThreadPoolExecutor(max_workers=1)
    )
    # Use a context manager only when we created the executor ourselves.
    if _executor_factory is None:
        with executor:
            future = executor.submit(_runner)
            return future.result()
    else:
        # In tests where a fake executor is injected we assume it stays alive.
        future = executor.submit(_runner)
        return future.result()

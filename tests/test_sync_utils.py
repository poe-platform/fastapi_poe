import asyncio

import pytest
from fastapi_poe.sync_utils import run_sync


async def _add(a: int, b: int) -> int:
    await asyncio.sleep(0.01)
    return a + b


def test_run_sync_without_event_loop() -> None:
    assert run_sync(_add(1, 2)) == 3


@pytest.mark.asyncio
async def test_run_sync_inside_event_loop() -> None:
    assert run_sync(_add(4, 5)) == 9


@pytest.mark.asyncio
async def test_run_sync_rejects_session_inside_loop() -> None:
    with pytest.raises(ValueError):
        run_sync(_add(1, 1), session="dummy")


def test_run_sync_propagates_exceptions() -> None:
    async def _boom() -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        run_sync(_boom())

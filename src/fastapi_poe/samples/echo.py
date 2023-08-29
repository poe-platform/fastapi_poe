"""

Sample bot that echoes back messages.

See more samples in the tutorial repo at: https://github.com/poe-platform/server-bot-quick-start

"""
from __future__ import annotations

from typing import AsyncIterable

from sse_starlette.sse import ServerSentEvent

from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        last_message = query.query[-1].content
        yield self.text_event(last_message)


if __name__ == "__main__":
    run(EchoBot(), allow_without_key=True)

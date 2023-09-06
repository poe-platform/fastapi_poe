"""

Sample bot that echoes back messages.

See more samples in the tutorial repo at: https://github.com/poe-platform/server-bot-quick-start

"""
from __future__ import annotations

from typing import AsyncIterable

from fastapi_poe import PoeBot, run
from fastapi_poe.types import PartialResponse, QueryRequest


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[PartialResponse]:
        last_message = query.query[-1].content
        yield PartialResponse(text=last_message)


if __name__ == "__main__":
    run(EchoBot(), allow_without_key=True)

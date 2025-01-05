# utils.py

import asyncio
from typing import AsyncGenerator
from fastapi_poe.types import ProtocolMessage
from fastapi_poe.client import get_bot_response
from fastapi import HTTPException


async def concat_message(partial_gen: AsyncGenerator[str, None]) -> str:
    """
    Concatenate messages from an async generator of partials.

    Args:
        partial_gen (AsyncGenerator[str, None]): An asynchronous generator yielding partial message strings.

    Returns:
        str: The concatenated message.
    """
    concated = ""
    async for partial in partial_gen:
        concated += partial
    return concated



async def get_poe_partial_messages(messages, bot_name: str, api_key: str) -> AsyncGenerator[str, None]:
    """
    Fetch partial messages from fastapi_poe's get_bot_response.

    Args:
        messages (list): List of ProtocolMessage objects.
        bot_name (str): Name of the bot to interact with.
        api_key (str): API key for authentication.

    Yields:
        str: Partial message content.
    """
    async for partial in get_bot_response(messages=messages, bot_name=bot_name, api_key=api_key):
        yield partial.text
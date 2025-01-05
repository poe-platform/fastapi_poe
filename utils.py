# utils.py

import asyncio
from typing import AsyncGenerator
from fastapi_poe.types import ProtocolMessage
from fastapi_poe.client import get_bot_response
from fastapi import HTTPException
import openai


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


async def openai_partial_messages(apikey: str, botname: str, request: str) -> AsyncGenerator[str, None]:
    """
    Asynchronously stream partial messages from OpenAI's ChatCompletion API.

    Args:
        apikey (str): API key for OpenAI.
        botname (str): Model name (e.g., 'gpt-3.5-turbo').
        request (str): User's request message.

    Yields:
        str: Partial response from the bot.
    """
    openai.api_key = apikey

    try:
        # Run the blocking OpenAI API call in a separate thread to avoid blocking the event loop
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model=botname,
                messages=[
                    {"role": "system", "content": "당신은 친절한 한국어 비서입니다."},
                    {"role": "user", "content": request}
                ],
                max_tokens=100,
                stream=True  # Enable streaming
            )
        )
    except Exception as e:
        print(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect to OpenAI API.")

    try:
        # Iterate over the streamed response
        for chunk in response:
            if 'choices' in chunk:
                delta = chunk['choices'][0]['delta']
                if 'content' in delta:
                    yield delta['content']
    except Exception as e:
        print(f"Error processing OpenAI response: {e}")
        raise HTTPException(status_code=500, detail="Error processing the OpenAI response.")


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
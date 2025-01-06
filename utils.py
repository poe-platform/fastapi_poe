# utils.py

import asyncio
from typing import AsyncGenerator
from fastapi_poe.types import ProtocolMessage
from fastapi_poe.client import get_bot_response
from fastapi import HTTPException
import os
from openai import OpenAI

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

from fastapi import HTTPException
import asyncio
from openai import OpenAI

from fastapi import HTTPException
import asyncio
import openai  # Ensure you're using the official OpenAI Python library

async def openai_full_message(request: str) -> str:
    """
    Asynchronously fetch a full response from OpenAI's ChatCompletion API.

    Args:
        request (str): User's request message.

    Returns:
        str: Full response from the bot.
    """
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
    )
    try:
        # Run the blocking OpenAI API call in a separate thread to avoid blocking the event loop
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": request,
                    }
                ],
                model="gpt-4",  # Use the desired model, e.g., "gpt-3.5-turbo" or "gpt-4"
            )
        )
    except Exception as e:
        print(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect to OpenAI API.")

    try:
        # Extract the content of the assistant's reply from the response
        if 'choices' in response:
            return response['choices'][0]['message']['content']
        else:
            raise HTTPException(status_code=500, detail="Unexpected response format from OpenAI API.")
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
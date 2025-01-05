# openai_endpoints.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from utils import concat_message
from typing import AsyncGenerator
import asyncio
import openai

router = APIRouter()


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


@router.get("/openai/{botname}")
async def call_openai_bot(botname: str, request: str, apikey: str):
    """
    Endpoint to interact with OpenAI's ChatCompletion API.

    Args:
        botname (str): The model name to use (e.g., 'gpt-3.5-turbo').
        request (str): The user's input message.
        apikey (str): OpenAI API key.

    Returns:
        JSONResponse: The concatenated response from the bot.
    """


    try:
        # Obtain the async generator for partial messages
        partial_gen = openai_partial_messages(apikey, botname, request)
        
        # Concatenate the partial messages into a single string
        concated = await concat_message(partial_gen)
        
        return {"message": concated}
    except HTTPException as http_exc:
        # Propagate HTTP exceptions
        raise http_exc
    except Exception as e:
        print(f"Unexpected error in call_openai_bot: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
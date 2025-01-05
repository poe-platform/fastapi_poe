# openai_endpoints.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from utils import concat_message, openai_partial_messages

router = APIRouter()

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
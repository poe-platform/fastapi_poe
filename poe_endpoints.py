# poe_endpoints.py

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils import concat_message, get_poe_partial_messages
from fastapi_poe.types import ProtocolMessage

router = APIRouter()

class Item(BaseModel):
    apikey: str
    request: str

@router.post("/liama")
async def call_liama(item: Item):
    """
    Call Llama-2-13b Bot.
    """
    concated = await concat_message_liama(item.apikey, item.request)
    return JSONResponse(content=concated, status_code=201)

@router.post("/call/{botname}")
async def call_bot_endpoint(botname: str, item: Item):
    """
    Call a specified Bot.
    """
    concated = await concat_message_bot(item.apikey, item.request, botname)
    return JSONResponse(content=concated, status_code=201)

@router.get("/gpt3")
async def call_gpt3(request: str, apikey: str):
    """Call GPT-3.5-Turbo Bot"""
    concated = await concat_message_gpt3(apikey, request)
    return {"message": concated}

@router.get("/gpt4/{request}")
async def call_gpt4(request: str, apikey: str):
    """Call GPT-4.0 Bot"""
    concated = await concat_message_gpt4(apikey, request)
    return {"message": concated}

@router.get("/bot/{botname}")
async def call_specific_bot(botname: str, request: str, apikey: str):
    """Call a specific Bot by name"""
    concated = await concat_message_specific_bot(apikey, request, botname)
    return {"message": concated}

# Helper Functions specific to POE Endpoints

async def concat_message_liama(apikey: str, request: str) -> str:
    """
    Concatenate messages from Llama-2-13b Bot using fastapi_poe.

    Args:
        apikey (str): API key for authentication.
        request (str): User's request message.

    Returns:
        str: The concatenated response from the bot.
    """
    message = ProtocolMessage(role="user", content=request)
    partial_gen = get_poe_partial_messages(messages=[message], bot_name="Llama-2-13b", api_key=apikey)
    concated = await concat_message(partial_gen)
    return concated

async def concat_message_bot(apikey: str, request: str, botname: str) -> str:
    """
    Concatenate messages from a specified Bot using fastapi_poe.

    Args:
        apikey (str): API key for authentication.
        request (str): User's request message.
        botname (str): Name of the bot to interact with.

    Returns:
        str: The concatenated response from the bot.
    """
    message = ProtocolMessage(role="user", content=request)
    partial_gen = get_poe_partial_messages(messages=[message], bot_name=botname, api_key=apikey)
    concated = await concat_message(partial_gen)
    return concated

async def concat_message_gpt3(apikey: str, request: str) -> str:
    """
    Concatenate messages from GPT-3.5-Turbo Bot using fastapi_poe.

    Args:
        apikey (str): API key for authentication.
        request (str): User's request message.

    Returns:
        str: The concatenated response from the bot.
    """
    return await concat_message_bot(apikey, request, "GPT-3.5-Turbo")

async def concat_message_gpt4(apikey: str, request: str) -> str:
    """
    Concatenate messages from GPT-4.0 Bot using fastapi_poe.

    Args:
        apikey (str): API key for authentication.
        request (str): User's request message.

    Returns:
        str: The concatenated response from the bot.
    """
    return await concat_message_bot(apikey, request, "GPT-4.0")

async def concat_message_specific_bot(apikey: str, request: str, botname: str) -> str:
    """
    Concatenate messages from a specific bot using fastapi_poe.

    Args:
        apikey (str): API key for authentication.
        request (str): User's request message.
        botname (str): Name of the bot.

    Returns:
        str: The concatenated response from the bot.
    """
    return await concat_message_bot(apikey, request, botname)
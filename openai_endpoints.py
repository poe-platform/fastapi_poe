# openai_endpoints.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from utils import concat_message, openai_full_message
from typing import AsyncGenerator
import asyncio
#import openai
from openai import OpenAI
import json
from pydantic import BaseModel

router = APIRouter()

class OpenAIRequest(BaseModel):
    request: str

class FunctionCallRequest(BaseModel):
    request_message: str
    function_name: str
    request_json: dict  # Additional parameters or function definitions


# Define a sample function for demonstration
def get_current_time():
    from datetime import datetime
    now = datetime.utcnow()
    return now.strftime("%Y-%m-%d %H:%M:%S UTC")


# Define the function schema
function_definitions = [
    {
        "name": "get_current_time",
        "description": "Returns the current UTC time.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

@router.post("/openai/{botname}")
async def call_openai_bot(botname: str, payload: OpenAIRequest):
    
    user_request = payload.request

    try:
        client = OpenAI()

        stream = client.chat.completions.create(
            model= botname,
            messages= [{"role": "user", "content": user_request}],
            stream= True,
        )
        concated=""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                print(chunk.choices[0].delta.content, end="")

                # Obtain the async generator for partial messages
                concated += chunk.choices[0].delta.content

        return {"message": concated}
    
    except HTTPException as http_exc:
        # Propagate HTTP exceptions
        raise http_exc
    except Exception as e:
        print(f"Unexpected error in call_openai_bot: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
    

# sample request: "What's the weather like in Paris today?"
# sample json_param: "location": {"type": "string"}
# sample function_name: get_weather
@router.post("/openai/functioncall/{botname}")
async def call_openai_bot_function_calling(botname: str, payload: FunctionCallRequest):
    
    request = payload.request_message
    json_param = payload.request_json
    function_name = payload.function_name

    try:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": function_name,
                    "parameters": {
                        "type" : "object",
                        "properties": json_param
                    }
                },
            }
        ]
        print(tools)

        client = OpenAI()

        completion = client.chat.completions.create(
            model=botname,
            messages=[{"role": "user", "content": request}],
            tools=tools,
        )

        print(completion)
        return completion.choices[0].message.tool_calls
    
    except HTTPException as http_exc:
        # Propagate HTTP exceptions
        raise http_exc
    except Exception as e:
        print(f"Unexpected error in call_openai_bot: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
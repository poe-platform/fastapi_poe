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


# @router.post("/openai/function_call/{botname}")
# async def call_openai_bot_with_function(botname: str, payload: FunctionCallRequest):
#     """
#     Standalone Endpoint to interact with OpenAI's ChatCompletion API using function calling.

#     This endpoint does not include any system messages and operates independently.
#     It accepts a bot name, a request message, and a JSON payload for function calls.

#     Args:
#         botname (str): The model name to use (e.g., 'gpt-3.5-turbo').
#         payload (FunctionCallRequest): The request payload containing the message and additional JSON data.

#     Returns:
#         JSONResponse: The model's response, including function call outputs if applicable.
#     """
#     user_request = payload.request_message
#     apikey = payload.request_json.get("apikey")  # Assuming apikey is part of request_json

#     if not user_request or not apikey:
#         raise HTTPException(status_code=400, detail="Missing 'request_message' or 'apikey' in the request payload.")

#     openai.api_key = apikey

#     try:
#         # Initiate the conversation with function definitions from request_json if provided
#         # If function_definitions are dynamic, they can be passed via request_json
#         functions = payload.request_json.get("functions", function_definitions)

#         response = await asyncio.get_event_loop().run_in_executor(
#             None,
#             lambda: openai.ChatCompletion.create(
#                 model=botname,
#                 messages=[
#                     {"role": "user", "content": user_request}
#                 ],
#                 functions=functions,
#                 function_call="auto",  # Let the model decide to call a function or not
#                 max_tokens=150,
#             )
#         )
#     except Exception as e:
#         print(f"OpenAI API error: {e}")
#         raise HTTPException(status_code=500, detail="Failed to connect to OpenAI API.")

#     function_response = None
#     model_reply = ""

#     if response.choices and response.choices[0].get("message"):
#         message = response.choices[0]["message"]

#         if message.get("function_call"):
#             function_name = message["function_call"]["name"]
#             function_args = message["function_call"].get("arguments")

#             # Convert string arguments to dict
#             try:
#                 function_args = json.loads(function_args) if function_args else {}
#             except json.JSONDecodeError:
#                 function_args = {}

#             # Execute the function
#             if function_name == "get_current_time":
#                 function_response = get_current_time()
#             else:
#                 function_response = "Function not implemented."

#             # Create a new message with the function response
#             messages = [
#                 {"role": "user", "content": user_request},
#                 {"role": "assistant", "content": None, "function_call": message["function_call"]},
#                 {"role": "function", "name": function_name, "content": function_response}
#             ]

#             try:
#                 # Get the final response from the model after the function call
#                 final_response = await asyncio.get_event_loop().run_in_executor(
#                     None,
#                     lambda: openai.ChatCompletion.create(
#                         model=botname,
#                         messages=messages,
#                         max_tokens=150,
#                     )
#                 )
#                 if final_response.choices and final_response.choices[0].get("message"):
#                     model_reply = final_response.choices[0]["message"].get("content", "")
#             except Exception as e:
#                 print(f"OpenAI API error during function call processing: {e}")
#                 raise HTTPException(status_code=500, detail="Error processing the OpenAI function call.")
#         else:
#             model_reply = message.get("content", "")
#     else:
#         raise HTTPException(status_code=500, detail="No response from OpenAI API.")

#     return JSONResponse(content={"message": model_reply, "function_response": function_response}, status_code=200)


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
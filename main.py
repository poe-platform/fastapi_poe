from fastapi_poe.types import ProtocolMessage
from fastapi_poe.client import get_bot_response
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, APIRouter, File, UploadFile, Depends, Form, status
from typing import Optional, Generator, AsyncGenerator
import uvicorn
import requests
import tempfile
from clientstorage import get_clients, ClientStorage
from pydantic import BaseModel, AnyHttpUrl
import openai

app = FastAPI()

origins = ["*"]

expose_headers = [
    "Access-Control-Allow-Origin"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allow all headers
    expose_headers=expose_headers
)

@app.get('/health')
def health():
    print('health endpoint')
    return "200"

class Item(BaseModel):
    apikey: str
    request: str

@app.post("/upload/video/by_url")
async def video_upload(
    sessionid: str = Form(...),
    url: str = Form(...),
    caption: str = Form(...),
    thumbnail: Optional[UploadFile] = File(None),
    clients: ClientStorage = Depends(get_clients)
):
    """Upload video by URL and configure to feed"""
    cl = clients.get(sessionid)

    content = requests.get(url).content
    if thumbnail is not None:
        thumb = await thumbnail.read()
        return await video_upload_post(
            cl, content, caption=caption, thumbnail=thumb
        )
    return await video_upload_post(cl, content, caption=caption)

async def photo_upload_post(cl, content: bytes, **kwargs):
    with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
        fp.write(content)
        fp.flush()  # Ensure data is written to disk
        return cl.photo_upload(fp.name, **kwargs)

async def video_upload_post(cl, content: bytes, **kwargs):
    with tempfile.NamedTemporaryFile(suffix='.mp4') as fp:
        fp.write(content)
        fp.flush()  # Ensure data is written to disk
        return cl.video_upload(fp.name, **kwargs)

@app.post("/instagram/login")
async def auth_login(
    username: str = Form(...),
    password: str = Form(...),
    verification_code: Optional[str] = Form(""),
    proxy: Optional[str] = Form(""),
    locale: Optional[str] = Form(""),
    timezone: Optional[str] = Form(""),
    clients: ClientStorage = Depends(get_clients)
) -> str:
    """Login by username and password with 2FA"""
    cl = clients.client()
    if proxy:
        cl.set_proxy(proxy)

    if locale:
        cl.set_locale(locale)

    if timezone:
        cl.set_timezone_offset(timezone)

    result = cl.login(
        username,
        password,
        verification_code=verification_code
    )
    if result:
        clients.set(cl)
        return cl.sessionid
    return result

@app.post("/upload/by_url")
async def photo_upload(
    sessionid: str = Form(...),
    url: AnyHttpUrl = Form(...),
    caption: str = Form(...),
    clients: ClientStorage = Depends(get_clients)
) -> str:
    """Upload photo and configure to feed"""
    cl = clients.get(sessionid)

    content = requests.get(url).content
    await photo_upload_post(
        cl, content, caption=caption
    )
    return "success"

@app.post("/instagram/publish")
async def upload_media(
    image: UploadFile = File(...),
    sessionid: str = Form(...),
    caption: str = Form(...),
    clients: ClientStorage = Depends(get_clients)
):
    """Publish media to Instagram"""
    cl = clients.get(sessionid)
    contents = await image.read()

    try:
        await photo_upload_post(cl, contents, caption=caption)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail='There was an error uploading the file'
        )
    finally:
        await image.close()

    return JSONResponse(content="success", status_code=201)

@app.post("/liama")
async def call_liama(item: Item):
    """Call Llama-2-13b Bot"""
    concated = await concat_message(item.apikey, item.request, "Llama-2-13b")
    return JSONResponse(content=concated, status_code=201)

@app.post("/call/{botname}")
async def call_bot_endpoint(botname: str, item: Item):
    """Call a specified Bot"""
    concated = await concat_message(item.apikey, item.request, botname)
    return JSONResponse(content=concated, status_code=201)

@app.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse(content={"message": "Hello world!"}, status_code=200)

@app.get("/gpt3")
async def call_gpt3(request: str, apikey: str):
    """Call GPT-3.5-Turbo Bot"""
    concated = await concat_message(apikey, request, "GPT-3.5-Turbo")
    return {"message": concated}

@app.get("/gpt4/{request}")
async def call_gpt4(request: str, apikey: str):
    """Call GPT-4.0 Bot"""
    concated = await concat_message(apikey, request, "GPT-4.0")
    return {"message": concated}

@app.get("/bot/{botname}")
async def call_specific_bot(botname: str, request: str, apikey: str):
    """Call a specific Bot by name"""
    concated = await concat_message(apikey, request, botname)
    return {"message": concated}


@app.get("/openai/{botname}")
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






async def concat_message(apikey: str, request: str, botname: str) -> str:
    """
    Concatenate messages from the bot response.

    Args:
        apikey (str): API key for authentication.
        request (str): User request message.
        botname (str): Name of the bot to interact with.

    Returns:
        str: The concatenated response from the bot.
    """
    concated = ""
    message = ProtocolMessage(role="user", content=request)
    
    async for partial in get_bot_response(messages=[message], bot_name=botname, api_key=apikey):
        concated += partial.text
    
    return concated

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
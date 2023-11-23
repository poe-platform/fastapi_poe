from fastapi_poe.types import ProtocolMessage
from fastapi_poe.client import get_bot_response
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi import FastAPI, APIRouter, File, UploadFile, Depends, Form, status
from typing import Optional, Generator
import uvicorn
import requests
import tempfile
from clientstorage import get_clients, ClientStorage


app = FastAPI()
concated= ""
# router = APIRouter()
# router.add_api_route('/api/v2/hello-world', 
# endpoint = HelloWorld().read_hello, methods=["GET"])
# app.include_router(router)

from pydantic import BaseModel, AnyHttpUrl

@app.get('/health')
def health():
    print('health endpoint')
    return "200"

class Item(BaseModel):
    apikey: str
    request: str

async def photo_upload_post(cl, content : bytes, **kwargs):
    with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
        fp.write(content)
        return cl.photo_upload(fp.name, **kwargs)

@app.post("/instagram/login")
async def auth_login(username: str = Form(...),
                     password: str = Form(...),
                     verification_code: Optional[str] = Form(""),
                     proxy: Optional[str] = Form(""),
                     locale: Optional[str] = Form(""),
                     timezone: Optional[str] = Form(""),
                     clients: ClientStorage = Depends(get_clients)) -> str:
    """Login by username and password with 2FA
    """
    cl = clients.client()
    if proxy != "":
        cl.set_proxy(proxy)

    if locale != "":
        cl.set_locale(locale)

    if timezone != "":
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
async def photo_upload(sessionid: str = Form(...),
                       url: AnyHttpUrl = Form(...),
                       caption: str = Form(...),
                       clients: ClientStorage = Depends(get_clients)
                       ) -> str:
    """Upload photo and configure to feed
    """
    cl = clients.get(sessionid)
    
    content = requests.get(url).content
    await photo_upload_post(
        cl, content,
        caption=caption)
    return "success"



@app.post("/instagram/publish")
async def upload_media(image: UploadFile = File(...),
                       sessionid: str = Form(...),
                       caption: str = Form(...),
                       clients: ClientStorage = Depends(get_clients)):
    
    cl = clients.get(sessionid)
    #cl.login(item.account, item.password)
    contents = await image.read()

    try:
        await photo_upload_post(cl, contents, caption=caption)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail='There was an error uploading the file')
    finally:
        await image.close()

    # media = cl.photo_upload(imagepath, caption, 
    # extra_data={
    #     "custom_accessibility_caption": "alt text example",
    #     "like_and_view_counts_disabled": 1,
    #     "disable_comments": 1,
    # })

    return JSONResponse(content="success", status_code=201)


@app.post("/liama")
async def call_liama(item: Item):
    global concated # 전역변수 사용
    await concat_message(item.apikey, item.request, "Llama-2-13b")
    
    return JSONResponse(content=concated, status_code=201)

@app.post("/call/{botname}")
async def call_liama(botname: str, item: Item):
    global concated # 전역변수 사용
    await concat_message(item.apikey, item.request, botname)
    
    return JSONResponse(content=concated, status_code=201)


@app.get("/")
async def root():
    return JSONResponse(content={"message": "Hello world!"}, status_code=201)

@app.get("/gpt3")
async def call_gpt3(request: str, apikey: str):
    global concated # 전역변수 사용

    await concat_message(apikey, request, "GPT-3.5-Turbo")
    return {"message": concated}

@app.get("/gpt4/{request}")
async def call_gpt4(request: str, apikey: str):
    global concated # 전역변수 사용

    await concat_message(apikey, request, "GPT-4.0")
    return {"message": concated}

@app.get("/bot/{botname}")
async def call_bot(botname: str, request: str, apikey: str):
    global concated # use global variable

    await concat_message(apikey, request, botname)
    return {"message": concated}

async def concat_message(apikey, request, botname):
    global concated # use global variable
    concated= "" # 초기화

    message = ProtocolMessage(role="user", content=request)
    async for partial in get_bot_response(messages=[message], bot_name=botname, api_key=apikey): 
        #print(partial.text, end='')
        concated = concated + partial.text

if __name__ == "__main__":
   uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
   #test_endpoint()
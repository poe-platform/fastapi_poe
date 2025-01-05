# instagram.py

from fastapi import APIRouter, Form, File, UploadFile, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional
import requests
import tempfile
from clientstorage import get_clients, ClientStorage

router = APIRouter()

@router.post("/instagram/login")
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

@router.post("/upload/video/by_url")
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

async def video_upload_post(cl, content: bytes, **kwargs):
    with tempfile.NamedTemporaryFile(suffix='.mp4') as fp:
        fp.write(content)
        fp.flush()  # Ensure data is written to disk
        return cl.video_upload(fp.name, **kwargs)

@router.post("/upload/by_url")
async def photo_upload(
    sessionid: str = Form(...),
    url: str = Form(...),
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

async def photo_upload_post(cl, content: bytes, **kwargs):
    with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
        fp.write(content)
        fp.flush()  # Ensure data is written to disk
        return cl.photo_upload(fp.name, **kwargs)

@router.post("/instagram/publish")
async def upload_media(
    image: UploadFile = File(...),
    sessionid: str = Form(...),
    caption: str = Form(...),
    clients: ClientStorage = Depends(get_clients)
):
    """
    Publish media to Instagram.
    """
    cl = clients.get(sessionid)
    contents = await image.read()

    try:
        await photo_upload_post(cl, contents, caption=caption)
    except Exception as e:
        print(f"Error uploading media: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail='There was an error uploading the file'
        )
    finally:
        await image.close()

    return JSONResponse(content="success", status_code=201)
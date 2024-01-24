import argparse
import asyncio
import copy
import json
import logging
import os
import sys
import warnings
from typing import AsyncIterable, BinaryIO, Dict, Optional, Union

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi_poe.types import (
    AttachmentUploadResponse,
    ContentType,
    ErrorResponse,
    Identifier,
    MetaResponse,
    PartialResponse,
    QueryRequest,
    ReportErrorRequest,
    ReportFeedbackRequest,
    RequestContext,
    SettingsRequest,
    SettingsResponse,
)

logger = logging.getLogger("uvicorn.default")


class InvalidParameterError(Exception):
    pass


class AttachmentUploadError(Exception):
    pass


class LoggingMiddleware(BaseHTTPMiddleware):
    async def set_body(self, request: Request):
        receive_ = await request._receive()

        async def receive():
            return receive_

        request._receive = receive

    async def dispatch(self, request: Request, call_next):
        logger.info(f"Request: {request.method} {request.url}")
        try:
            # Per https://github.com/tiangolo/fastapi/issues/394#issuecomment-927272627
            # to avoid blocking.
            await self.set_body(request)
            body = await request.json()
            logger.debug(f"Request body: {json.dumps(body)}")
        except json.JSONDecodeError:
            logger.error("Request body: Unable to parse JSON")

        response = await call_next(request)

        logger.info(f"Response status: {response.status_code}")
        try:
            if hasattr(response, "body"):
                body = json.loads(response.body.decode())
                logger.debug(f"Response body: {json.dumps(body)}")
        except json.JSONDecodeError:
            logger.error("Response body: Unable to parse JSON")

        return response


async def http_exception_handler(request, ex):
    logger.error(ex)


http_bearer = HTTPBearer()


def auth_user(
    authorization: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> None:
    if auth_key is None:
        return
    if authorization.scheme != "Bearer" or authorization.credentials != auth_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid access key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class PoeBot:
    # Override these for your bot

    async def get_response_with_context(
        self, request: QueryRequest, context: RequestContext
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent]]:
        async for event in self.get_response(request):
            yield event

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent]]:
        """Override this to return a response to user queries."""
        yield self.text_event("hello")

    async def get_settings_with_context(
        self, setting: SettingsRequest, context: RequestContext
    ) -> SettingsResponse:
        settings = await self.get_settings(setting)
        return settings

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        """Override this to return non-standard settings."""
        return SettingsResponse()

    async def on_feedback_with_context(
        self, feedback_request: ReportFeedbackRequest, context: RequestContext
    ) -> None:
        await self.on_feedback(feedback_request)

    async def on_feedback(self, feedback_request: ReportFeedbackRequest) -> None:
        """Override this to record feedback from the user."""
        pass

    async def on_error_with_context(
        self, error_request: ReportErrorRequest, context: RequestContext
    ) -> None:
        await self.on_error(error_request)

    async def on_error(self, error_request: ReportErrorRequest) -> None:
        """Override this to record errors from the Poe server."""
        logger.error(f"Error from Poe server: {error_request}")

    # Helpers for generating responses
    def __init__(self):
        self._pending_file_attachment_tasks = {}

    async def post_message_attachment(
        self,
        access_key: str,
        message_id: Identifier,
        *,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse:
        task = asyncio.create_task(
            self._make_file_attachment_request(
                access_key=access_key,
                message_id=message_id,
                download_url=download_url,
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                is_inline=is_inline,
            )
        )
        pending_tasks_for_message = self._pending_file_attachment_tasks.get(message_id)
        if pending_tasks_for_message is None:
            pending_tasks_for_message = set()
            self._pending_file_attachment_tasks[message_id] = pending_tasks_for_message
        pending_tasks_for_message.add(task)
        try:
            return await task
        finally:
            pending_tasks_for_message.remove(task)

    async def _make_file_attachment_request(
        self,
        access_key: str,
        message_id: Identifier,
        *,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse:
        url = "https://www.quora.com/poe_api/file_attachment_3RD_PARTY_POST"

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                headers = {"Authorization": f"{access_key}"}
                if download_url:
                    if file_data or filename:
                        raise InvalidParameterError(
                            "Cannot provide filename or file_data if download_url is provided."
                        )
                    data = {
                        "message_id": message_id,
                        "is_inline": is_inline,
                        "download_url": download_url,
                    }
                    request = httpx.Request("POST", url, data=data, headers=headers)
                elif file_data and filename:
                    data = {"message_id": message_id, "is_inline": is_inline}
                    files = {
                        "file": (
                            (filename, file_data)
                            if content_type is None
                            else (filename, file_data, content_type)
                        )
                    }
                    request = httpx.Request(
                        "POST", url, files=files, data=data, headers=headers
                    )
                else:
                    raise InvalidParameterError(
                        "Must provide either download_url or file_data and filename."
                    )
                response = await client.send(request)

                if response.status_code != 200:
                    raise AttachmentUploadError(
                        f"{response.status_code}: {response.reason_phrase}"
                    )

                return AttachmentUploadResponse(
                    inline_ref=response.json().get("inline_ref")
                )

            except httpx.HTTPError:
                logger.error("An HTTP error occurred when attempting to attach file")
                raise

    async def _process_pending_attachment_requests(self, message_id):
        try:
            await asyncio.gather(
                *self._pending_file_attachment_tasks.pop(message_id, [])
            )
        except Exception:
            logger.error("Error processing pending attachment requests")
            raise

    @staticmethod
    def text_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(data=json.dumps({"text": text}), event="text")

    @staticmethod
    def replace_response_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(
            data=json.dumps({"text": text}), event="replace_response"
        )

    @staticmethod
    def done_event() -> ServerSentEvent:
        return ServerSentEvent(data="{}", event="done")

    @staticmethod
    def suggested_reply_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(data=json.dumps({"text": text}), event="suggested_reply")

    @staticmethod
    def meta_event(
        *,
        content_type: ContentType = "text/markdown",
        refetch_settings: bool = False,
        linkify: bool = True,
        suggested_replies: bool = False,
    ) -> ServerSentEvent:
        return ServerSentEvent(
            data=json.dumps(
                {
                    "content_type": content_type,
                    "refetch_settings": refetch_settings,
                    "linkify": linkify,
                    "suggested_replies": suggested_replies,
                }
            ),
            event="meta",
        )

    @staticmethod
    def error_event(
        text: Optional[str] = None,
        *,
        allow_retry: bool = True,
        error_type: Optional[str] = None,
    ) -> ServerSentEvent:
        data: Dict[str, Union[bool, str]] = {"allow_retry": allow_retry}
        if text is not None:
            data["text"] = text
        if error_type is not None:
            data["error_type"] = error_type
        return ServerSentEvent(data=json.dumps(data), event="error")

    # Internal handlers

    async def handle_report_feedback(
        self, feedback_request: ReportFeedbackRequest, context: RequestContext
    ) -> JSONResponse:
        await self.on_feedback_with_context(feedback_request, context)
        return JSONResponse({})

    async def handle_report_error(
        self, error_request: ReportErrorRequest, context: RequestContext
    ) -> JSONResponse:
        await self.on_error_with_context(error_request, context)
        return JSONResponse({})

    async def handle_settings(
        self, settings_request: SettingsRequest, context: RequestContext
    ) -> JSONResponse:
        settings = await self.get_settings_with_context(settings_request, context)
        return JSONResponse(settings.dict())

    async def handle_query(
        self, request: QueryRequest, context: RequestContext
    ) -> AsyncIterable[ServerSentEvent]:
        try:
            async for event in self.get_response_with_context(request, context):
                if isinstance(event, ServerSentEvent):
                    yield event
                elif isinstance(event, ErrorResponse):
                    yield self.error_event(
                        event.text,
                        allow_retry=event.allow_retry,
                        error_type=event.error_type,
                    )
                elif isinstance(event, MetaResponse):
                    yield self.meta_event(
                        content_type=event.content_type,
                        refetch_settings=event.refetch_settings,
                        linkify=event.linkify,
                        suggested_replies=event.suggested_replies,
                    )
                elif event.is_suggested_reply:
                    yield self.suggested_reply_event(event.text)
                elif event.is_replace_response:
                    yield self.replace_response_event(event.text)
                else:
                    yield self.text_event(event.text)
        except Exception as e:
            logger.exception("Error responding to query")
            yield self.error_event(repr(e), allow_retry=False)
        try:
            await self._process_pending_attachment_requests(request.message_id)
        except Exception as e:
            logger.exception("Error processing pending attachment requests")
            yield self.error_event(repr(e), allow_retry=False)
        yield self.done_event()


def _find_access_key(*, access_key: str, api_key: str) -> Optional[str]:
    """Figures out the access key.

    The order of preference is:
    1) access_key=
    2) $POE_ACCESS_KEY
    3) api_key=
    4) $POE_API_KEY

    """
    if access_key:
        return access_key

    environ_poe_access_key = os.environ.get("POE_ACCESS_KEY")
    if environ_poe_access_key:
        return environ_poe_access_key

    if api_key:
        warnings.warn(
            "usage of api_key is deprecated, pass your key using access_key instead",
            DeprecationWarning,
            stacklevel=3,
        )
        return api_key

    environ_poe_api_key = os.environ.get("POE_API_KEY")
    if environ_poe_api_key:
        warnings.warn(
            "usage of POE_API_KEY is deprecated, pass your key using POE_ACCESS_KEY instead",
            DeprecationWarning,
            stacklevel=3,
        )
        return environ_poe_api_key

    return None


def _verify_access_key(
    *, access_key: str, api_key: str, allow_without_key: bool = False
) -> Optional[str]:
    """Checks whether we have a valid access key and returns it."""
    _access_key = _find_access_key(access_key=access_key, api_key=api_key)
    if not _access_key:
        if allow_without_key:
            return None
        print(
            "Please provide an access key.\n"
            "You can get a key from the create_bot page at: https://poe.com/create_bot?server=1\n"
            "You can then pass the key using the access_key param to the run() or make_app() "
            "functions, or by using the POE_ACCESS_KEY environment variable."
        )
        sys.exit(1)
    if len(_access_key) != 32:
        print("Invalid access key (should be 32 characters)")
        sys.exit(1)
    return _access_key


def make_app(
    bot: PoeBot,
    access_key: str = "",
    *,
    api_key: str = "",
    allow_without_key: bool = False,
) -> FastAPI:
    """Create an app object. Arguments are as for run()."""
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, http_exception_handler)

    global auth_key
    auth_key = _verify_access_key(
        access_key=access_key, api_key=api_key, allow_without_key=allow_without_key
    )

    @app.get("/")
    async def index() -> Response:
        url = "https://poe.com/create_bot?server=1"
        return HTMLResponse(
            "<html><body><h1>FastAPI Poe bot server</h1><p>Congratulations! Your server"
            " is running. To connect it to Poe, create a bot at <a"
            f' href="{url}">{url}</a>.</p></body></html>'
        )

    @app.post("/")
    async def poe_post(request: Request, dict=Depends(auth_user)) -> Response:
        request_body = await request.json()
        request_body["http_request"] = request
        if request_body["type"] == "query":
            return EventSourceResponse(
                bot.handle_query(
                    QueryRequest.parse_obj(
                        {
                            **request_body,
                            "access_key": auth_key or "<missing>",
                            "api_key": auth_key or "<missing>",
                        }
                    ),
                    RequestContext(http_request=request),
                )
            )
        elif request_body["type"] == "settings":
            return await bot.handle_settings(
                SettingsRequest.parse_obj(request_body),
                RequestContext(http_request=request),
            )
        elif request_body["type"] == "report_feedback":
            return await bot.handle_report_feedback(
                ReportFeedbackRequest.parse_obj(request_body),
                RequestContext(http_request=request),
            )
        elif request_body["type"] == "report_error":
            return await bot.handle_report_error(
                ReportErrorRequest.parse_obj(request_body),
                RequestContext(http_request=request),
            )
        else:
            raise HTTPException(status_code=501, detail="Unsupported request type")

    # Uncomment this line to print out request and response
    # app.add_middleware(LoggingMiddleware)
    return app


def run(
    bot: PoeBot,
    access_key: str = "",
    *,
    api_key: str = "",
    allow_without_key: bool = False,
) -> None:
    """
    Run a Poe bot server using FastAPI.

    :param bot: The bot object.
    :param access_key: The access key to use. If not provided, the server tries to read
    the POE_ACCESS_KEY environment variable. If that is not set, the server will
    refuse to start, unless *allow_without_key* is True.
    :param api_key: The previous name of access_key. This param is deprecated and will be
    removed in a future version
    :param allow_without_key: If True, the server will start even if no access key
    is provided. Requests will not be checked against any key. If an access key
    is provided, it is still checked.

    """

    app = make_app(
        bot, access_key=access_key, api_key=api_key, allow_without_key=allow_without_key
    )

    parser = argparse.ArgumentParser("FastAPI sample Poe bot server")
    parser.add_argument("-p", "--port", type=int, default=8080)
    args = parser.parse_args()
    port = args.port

    logger.info("Starting")
    import uvicorn.config

    log_config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    log_config["formatters"]["default"][
        "fmt"
    ] = "%(asctime)s - %(levelname)s - %(message)s"
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=log_config)

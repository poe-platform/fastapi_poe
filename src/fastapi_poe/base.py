import argparse
import asyncio
import copy
import json
import logging
import os
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import (
    AsyncIterable,
    Awaitable,
    BinaryIO,
    Callable,
    Dict,
    Optional,
    Sequence,
    Union,
)

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
from typing_extensions import deprecated, overload

from fastapi_poe.client import PROTOCOL_VERSION, sync_bot_settings
from fastapi_poe.templates import (
    IMAGE_VISION_ATTACHMENT_TEMPLATE,
    TEXT_ATTACHMENT_TEMPLATE,
    URL_ATTACHMENT_TEMPLATE,
)
from fastapi_poe.types import (
    AttachmentUploadResponse,
    ContentType,
    ErrorResponse,
    Identifier,
    MetaResponse,
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    ReportErrorRequest,
    ReportFeedbackRequest,
    ReportReactionRequest,
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
    async def set_body(self, request: Request) -> None:
        receive_ = await request._receive()

        async def receive() -> Message:
            return receive_

        request._receive = receive

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
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
                body = json.loads(bytes(response.body).decode())
                logger.debug(f"Response body: {json.dumps(body)}")
        except json.JSONDecodeError:
            logger.error("Response body: Unable to parse JSON")

        return response


async def http_exception_handler(request: Request, ex: Exception) -> Response:
    logger.error(ex)
    return Response(status_code=500, content="Internal server error")


http_bearer = HTTPBearer()


@dataclass
class PoeBot:
    """

    The class that you use to define your bot behavior. Once you define your PoeBot class, you
    pass it to `make_app` to create a FastAPI app that serves your bot.

    #### Parameters:
    - `path` (`str = "/"`): This is the path at which your bot is served. By default, it's
    set to "/" but this is something you can adjust. This is especially useful if you want to serve
    multiple bots from one server.
    - `access_key` (`Optional[str] = None`): This is the access key for your bot and when
    provided is used to validate that the requests are coming from a trusted source. This access key
    should be the same one that you provide when integrating your bot with Poe at:
    https://poe.com/create_bot?server=1. You can also set this to None but certain features like
    file output that mandate an `access_key` will not be available for your bot.
    - `should_insert_attachment_messages` (`bool = True`): A flag to decide whether to parse out
    content from attachments and insert them as messages into the conversation. This is set to
    `True`by default and we recommend leaving on since it allows your bot to comprehend attachments
    uploaded by users by default.
    - `concat_attachments_to_message` (`bool = False`): Deprecated. This was used to concatenate
    attachment content to the message body. This is now handled by `insert_attachment_messages`.
    This will be removed in a future release.

    """

    path: str = "/"  # Path where this bot will be exposed
    access_key: Optional[str] = None  # Access key for this bot
    bot_name: Optional[str] = None  # Name of the bot using this PoeBot instance in Poe
    should_insert_attachment_messages: bool = (
        True  # Whether to insert attachment messages into the conversation
    )
    concat_attachments_to_message: bool = False  # Deprecated

    # Override these for your bot
    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent]]:
        """

        Override this to define your bot's response given a user query.
        #### Parameters:
        - `request` (`QueryRequest`): an object representing the chat response request from Poe.
        This will contain information about the chat state among other things.

        #### Returns:
        - `AsyncIterable[PartialResponse]`: objects representing your
        response to the Poe servers. This is what gets displayed to the user.

        Example usage:
        ```python
        async def get_response(self, request: fp.QueryRequest) -> AsyncIterable[fp.PartialResponse]:
            last_message = request.query[-1].content
            yield fp.PartialResponse(text=last_message)
        ```

        """
        yield self.text_event("hello")

    async def get_response_with_context(
        self, request: QueryRequest, context: RequestContext
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent]]:
        """

        A version of `get_response` that also includes the request context information. By
        default, this will call `get_response`.
        #### Parameters:
        - `request` (`QueryRequest`): an object representing the chat response request from Poe.
        This will contain information about the chat state among other things.
        - `context` (`RequestContext`): an object representing the current HTTP request.

        #### Returns:
        - `AsyncIterable[Union[PartialResponse, ErrorResponse]]`: objects representing your
        response to the Poe servers. This is what gets displayed to the user.

        """
        async for event in self.get_response(request):
            yield event

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        """

        Override this to define your bot's settings.

        #### Parameters:
        - `setting` (`SettingsRequest`): An object representing the settings request.

        #### Returns:
        - `SettingsResponse`: An object representing the settings you want to use for your bot.

        """
        return SettingsResponse()

    async def get_settings_with_context(
        self, setting: SettingsRequest, context: RequestContext
    ) -> SettingsResponse:
        """

        A version of `get_settings` that also includes the request context information. By
        default, this will call `get_settings`.

        #### Parameters:
        - `setting` (`SettingsRequest`): An object representing the settings request.
        - `context` (`RequestContext`): an object representing the current HTTP request.

        #### Returns:
        - `SettingsResponse`: An object representing the settings you want to use for your bot.

        """
        settings = await self.get_settings(setting)
        return settings

    async def on_feedback(self, feedback_request: ReportFeedbackRequest) -> None:
        """

        Override this to record feedback from the user.
        #### Parameters:
        - `feedback_request` (`ReportFeedbackRequest`): An object representing the Feedback rqeuest
        from Poe. This is sent out when a user provides feedback on a response on your bot.
        #### Returns: `None`

        """
        pass

    async def on_feedback_with_context(
        self, feedback_request: ReportFeedbackRequest, context: RequestContext
    ) -> None:
        """

        A version of `on_feedback` that also includes the request context information. By
        default, this will call `on_feedback`.

        #### Parameters:
        - `feedback_request` (`ReportFeedbackRequest`): An object representing a feedback rqeuest
        from Poe. This is sent out when a user provides feedback on a response on your bot.
        - `context` (`RequestContext`): an object representing the current HTTP request.
        #### Returns: `None`

        """
        await self.on_feedback(feedback_request)

    async def on_reaction_with_context(
        self, reaction_request: ReportReactionRequest, context: RequestContext
    ) -> None:
        """

        Override this to record reaction from the user. This also includes the request context
        information.

        #### Parameters:
        - `reaction_request` (`ReportReactionRequest`): An object representing a reaction request
        from Poe. This is sent out when a user provides reaction on a response on your bot.
        - `context` (`RequestContext`): an object representing the current HTTP request.
        #### Returns: `None`

        """
        pass

    async def on_error(self, error_request: ReportErrorRequest) -> None:
        """

        Override this to record errors from the Poe server.
        #### Parameters:
        - `error_request` (`ReportErrorRequest`): An object representing an error request from Poe.
        This is sent out when the Poe server runs into an issue processing the response from your
        bot.
        #### Returns: `None`

        """
        logger.error(f"Error from Poe server: {error_request}")

    async def on_error_with_context(
        self, error_request: ReportErrorRequest, context: RequestContext
    ) -> None:
        """

        A version of `on_error` that also includes the request context information. By
        default, this will call `on_error`.

        #### Parameters:
        - `error_request` (`ReportErrorRequest`): An object representing an error request from Poe.
        This is sent out when the Poe server runs into an issue processing the response from your
        bot.
        - `context` (`RequestContext`): an object representing the current HTTP request.
        #### Returns: `None`

        """
        await self.on_error(error_request)

    # Helpers for generating responses
    def __post_init__(self) -> None:
        self._pending_file_attachment_tasks = {}

    # This overload leaves access_key as the first argument, but is deprecated.
    @overload
    @deprecated(
        "The access_key parameter is deprecated. "
        "Set the access_key when creating the Bot object instead."
    )
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
    ) -> AttachmentUploadResponse: ...

    # This overload requires all parameters to be passed as keywords
    @overload
    async def post_message_attachment(
        self,
        *,
        message_id: Identifier,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse: ...

    async def post_message_attachment(
        self,
        access_key: Optional[str] = None,
        message_id: Optional[Identifier] = None,
        *,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse:
        """

        Used to output an attachment in your bot's response.

        #### Parameters:
        - `message_id` (`Identifier`): The message id associated with the current QueryRequest
        object. **Important**: This must be the request that is currently being handled by
        get_response. Attempting to attach files to previously handled requests will fail.
        - `access_key` (`str`): The access_key corresponding to your bot. This is needed to ensure
        that file upload requests are coming from an authorized source.
        - `download_url` (`Optional[str] = None`): A url to the file to be attached to the message.
        - `file_data` (`Optional[Union[bytes, BinaryIO]] = None`): The contents of the file to be
        uploaded. This should be a bytes-like or file object.
        - `filename` (`Optional[str] = None`): The name of the file to be attached.
        #### Returns:
        - `AttachmentUploadResponse`

        **Note**: You need to provide either the `download_url` or both of `file_data` and
        `filename`.

        """
        if message_id is None:
            raise InvalidParameterError("message_id parameter is required")

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
        message_id: Identifier,
        *,
        access_key: Optional[str] = None,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse:
        if self.access_key:
            if access_key:
                warnings.warn(
                    "Bot already has an access key, access_key parameter is not needed.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                attachment_access_key = access_key
            else:
                attachment_access_key = self.access_key
        else:
            if access_key is None:
                raise InvalidParameterError(
                    "access_key parameter is required if bot is not"
                    + " provided with an access_key when make_app is called."
                )
            attachment_access_key = access_key
        url = "https://www.quora.com/poe_api/file_attachment_3RD_PARTY_POST"

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                headers = {"Authorization": f"{attachment_access_key}"}
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
                    error_pieces = [piece async for piece in response.aiter_text()]
                    raise AttachmentUploadError(
                        f"{response.status_code} {response.reason_phrase}: {''.join(error_pieces)}"
                    )

                response_data = response.json()
                return AttachmentUploadResponse(
                    inline_ref=response_data.get("inline_ref"),
                    attachment_url=response_data.get("attachment_url"),
                )

            except httpx.HTTPError:
                logger.error("An HTTP error occurred when attempting to attach file")
                raise

    async def _process_pending_attachment_requests(
        self, message_id: Identifier
    ) -> None:
        try:
            await asyncio.gather(
                *self._pending_file_attachment_tasks.pop(message_id, [])
            )
        except Exception:
            logger.error("Error processing pending attachment requests")
            raise

    @deprecated(
        "This method is deprecated. Use `insert_attachment_messages` instead."
        "This method will be removed in a future release."
    )
    def concat_attachment_content_to_message_body(
        self, query_request: QueryRequest
    ) -> QueryRequest:
        """

        Concatenate received attachment file content into the message body. This will be called
        by default if `concat_attachments_to_message` is set to `True` but can also be used
        manually if needed.

        #### Parameters:
        - `query_request` (`QueryRequest`): the request object from Poe.
        #### Returns:
        - `QueryRequest`: the request object after the attachments are unpacked and added to the
        message body.

        """
        last_message = query_request.query[-1]
        concatenated_content = last_message.content
        for attachment in last_message.attachments:
            if attachment.parsed_content:
                if attachment.content_type == "text/html":
                    url_attachment_content = URL_ATTACHMENT_TEMPLATE.format(
                        attachment_name=attachment.name,
                        content=attachment.parsed_content,
                    )
                    concatenated_content = (
                        f"{concatenated_content}\n\n{url_attachment_content}"
                    )
                elif "text" in attachment.content_type:
                    text_attachment_content = TEXT_ATTACHMENT_TEMPLATE.format(
                        attachment_name=attachment.name,
                        attachment_parsed_content=attachment.parsed_content,
                    )
                    concatenated_content = (
                        f"{concatenated_content}\n\n{text_attachment_content}"
                    )
                elif "image" in attachment.content_type:
                    parsed_content_filename = attachment.parsed_content.split("***")[0]
                    parsed_content_text = attachment.parsed_content.split("***")[1]
                    image_attachment_content = IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                        filename=parsed_content_filename,
                        parsed_image_description=parsed_content_text,
                    )
                    concatenated_content = (
                        f"{concatenated_content}\n\n{image_attachment_content}"
                    )
        modified_last_message = last_message.model_copy(
            update={"content": concatenated_content}
        )
        modified_query = query_request.model_copy(
            update={"query": query_request.query[:-1] + [modified_last_message]}
        )
        return modified_query

    def insert_attachment_messages(self, query_request: QueryRequest) -> QueryRequest:
        """

        Insert messages containing the contents of each user attachment right before the last user
        message. This ensures the bot can consider all relevant information when generating a
        response. This will be called by default if `should_insert_attachment_messages` is set to
        `True` but can also be used manually if needed.

        #### Parameters:
        - `query_request` (`QueryRequest`): the request object from Poe.
        #### Returns:
        - `QueryRequest`: the request object after the attachments are unpacked and added to the
        message body.

        """
        last_message = query_request.query[-1]
        text_attachment_messages = []
        image_attachment_messages = []
        for attachment in last_message.attachments:
            if attachment.parsed_content:
                if attachment.content_type == "text/html":
                    url_attachment_content = URL_ATTACHMENT_TEMPLATE.format(
                        attachment_name=attachment.name,
                        content=attachment.parsed_content,
                    )
                    text_attachment_messages.append(
                        ProtocolMessage(role="user", content=url_attachment_content)
                    )
                elif "text" in attachment.content_type:
                    text_attachment_content = TEXT_ATTACHMENT_TEMPLATE.format(
                        attachment_name=attachment.name,
                        attachment_parsed_content=attachment.parsed_content,
                    )
                    text_attachment_messages.append(
                        ProtocolMessage(role="user", content=text_attachment_content)
                    )
                elif "image" in attachment.content_type:
                    parsed_content_filename = attachment.parsed_content.split("***")[0]
                    parsed_content_text = attachment.parsed_content.split("***")[1]
                    image_attachment_content = IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                        filename=parsed_content_filename,
                        parsed_image_description=parsed_content_text,
                    )
                    image_attachment_messages.append(
                        ProtocolMessage(role="user", content=image_attachment_content)
                    )
        modified_query = query_request.model_copy(
            update={
                "query": query_request.query[:-1]
                + text_attachment_messages
                + image_attachment_messages
                + [last_message]
            }
        )
        return modified_query

    def make_prompt_author_role_alternated(
        self, protocol_messages: Sequence[ProtocolMessage]
    ) -> Sequence[ProtocolMessage]:
        """

        Concatenate consecutive messages from the same author into a single message. This is useful
        for LLMs that require role alternation between user and bot messages.

        #### Parameters:
        - `protocol_messages` (`Sequence[ProtocolMessage]`): the messages to make alternated.
        #### Returns:
        - `Sequence[ProtocolMessage]`: the modified messages.

        """
        new_messages = []

        for protocol_message in protocol_messages:
            if new_messages and protocol_message.role == new_messages[-1].role:
                prev_message = new_messages.pop()
                new_content = prev_message.content + "\n\n" + protocol_message.content

                new_attachments = []
                added_attachment_urls = set()
                for attachment in (
                    protocol_message.attachments + prev_message.attachments
                ):
                    if attachment.url not in added_attachment_urls:
                        added_attachment_urls.add(attachment.url)
                        new_attachments.append(attachment)

                new_messages.append(
                    prev_message.model_copy(
                        update={"content": new_content, "attachments": new_attachments}
                    )
                )
            else:
                new_messages.append(protocol_message)

        return new_messages

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
        raw_response: Optional[object] = None,
        allow_retry: bool = True,
        error_type: Optional[str] = None,
    ) -> ServerSentEvent:
        data: Dict[str, Union[bool, str]] = {"allow_retry": allow_retry}
        if text is not None:
            data["text"] = text
        if raw_response is not None:
            data["raw_response"] = repr(raw_response)
        if error_type is not None:
            data["error_type"] = error_type
        return ServerSentEvent(data=json.dumps(data), event="error")

    # Internal handlers

    async def handle_report_feedback(
        self, feedback_request: ReportFeedbackRequest, context: RequestContext
    ) -> JSONResponse:
        await self.on_feedback_with_context(feedback_request, context)
        return JSONResponse({})

    async def handle_report_reaction(
        self, reaction_request: ReportReactionRequest, context: RequestContext
    ) -> JSONResponse:
        await self.on_reaction_with_context(reaction_request, context)
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
            if self.should_insert_attachment_messages:
                request = self.insert_attachment_messages(query_request=request)
            elif self.concat_attachments_to_message:
                warnings.warn(
                    "concat_attachments_to_message is deprecated. "
                    "Use should_insert_attachment_messages instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                request = self.concat_attachment_content_to_message_body(
                    query_request=request
                )
            async for event in self.get_response_with_context(request, context):
                if isinstance(event, ServerSentEvent):
                    yield event
                elif isinstance(event, ErrorResponse):
                    yield self.error_event(
                        event.text,
                        raw_response=event.raw_response,
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
            yield self.error_event(
                "The bot encountered an unexpected issue.",
                raw_response=e,
                allow_retry=False,
            )
        try:
            await self._process_pending_attachment_requests(request.message_id)
        except Exception as e:
            logger.exception("Error processing pending attachment requests")
            yield self.error_event(
                "The bot encountered an unexpected issue.",
                raw_response=e,
                allow_retry=False,
            )
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


def _add_routes_for_bot(app: FastAPI, bot: PoeBot) -> None:
    async def index() -> Response:
        url = "https://poe.com/create_bot?server=1"
        return HTMLResponse(
            "<html><body><h1>FastAPI Poe bot server</h1><p>Congratulations! Your server"
            " is running. To connect it to Poe, create a bot at <a"
            f' href="{url}">{url}</a>.</p></body></html>'
        )

    def auth_user(
        authorization: HTTPAuthorizationCredentials = Depends(http_bearer),
    ) -> None:
        if bot.access_key is None:
            return
        if (
            authorization.scheme != "Bearer"
            or authorization.credentials != bot.access_key
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid access key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def poe_post(request: Request, dict: object = Depends(auth_user)) -> Response:
        request_body = await request.json()
        request_body["http_request"] = request
        if request_body["type"] == "query":
            return EventSourceResponse(
                bot.handle_query(
                    QueryRequest.parse_obj(
                        {
                            **request_body,
                            "access_key": bot.access_key or "<missing>",
                            "api_key": bot.access_key or "<missing>",
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
        elif request_body["type"] == "report_reaction":
            return await bot.handle_report_reaction(
                ReportReactionRequest.parse_obj(request_body),
                RequestContext(http_request=request),
            )
        elif request_body["type"] == "report_error":
            return await bot.handle_report_error(
                ReportErrorRequest.parse_obj(request_body),
                RequestContext(http_request=request),
            )
        else:
            raise HTTPException(status_code=501, detail="Unsupported request type")

    app.get(bot.path)(index)
    app.post(bot.path)(poe_post)


def make_app(
    bot: Union[PoeBot, Sequence[PoeBot]],
    access_key: str = "",
    *,
    bot_name: str = "",
    api_key: str = "",
    allow_without_key: bool = False,
    app: Optional[FastAPI] = None,
) -> FastAPI:
    """

    Create an app object for your bot(s).

    #### Parameters:
    - `bot` (`Union[PoeBot, Sequence[PoeBot]]`): A bot object or a list of bot objects if you want
    to host multiple bots on one server.
    - `access_key` (`str = ""`): The access key to use.  If not provided, the server tries to
    read the POE_ACCESS_KEY environment variable. If that is not set, the server will
    refuse to start, unless `allow_without_key` is True. If multiple bots are provided,
    the access key must be provided as part of the bot object.
    - `allow_without_key` (`bool = False`): If True, the server will start even if no access
    key is provided. Requests will not be checked against any key. If an access key is provided, it
    is still checked.
    - `app` (`Optional[FastAPI] = None`): A FastAPI app instance. If provided, the app will be
    configured with the provided bots, access keys, and other settings. If not provided, a new
    FastAPI application instance will be created and configured.
    #### Returns:
    - `FastAPI`: A FastAPI app configured to serve your bot when run.

    """
    if app is None:
        app = FastAPI()
    app.add_exception_handler(RequestValidationError, http_exception_handler)

    if isinstance(bot, PoeBot):
        if bot.access_key is None:
            bot.access_key = _verify_access_key(
                access_key=access_key,
                api_key=api_key,
                allow_without_key=allow_without_key,
            )
        elif access_key:
            raise ValueError(
                "Cannot provide access_key if the bot object already has an access key"
            )
        elif api_key:
            raise ValueError(
                "Cannot provide api_key if the bot object already has an access key"
            )

        if bot.bot_name is None:
            bot.bot_name = bot_name
        elif bot_name:
            raise ValueError(
                "Cannot provide bot_name if the bot object already has a bot_name"
            )
        bots = [bot]
    else:
        if access_key or api_key or bot_name:
            raise ValueError(
                "When serving multiple bots, the access_key/bot_name must be set on each bot"
            )
        bots = bot

    # Ensure paths are unique
    path_to_bots = defaultdict(list)
    for bot in bots:
        path_to_bots[bot.path].append(bot)
    for path, bots_of_path in path_to_bots.items():
        if len(bots_of_path) > 1:
            raise ValueError(
                f"Multiple bots are trying to use the same path: {path}: {bots_of_path}. "
                "Please use a different path for each bot."
            )

    for bot_obj in bots:
        if bot_obj.access_key is None and not allow_without_key:
            raise ValueError(f"Missing access key on {bot_obj}")
        _add_routes_for_bot(app, bot_obj)
        if not bot_obj.bot_name or not bot_obj.access_key:
            logger.warning("\n************* Warning *************")
            logger.warning(
                "Bot name or access key is not set for PoeBot.\n"
                "Bot settings will NOT be synced automatically on server start/update."
                "Please remember to sync bot settings manually.\n\n"
                "For more information, see: https://creator.poe.com/docs/server-bots-functional-guides#updating-bot-settings"
            )
            logger.warning("\n************* Warning *************")
        else:
            try:
                settings_response = asyncio.run(
                    bot_obj.get_settings(
                        SettingsRequest(version=PROTOCOL_VERSION, type="settings")
                    )
                )
                sync_bot_settings(
                    bot_name=bot_obj.bot_name,
                    settings=settings_response.model_dump(),
                    access_key=bot_obj.access_key,
                )
            except Exception as e:
                logger.error("\n*********** Error ***********")
                logger.error(
                    f"Bot settings sync failed for {bot_obj.bot_name}: \n{e}\n\n"
                )
                logger.error("Please sync bot settings manually.\n\n")
                logger.error(
                    "For more information, see: https://creator.poe.com/docs/server-bots-functional-guides#updating-bot-settings"
                )
                logger.error("\n*********** Error ***********")

    # Uncomment this line to print out request and response
    # app.add_middleware(LoggingMiddleware)
    return app


def run(
    bot: Union[PoeBot, Sequence[PoeBot]],
    access_key: str = "",
    *,
    api_key: str = "",
    allow_without_key: bool = False,
    app: Optional[FastAPI] = None,
) -> None:
    """

    Serve a poe bot using a FastAPI app. This function should be used when you are running the
    bot locally. The parameters are the same as they are for `make_app`.

    #### Returns: `None`

    """

    app = make_app(
        bot,
        access_key=access_key,
        api_key=api_key,
        allow_without_key=allow_without_key,
        app=app,
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

import asyncio
import httpx
import logging
from typing import Any, BinaryIO, Dict, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal, TypeAlias

logger = logging.getLogger("uvicorn.default")

Identifier: TypeAlias = str
FeedbackType: TypeAlias = Literal["like", "dislike"]
ContentType: TypeAlias = Literal["text/markdown", "text/plain"]
ErrorType: TypeAlias = Literal["user_message_too_long"]


class MessageFeedback(BaseModel):
    """Feedback for a message as used in the Poe protocol."""

    type: FeedbackType
    reason: Optional[str]


class Attachment(BaseModel):
    url: str
    content_type: str
    name: str


class AttachmentUploadResponse(BaseModel):
    inline_ref: Optional[str]


class ProtocolMessage(BaseModel):
    """A message as used in the Poe protocol."""

    role: Literal["system", "user", "bot"]
    content: str
    content_type: ContentType = "text/markdown"
    timestamp: int = 0
    message_id: str = ""
    feedback: List[MessageFeedback] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)


class InvalidParameterError(Exception):
    pass


class AttachmentUploadError(Exception):
    pass


class BaseRequest(BaseModel):
    """Common data for all requests."""

    version: str
    type: Literal["query", "settings", "report_feedback", "report_error"]


class QueryRequest(BaseRequest):
    """Request parameters for a query request."""

    query: List[ProtocolMessage]
    user_id: Identifier
    conversation_id: Identifier
    message_id: Identifier
    metadata: Identifier = ""
    api_key: str = "<missing>"
    access_key: str = "<missing>"
    temperature: float = 0.7
    skip_system_prompt: bool = False
    logit_bias: Dict[str, float] = {}
    stop_sequences: List[str] = []

    _pending_tasks: Set[asyncio.Task] = set()

    async def post_message_attachment(
        self,
        *,
        download_url: Optional[str] = None,
        file_data: Optional[Union[bytes, BinaryIO]] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        is_inline: bool = False,
    ) -> AttachmentUploadResponse:
        task = asyncio.create_task(
            self._make_file_attachment_request(
                download_url=download_url,
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                is_inline=is_inline,
            )
        )
        self._pending_tasks.add(task)
        try:
            return await task
        finally:
            self._pending_tasks.remove(task)

    async def _make_file_attachment_request(
        self,
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
                headers = {"Authorization": f"{self.access_key}"}
                if download_url:
                    if file_data or filename:
                        raise InvalidParameterError(
                            "Cannot provide filename or file_data if download_url is provided."
                        )
                    data = {
                        "message_id": self.message_id,
                        "is_inline": is_inline,
                        "download_url": download_url,
                    }
                    request = httpx.Request("POST", url, data=data, headers=headers)
                elif file_data and filename:
                    data = {"message_id": self.message_id, "is_inline": is_inline}
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


class SettingsRequest(BaseRequest):
    """Request parameters for a settings request."""


class ReportFeedbackRequest(BaseRequest):
    """Request parameters for a report_feedback request."""

    message_id: Identifier
    user_id: Identifier
    conversation_id: Identifier
    feedback_type: FeedbackType


class ReportErrorRequest(BaseRequest):
    """Request parameters for a report_error request."""

    message: str
    metadata: Dict[str, Any]


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_clear_window_secs: Optional[int] = None  # deprecated
    allow_user_context_clear: bool = True  # deprecated
    server_bot_dependencies: Dict[str, int] = Field(default_factory=dict)
    allow_attachments: bool = False
    introduction_message: str = ""


class PartialResponse(BaseModel):
    """Representation of a (possibly partial) response from a bot."""

    # These objects are usually instantiated in user code, so we
    # disallow extra fields to prevent mistakes.
    model_config = ConfigDict(extra="forbid")

    text: str
    """Partial response text.

    If the final bot response is "ABC", you may see a sequence
    of PartialResponse objects like PartialResponse(text="A"),
    PartialResponse(text="B"), PartialResponse(text="C").

    """

    data: Optional[Dict[str, Any]] = None
    """Used when a bot returns the json event."""

    raw_response: object = None
    """For debugging, the raw response from the bot."""

    full_prompt: Optional[str] = None
    """For debugging, contains the full prompt as sent to the bot."""

    request_id: Optional[str] = None
    """May be set to an internal identifier for the request."""

    is_suggested_reply: bool = False
    """If true, this is a suggested reply."""

    is_replace_response: bool = False
    """If true, this text should completely replace the previous bot text."""


class ErrorResponse(PartialResponse):
    """Communicate errors from server bots."""

    allow_retry: bool = False
    error_type: Optional[ErrorType] = None


class MetaResponse(PartialResponse):
    """Communicate 'meta' events from server bots."""

    linkify: bool = True
    suggested_replies: bool = True
    content_type: ContentType = "text/markdown"
    refetch_settings: bool = False


class ToolDefinition(BaseModel):
    class FunctionDefinition(BaseModel):
        class ParametersDefinition(BaseModel):
            type: str
            properties: Dict[str, object]
            required: Optional[List[str]] = None

        name: str
        description: str
        parameters: ParametersDefinition

    type: str
    function: FunctionDefinition


class ToolCallDefinition(BaseModel):
    class FunctionDefinition(BaseModel):
        name: str
        arguments: str

    id: str
    type: str
    function: FunctionDefinition


class ToolResultDefinition(BaseModel):
    role: str
    name: str
    tool_call_id: str
    content: str

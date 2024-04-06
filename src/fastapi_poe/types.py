from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal, TypeAlias

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
    parsed_content: Optional[str] = None


class ProtocolMessage(BaseModel):
    """A message as used in the Poe protocol."""

    role: Literal["system", "user", "bot"]
    content: str
    content_type: ContentType = "text/markdown"
    timestamp: int = 0
    message_id: str = ""
    feedback: List[MessageFeedback] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)


class RequestContext(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    http_request: Request


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
    expand_text_attachments: bool = True
    enable_image_comprehension: bool = False
    enforce_author_role_alternation: bool = False


class AttachmentUploadResponse(BaseModel):
    inline_ref: Optional[str]


class PartialResponse(BaseModel):
    """

    Representation of a (possibly partial) response from a bot. Yield this in
    `PoeBot.get_response` or `PoeBot.get_response_with_context` to communicate your response to Poe.

    #### Parameters:
    - `text`: The actual text you want to display to the user. Note that this should solely
    be the text in the next token since Poe will automatically concatenate all tokens before
    displaying the response to the user.
    - `data`: Used to send arbitrary json data to Poe. This is currently only used for OpenAI
    function calling.
    - `is_suggested_reply`: Seting this to true will create a suggested reply with the provided
    text value.
    - `is_replace_response`: Setting this to true will clear out the previously displayed text
    to the user and replace it with the provided text value.


    """

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
    """

    Similar to `PartialResponse`. Yield this to communicate errors from your bot.

    #### Parameters:
    - `allow_retry`: Whether or not to allow a user to retry on error.
    - `error_type`: An enum indicating what error to display.

    """

    allow_retry: bool = False
    error_type: Optional[ErrorType] = None


class MetaResponse(PartialResponse):
    """

    Similar to `Partial Response`. Yield this to communicate `meta` events from server bots.

    #### Parameters:
    - `suggested_replies`: Whether or not to enable suggested replies.
    - `content_type`: Used to describe the format of the response. The currently supported values
    are `text/plain` and `text/markdown`.
    - `refetch_settings`: Used to trigger a settings fetch request from Poe. A more robust way
    to trigger this is documented at: https://creator.poe.com/docs/server-bots-functional-guides#updating-bot-settings

    """

    linkify: bool = True  # deprecated
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

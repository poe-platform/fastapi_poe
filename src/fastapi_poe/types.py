from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal, TypeAlias

Identifier: TypeAlias = str
FeedbackType: TypeAlias = Literal["like", "dislike"]
ContentType: TypeAlias = Literal["text/markdown", "text/plain"]
ErrorType: TypeAlias = Literal["user_message_too_long", "insufficient_fund"]


class MessageFeedback(BaseModel):
    """

    Feedback for a message as used in the Poe protocol.
    #### Fields:
    - `type` (`FeedbackType`)
    - `reason` (`Optional[str]`)

    """

    type: FeedbackType
    reason: Optional[str]


class CostItem(BaseModel):
    """

    An object representing a cost item used for authorization and charge request.
    #### Fields:
    - `amount_usd_milli_cents` (`int`)
    - `description` (`str`)

    """

    amount_usd_milli_cents: int
    description: Optional[str] = None


class Attachment(BaseModel):
    """

    Attachment included in a protocol message.
    #### Fields:
    - `url` (`str`)
    - `content_type` (`str`)
    - `name` (`str`)
    - `parsed_content` (`Optional[str] = None`)

    """

    url: str
    content_type: str
    name: str
    parsed_content: Optional[str] = None


class ProtocolMessage(BaseModel):
    """

    A message as used in the Poe protocol.
    #### Fields:
    - `role` (`Literal["system", "user", "bot"]`)
    - `sender_id` (`Optional[str]`)
    - `content` (`str`)
    - `content_type` (`ContentType="text/markdown"`)
    - `timestamp` (`int = 0`)
    - `message_id` (`str = ""`)
    - `feedback` (`List[MessageFeedback] = []`)
    - `attachments` (`List[Attachment] = []`)

    """

    role: Literal["system", "user", "bot"]
    sender_id: Optional[str] = None
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
    type: Literal[
        "query", "settings", "report_feedback", "report_reaction", "report_error"
    ]


class QueryRequest(BaseRequest):
    """

    Request parameters for a query request.
    #### Fields:
    - `query` (`List[ProtocolMessage]`): list of message representing the current state of the chat.
    - `user_id` (`Identifier`): an anonymized identifier representing a user. This is persistent
    for subsequent requests from that user.
    - `conversation_id` (`Identifier`): an identifier representing a chat. This is
    persistent for subsequent request for that chat.
    - `message_id` (`Identifier`): an identifier representing a message.
    - `access_key` (`str = "<missing>"`): contains the access key defined when you created your bot
    on Poe.
    - `temperature` (`float | None = None`): Temperature input to be used for model inference.
    - `skip_system_prompt` (`bool = False`): Whether to use any system prompting or not.
    - `logit_bias` (`Dict[str, float] = {}`)
    - `stop_sequences` (`List[str] = []`)
    - `language_code` (`str = "en"`): BCP 47 language code of the user's client.
    - `bot_query_id` (`str = ""`): an identifier representing a bot query.

    """

    query: List[ProtocolMessage]
    user_id: Identifier
    conversation_id: Identifier
    message_id: Identifier
    metadata: Identifier = ""
    api_key: str = "<missing>"
    access_key: str = "<missing>"
    temperature: Optional[float] = None
    skip_system_prompt: bool = False
    logit_bias: Dict[str, float] = {}
    stop_sequences: List[str] = []
    language_code: str = "en"
    bot_query_id: Identifier = ""


class SettingsRequest(BaseRequest):
    """

    Request parameters for a settings request. Currently, this contains no fields but this
    might get updated in the future.

    """


class ReportFeedbackRequest(BaseRequest):
    """

    Request parameters for a report_feedback request.
    #### Fields:
    - `message_id` (`Identifier`)
    - `user_id` (`Identifier`)
    - `conversation_id` (`Identifier`)
    - `feedback_type` (`FeedbackType`)

    """

    message_id: Identifier
    user_id: Identifier
    conversation_id: Identifier
    feedback_type: FeedbackType


class ReportReactionRequest(BaseRequest):
    """

    Request parameters for a report_reaction request.
    #### Fields:
    - `message_id` (`Identifier`)
    - `user_id` (`Identifier`)
    - `conversation_id` (`Identifier`)
    - `reaction` (`str`)

    """

    message_id: Identifier
    user_id: Identifier
    conversation_id: Identifier
    reaction: str


class ReportErrorRequest(BaseRequest):
    """

    Request parameters for a report_error request.
    #### Fields:
    - `message` (`str`)
    - `metadata` (`Dict[str, Any]`)

    """

    message: str
    metadata: Dict[str, Any]


class SettingsResponse(BaseModel):
    """

    An object representing your bot's response to a settings object.
    #### Fields:
    - `server_bot_dependencies` (`Dict[str, int] = {}`): Information about other bots that your bot
    uses. This is used to facilitate the Bot Query API.
    - `allow_attachments` (`bool = False`): Whether to allow users to upload attachments to your
    bot.
    - `introduction_message` (`str = ""`): The introduction message to display to the users of your
    bot.
    - `expand_text_attachments` (`bool = True`): Whether to request parsed content/descriptions from
    text attachments with the query request. This content is sent through the new parsed_content
    field in the attachment dictionary. This change makes enabling file uploads much simpler.
    - `enable_image_comprehension` (`bool = False`): Similar to `expand_text_attachments` but for
    images.
    - `enforce_author_role_alternation` (`bool = False`): If enabled, Poe will concatenate messages
    so that they follow role alternation, which is a requirement for certain LLM providers like
    Anthropic.
     - `enable_multi_bot_chat_prompting` (`bool = False`): If enabled, Poe will combine previous bot
     messages if there is a multibot context.

    """

    model_config = ConfigDict(extra="forbid")

    context_clear_window_secs: Optional[int] = None  # deprecated
    allow_user_context_clear: Optional[bool] = None  # deprecated
    server_bot_dependencies: Dict[str, int] = Field(default_factory=dict)
    allow_attachments: Optional[bool] = None
    introduction_message: Optional[str] = None
    expand_text_attachments: Optional[bool] = None
    enable_image_comprehension: Optional[bool] = None
    enforce_author_role_alternation: Optional[bool] = None
    enable_multi_bot_chat_prompting: Optional[bool] = None
    custom_rate_card: Optional[str] = None


class AttachmentUploadResponse(BaseModel):
    inline_ref: Optional[str]
    attachment_url: Optional[str]


class PartialResponse(BaseModel):
    """

    Representation of a (possibly partial) response from a bot. Yield this in
    `PoeBot.get_response` or `PoeBot.get_response_with_context` to communicate your response to Poe.

    #### Fields:
    - `text` (`str`): The actual text you want to display to the user. Note that this should solely
    be the text in the next token since Poe will automatically concatenate all tokens before
    displaying the response to the user.
    - `data` (`Optional[Dict[str, Any]]`): Used to send arbitrary json data to Poe. This is
    currently only used for OpenAI function calling.
    - `is_suggested_reply` (`bool = False`): Setting this to true will create a suggested reply with
    the provided text value.
    - `is_replace_response` (`bool = False`): Setting this to true will clear out the previously
    displayed text to the user and replace it with the provided text value.

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

    #### Fields:
    - `allow_retry` (`bool = False`): Whether or not to allow a user to retry on error.
    - `error_type` (`Optional[ErrorType] = None`): An enum indicating what error to display.

    """

    allow_retry: bool = False
    error_type: Optional[ErrorType] = None


class MetaResponse(PartialResponse):
    """

    Similar to `Partial Response`. Yield this to communicate `meta` events from server bots.

    #### Fields:
    - `suggested_replies` (`bool = False`): Whether or not to enable suggested replies.
    - `content_type` (`ContentType = "text/markdown"`): Used to describe the format of the response.
    The currently supported values are `text/plain` and `text/markdown`.
    - `refetch_settings` (`bool = False`): Used to trigger a settings fetch request from Poe. A more
    robust way to trigger this is documented at:
    https://creator.poe.com/docs/server-bots-functional-guides#updating-bot-settings

    """

    linkify: bool = True  # deprecated
    suggested_replies: bool = True
    content_type: ContentType = "text/markdown"
    refetch_settings: bool = False


class ToolDefinition(BaseModel):
    """

    An object representing a tool definition used for OpenAI function calling.
    #### Fields:
    - `type` (`str`)
    - `function` (`FunctionDefinition`): Look at the source code for a detailed description
    of what this means.

    """

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
    """

    An object representing a tool call. This is returned as a response by the model when using
    OpenAI function calling.
    #### Fields:
    - `id` (`str`)
    - `type` (`str`)
    - `function` (`FunctionDefinition`): Look at the source code for a detailed description
    of what this means.

    """

    class FunctionDefinition(BaseModel):
        name: str
        arguments: str

    id: str
    type: str
    function: FunctionDefinition


class ToolResultDefinition(BaseModel):
    """

    An object representing a function result. This is passed to the model in the last step
    when using OpenAI function calling.
    #### Fields:
    - `role` (`str`)
    - `name` (`str`)
    - `tool_call_id` (`str`)
    - `content` (`str`)

    """

    role: str
    name: str
    tool_call_id: str
    content: str

import math
from typing import Any, Optional, Union

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import Literal, TypeAlias

Identifier: TypeAlias = str
FeedbackType: TypeAlias = Literal["like", "dislike"]
ContentType: TypeAlias = Literal["text/markdown", "text/plain"]
MessageType: TypeAlias = Literal["function_call"]
ErrorType: TypeAlias = Literal[
    "user_message_too_long",
    "insufficient_fund",
    "user_caused_error",
    "privacy_authorization_error",
]


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

    @field_validator("amount_usd_milli_cents", mode="before")
    def validate_amount_is_int(cls, v: Union[int, str, float]) -> int:
        if isinstance(v, float):
            return math.ceil(v)
        if not isinstance(v, int):
            raise ValueError(
                "Invalid amount: expected an integer for amount_usd_milli_cents, "
                f"got {type(v)}. Please provide the amount in milli-cents "
                "(1/1000 of a cent) as a whole number. If you're working with a "
                "decimal value, consider using math.ceil() to round up."
            )
        return v


class Attachment(BaseModel):
    """

    Attachment included in a protocol message.
    #### Fields:
    - `url` (`str`): The download URL of the attachment.
    - `content_type` (`str`): The MIME type of the attachment.
    - `name` (`str`): The name of the attachment.
    - `inline_ref` (`Optional[str] = None`): Set this to make Poe render the attachment inline.
        You can then reference the attachment inline using ![title][inline_ref].
    - `parsed_content` (`Optional[str] = None`): The parsed content of the attachment.

    """

    url: str
    content_type: str
    name: str
    inline_ref: Optional[str] = None
    parsed_content: Optional[str] = None


class ProtocolMessage(BaseModel):
    """

    A message as used in the Poe protocol.
    #### Fields:
    - `role` (`Literal["system", "user", "bot", "tool"]`)
    - `message_type` (`Optional[MessageType] = None`)
    - `sender_id` (`Optional[str]`)
    - `content` (`str`)
    - `parameters` (`dict[str, Any] = {}`)
    - `content_type` (`ContentType="text/markdown"`)
    - `timestamp` (`int = 0`)
    - `message_id` (`str = ""`)
    - `feedback` (`list[MessageFeedback] = []`)
    - `attachments` (`list[Attachment] = []`)
    - `metadata` (`Optional[str] = None`)

    """

    role: Literal["system", "user", "bot", "tool"]
    message_type: Optional[MessageType] = None
    sender_id: Optional[str] = None
    content: str
    parameters: dict[str, Any] = {}
    content_type: ContentType = "text/markdown"
    timestamp: int = 0
    message_id: str = ""
    feedback: list[MessageFeedback] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    metadata: Optional[str] = None


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
    - `query` (`list[ProtocolMessage]`): list of message representing the current state of the chat.
    - `user_id` (`Identifier`): an anonymized identifier representing a user. This is persistent
    for subsequent requests from that user.
    - `conversation_id` (`Identifier`): an identifier representing a chat. This is
    persistent for subsequent request for that chat.
    - `message_id` (`Identifier`): an identifier representing a message.
    - `access_key` (`str = "<missing>"`): contains the access key defined when you created your bot
    on Poe.
    - `temperature` (`float | None = None`): Temperature input to be used for model inference.
    - `skip_system_prompt` (`bool = False`): Whether to use any system prompting or not.
    - `logit_bias` (`dict[str, float] = {}`)
    - `stop_sequences` (`list[str] = []`)
    - `language_code` (`str = "en"`): BCP 47 language code of the user's client.
    - `bot_query_id` (`str = ""`): an identifier representing a bot query.

    """

    query: list[ProtocolMessage]
    user_id: Identifier
    conversation_id: Identifier
    message_id: Identifier
    metadata: Identifier = ""
    api_key: str = "<missing>"
    access_key: str = "<missing>"
    temperature: Optional[float] = None
    skip_system_prompt: bool = False
    logit_bias: dict[str, float] = {}
    stop_sequences: list[str] = []
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
    - `metadata` (`dict[str, Any]`)

    """

    message: str
    metadata: dict[str, Any]


Number = Union[int, float]


class Divider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["divider"] = "divider"


class TextField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["text_field"] = "text_field"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[str] = None
    placeholder: Optional[str] = None


class TextArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["text_area"] = "text_area"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[str] = None
    placeholder: Optional[str] = None


class ValueNamePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    name: str


class DropDown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["drop_down"] = "drop_down"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[str] = None
    options: list[ValueNamePair]


class ToggleSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["toggle_switch"] = "toggle_switch"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[bool] = None


class Slider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["slider"] = "slider"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[Number] = None
    min_value: Number
    max_value: Number
    step: Number


class AspectRatioOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None
    width: Number
    height: Number


class AspectRatio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["aspect_ratio"] = "aspect_ratio"
    label: str
    description: Optional[str] = None
    parameter_name: str
    default_value: Optional[str] = None
    options: list[AspectRatioOption]


BaseControl = Union[
    Divider, TextField, TextArea, DropDown, ToggleSwitch, Slider, AspectRatio
]


class LiteralValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    literal: Union[str, float, int, bool]


class ParameterValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter_name: str


class ComparatorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparator: Literal["eq", "ne", "gt", "ge", "lt", "le"]
    left: Union[LiteralValue, ParameterValue]
    right: Union[LiteralValue, ParameterValue]


class ConditionallyRenderControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: Literal["condition"] = "condition"
    condition: ComparatorCondition
    controls: list[BaseControl]


FullControls = Union[
    Divider,
    TextField,
    TextArea,
    DropDown,
    ToggleSwitch,
    Slider,
    AspectRatio,
    ConditionallyRenderControls,
]


class Tab(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    controls: list[FullControls]


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    controls: Optional[list[FullControls]] = None
    tabs: Optional[list[Tab]] = None
    collapsed_by_default: Optional[bool] = None


class ParameterControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: Literal["2"] = "2"
    sections: list[Section]


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
            properties: dict[str, object]
            required: Optional[list[str]] = None

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
    - `function` (`FunctionDefinition`): The function name (string) and arguments (JSON string).

    """

    class FunctionDefinition(BaseModel):
        name: str
        arguments: str

    id: str
    type: str
    function: FunctionDefinition


class ToolCallDefinitionDelta(BaseModel):
    """

    An object representing a tool call chunk. This is returned as a streamed response by the model
    when using OpenAI function calling. This may be an incomplete tool call definition (e.g. with
    the function name set with the arguments not yet filled in), so the index can be used to
    identify which tool call this chunk belongs to. Chunks may have null id, type, and
    function.name values.
    See https://platform.openai.com/docs/guides/function-calling#streaming for examples.
    #### Fields:
    - `index` (`int`): used to identify to which tool call this chunk belongs.
    - `id` (`Optional[str] = None`): The tool call ID. This helps the model identify previous tool
    call suggestions and help optimize tool call loops.
    - `type` (`Optional[str] = None`): The type of the tool call (always function for function
    calls).
    - `function` (`FunctionDefinitionDelta`): The function name (string) and arguments (JSON
    string).

    """

    class FunctionDefinitionDelta(BaseModel):
        name: Optional[str] = None
        arguments: str

    index: int = 0
    id: Optional[str] = None
    type: Optional[str] = None
    function: FunctionDefinitionDelta


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


class SettingsResponse(BaseModel):
    """

    An object representing your bot's response to a settings object.
    #### Fields:
    - `response_version` (`int = 2`): Different Poe Protocol versions use different default settings
    values. When provided, Poe will use the default values for the specified response version.
    If not provided, Poe will use the default values for response version 0.
    - `server_bot_dependencies` (`dict[str, int] = {}`): Information about other bots that your bot
    uses. This is used to facilitate the Bot Query API.
    - `allow_attachments` (`bool = True`): Whether to allow users to upload attachments to your
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
     - `enable_multi_bot_chat_prompting` (`bool = True`): If enabled, Poe will combine previous bot
     messages if there is a multibot context.
    - `parameter_controls` (`Optional[ParameterControls] = None`): Optional JSON object that defines
    interactive parameter controls. The object must contain an api_version and sections array.

    """

    model_config = ConfigDict(extra="forbid")

    response_version: Optional[int] = 2
    context_clear_window_secs: Optional[int] = None  # deprecated
    allow_user_context_clear: Optional[bool] = None  # deprecated
    custom_rate_card: Optional[str] = None  # deprecated
    server_bot_dependencies: dict[str, int] = Field(default_factory=dict)
    allow_attachments: Optional[bool] = None
    introduction_message: Optional[str] = None
    expand_text_attachments: Optional[bool] = None
    enable_image_comprehension: Optional[bool] = None
    enforce_author_role_alternation: Optional[bool] = None
    enable_multi_bot_chat_prompting: Optional[bool] = None
    rate_card: Optional[str] = None
    cost_label: Optional[str] = None
    parameter_controls: Optional[ParameterControls] = None


class AttachmentUploadResponse(BaseModel):
    """

    The result of a post_message_attachment request.
    #### Fields:
    - `attachment_url` (`Optional[str]`): The URL of the attachment.
    - `mime_type` (`Optional[str]`): The MIME type of the attachment.
    - `inline_ref` (`Optional[str]`): The inline reference of the attachment.
    if post_message_attachment is called with is_inline=False, this will be None.

    """

    attachment_url: Optional[str]
    mime_type: Optional[str]
    inline_ref: Optional[str]


class AttachmentHttpResponse(BaseModel):
    attachment_url: Optional[str]
    mime_type: Optional[str]


class DataResponse(BaseModel):
    """

    A response that contains arbitrary data to attach to the bot response.
    This data can be retrieved in later requests to the bot within the same chat.
    Note that only the final DataResponse object in the stream will be attached to the bot response.

    #### Fields:
    - `metadata` (`str`): String of data to attach to the bot response.

    """

    model_config = ConfigDict(extra="forbid")

    metadata: str


class PartialResponse(BaseModel):
    """

    Representation of a (possibly partial) response from a bot. Yield this in
    `PoeBot.get_response` or `PoeBot.get_response_with_context` to communicate your response to Poe.

    #### Fields:
    - `text` (`str`): The actual text you want to display to the user. Note that this should solely
    be the text in the next token since Poe will automatically concatenate all tokens before
    displaying the response to the user.
    - `data` (`Optional[dict[str, Any]]`): Used to send arbitrary json data to Poe. This is
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

    data: Optional[dict[str, Any]] = None
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

    attachment: Optional[Attachment] = None
    """If the bot returns an attachment, it will be contained here."""

    tool_calls: list[ToolCallDefinitionDelta] = Field(default_factory=list)
    """If the bot returns tool calls, it will be contained here."""

    index: Optional[int] = None
    """If a bot supports multiple responses, this is the index of the response to be updated."""


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
    https://creator.poe.com/docs/server-bots/updating-bot-settings

    """

    linkify: bool = True  # deprecated
    suggested_replies: bool = True
    content_type: ContentType = "text/markdown"
    refetch_settings: bool = False

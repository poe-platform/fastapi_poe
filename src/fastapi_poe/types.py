from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal, TypeAlias

Identifier: TypeAlias = str
FeedbackType: TypeAlias = Literal["like", "dislike"]
ContentType: TypeAlias = Literal["text/markdown", "text/plain"]


class MessageFeedback(BaseModel):
    """Feedback for a message as used in the Poe protocol."""

    type: FeedbackType
    reason: Optional[str]


class Attachment(BaseModel):
    url: str
    content_type: str
    name: str


class ProtocolMessage(BaseModel):
    """A message as used in the Poe protocol."""

    role: Literal["system", "user", "bot"]
    content: str
    content_type: ContentType = "text/markdown"
    timestamp: int = 0
    message_id: str = ""
    feedback: List[MessageFeedback] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)


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
    context_clear_window_secs: Optional[int] = None  # deprecated
    allow_user_context_clear: bool = True  # deprecated
    server_bot_dependencies: Dict[str, int] = Field(default_factory=dict)
    allow_attachments: bool = False
    introduction_message: str = ""

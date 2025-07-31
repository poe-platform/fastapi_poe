import json

import pydantic
import pytest
from fastapi_poe.types import (
    CostItem,
    PartialResponse,
    ProtocolMessage,
    SettingsResponse,
)


class TestSettingsResponse:

    def test_default_response_version(self) -> None:
        response = SettingsResponse()
        assert response.response_version == 2


def test_extra_attrs() -> None:
    with pytest.raises(pydantic.ValidationError):
        PartialResponse(text="hi", replaceResponse=True)  # type: ignore

    resp = PartialResponse(text="a capybara", is_replace_response=True)
    assert resp.is_replace_response is True
    assert resp.text == "a capybara"


def test_cost_item() -> None:
    with pytest.raises(pydantic.ValidationError):
        CostItem(amount_usd_milli_cents="1")  # type: ignore

    item = CostItem(amount_usd_milli_cents=25)
    assert item.amount_usd_milli_cents == 25
    assert item.description is None

    item = CostItem(amount_usd_milli_cents=25.5, description="Test")  # type: ignore
    assert item.amount_usd_milli_cents == 26
    assert item.description == "Test"


def test_protocol_message() -> None:
    # user message
    message = ProtocolMessage(role="user", content="Hello, world!")
    assert message.role == "user"
    assert message.message_type is None
    assert message.content == "Hello, world!"

    # bot message
    message = ProtocolMessage(role="bot", content="How can I help you?")
    assert message.role == "bot"
    assert message.message_type is None
    assert message.content == "How can I help you?"

    # tool calls message
    tool_calls_content = json.dumps(
        [
            {
                "id": "tool_call_id_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"location": "San Francisco, CA", "unit": "celsius"}',
                },
            },
            {
                "id": "tool_call_id_2",
                "type": "function",
                "function": {
                    "name": "send_email",
                    "arguments": '{"to": "bob@email.com", "body": "Hi bob"}',
                },
            },
        ]
    )
    message = ProtocolMessage(
        role="bot", message_type="function_call", content=tool_calls_content
    )
    assert message.role == "bot"
    assert message.message_type == "function_call"
    assert message.content == tool_calls_content

    # tool results message
    tool_results_content = json.dumps(
        [
            {
                "role": "tool",
                "name": "get_weather",
                "tool_call_id": "tool_call_id_1",
                "content": "15 degrees",
            },
            {
                "role": "tool",
                "name": "send_email",
                "tool_call_id": "tool_call_id_2",
                "content": "Email sent to bob@email.com",
            },
        ]
    )
    message = ProtocolMessage(role="tool", content=tool_results_content)
    assert message.role == "tool"
    assert message.message_type is None
    assert message.content == tool_results_content

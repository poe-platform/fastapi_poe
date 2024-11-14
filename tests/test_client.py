from typing import Any, AsyncGenerator, Optional, Union
import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi_poe.client import (
    _BotContext,
    BotMessage,
    MetaMessage,
    BotError,
    BotErrorNoRetry,
)
from fastapi_poe.types import QueryRequest


class MockSSEEvent:
    def __init__(self, event_type: str, data: Union[dict[str, Any], str]) -> None:
        self.event: str = event_type
        self.data: str = json.dumps(data) if isinstance(data, dict) else data


class MockEventSource:
    def __init__(self, events: list[MockSSEEvent]) -> None:
        self.events = events

    async def aiter_sse(self) -> AsyncGenerator[MockSSEEvent, None]:
        for event in self.events:
            yield event

    async def __aenter__(self) -> "MockEventSource":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class TestPerformQueryRequest:
    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def bot_context(self, mock_session: AsyncMock) -> _BotContext:
        return _BotContext(
            endpoint="https://test.com/bot", session=mock_session, api_key="test_key"
        )

    @pytest.fixture
    def base_request(self) -> QueryRequest:
        return QueryRequest(
            query=[],
            user_id="test_user",
            conversation_id="test_conv",
            message_id="test_message",
            version="1.0",
            type="query",
        )

    async def _run_query_request(
        self, events: list[MockSSEEvent], context: _BotContext, request: QueryRequest
    ) -> list[BotMessage]:
        """Helper method to run query request and collect messages"""
        messages: list[BotMessage] = []
        with patch("httpx_sse.aconnect_sse", return_value=MockEventSource(events)):
            async for msg in context.perform_query_request(
                request=request, tools=None, tool_calls=None, tool_results=None
            ):
                messages.append(msg)
        return messages

    @pytest.mark.asyncio
    async def test_text_event_with_extra_fields(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent("text", {"text": "Hello", "extra_field": "extra_value"}),
            MockSSEEvent("done", {}),
        ]

        messages = await self._run_query_request(events, bot_context, base_request)

        assert len(messages) == 1
        assert messages[0].text == "Hello"
        assert isinstance(messages[0].raw_response, dict)
        assert "text" in messages[0].raw_response
        assert (
            json.loads(messages[0].raw_response["text"]).get("extra_field")
            == "extra_value"
        )

    @pytest.mark.asyncio
    async def test_replace_response_event(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent("text", {"text": "First"}),
            MockSSEEvent("replace_response", {"text": "Replaced"}),
            MockSSEEvent("done", {}),
        ]

        messages = await self._run_query_request(events, bot_context, base_request)

        assert len(messages) == 2
        assert messages[1].is_replace_response == True
        assert messages[1].text == "Replaced"

    @pytest.mark.asyncio
    async def test_meta_event(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent(
                "meta",
                {
                    "linkify": True,
                    "suggested_replies": True,
                    "content_type": "text/markdown",
                },
            ),
            MockSSEEvent("done", {}),
        ]

        messages = await self._run_query_request(events, bot_context, base_request)

        assert len(messages) == 1
        assert isinstance(messages[0], MetaMessage)
        assert messages[0].linkify == True
        assert messages[0].suggested_replies == True
        assert messages[0].content_type == "text/markdown"

    @pytest.mark.asyncio
    async def test_error_event(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent("error", {"message": "Test error", "allow_retry": False}),
        ]
        with pytest.raises(BotErrorNoRetry):
            await self._run_query_request(events, bot_context, base_request)

    @pytest.mark.asyncio
    async def test_invalid_text_event(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent("text", {"text": None}),  # Invalid text field
        ]
        with pytest.raises(BotErrorNoRetry):
            await self._run_query_request(events, bot_context, base_request)

    @pytest.mark.asyncio
    async def test_suggested_reply_event(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent(
                "text",
                {"text": "Suggestion", "data": {"extra_field": "extra_value"}},
            ),
            MockSSEEvent("done", {}),
        ]

        messages = await self._run_query_request(events, bot_context, base_request)

        assert len(messages) == 1
        assert messages[0].is_suggested_reply == True
        assert messages[0].text == "Suggestion"

    async def test_multiple_text_events(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [
            MockSSEEvent(
                "text",
                {
                    "text": "First",
                    "extra_field": "extra_value",
                    "waiting_time_us": 1000,
                },
            ),
            MockSSEEvent(
                "text",
                {
                    "text": "Second",
                    "extra_field": "extra_value",
                    "waiting_time_us": 2000,
                },
            ),
            MockSSEEvent("done", {}),
        ]

        messages = await self._run_query_request(events, bot_context, base_request)

        # Check number of messages
        assert len(messages) == 2

        # Check first message
        assert messages[0].text == "First"
        assert isinstance(messages[0].raw_response, dict)
        assert "text" in messages[0].raw_response
        parsed_data = json.loads(messages[0].raw_response["text"])
        assert parsed_data.get("extra_field") == "extra_value"
        assert parsed_data.get("waiting_time_us") == 1000
        assert messages[0].is_replace_response == False
        assert messages[0].is_suggested_reply == False
        # Check second message
        assert messages[1].text == "Second"
        assert isinstance(messages[1].raw_response, dict)
        assert "text" in messages[1].raw_response
        parsed_data = json.loads(messages[1].raw_response["text"])
        assert parsed_data.get("extra_field") == "extra_value"
        assert parsed_data.get("waiting_time_us") == 2000
        assert messages[1].is_replace_response == False
        assert messages[1].is_suggested_reply == False

    @pytest.mark.asyncio
    async def test_unknown_event_type(
        self, bot_context: _BotContext, base_request: QueryRequest
    ) -> None:
        events = [MockSSEEvent("unknown", {"data": "test"}), MockSSEEvent("done", {})]

        messages = await self._run_query_request(events, bot_context, base_request)

        assert len(messages) == 0  # Unknown event should be ignored

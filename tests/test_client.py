import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Callable, cast
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi_poe.client import (
    AttachmentUploadError,
    BotError,
    BotErrorNoRetry,
    _BotContext,
    _safe_ellipsis,
    get_bot_response,
    get_bot_response_sync,
    get_final_response,
    stream_request,
    sync_bot_settings,
    upload_file,
)
from fastapi_poe.types import MetaResponse as MetaMessage
from fastapi_poe.types import PartialResponse as BotMessage
from fastapi_poe.types import (
    ProtocolMessage,
    QueryRequest,
    ToolCallDefinition,
    ToolDefinition,
    ToolResultDefinition,
)
from sse_starlette import ServerSentEvent


@pytest.fixture
def mock_request() -> QueryRequest:
    return QueryRequest(
        version="1.1",
        type="query",
        query=[ProtocolMessage(role="user", content="Hello, world!")],
        user_id="123",
        conversation_id="456",
        message_id="789",
    )


async def message_generator() -> AsyncGenerator[BotMessage, None]:
    return_messages = ["Hello,", " world", "!"]
    for message in return_messages:
        yield BotMessage(text=message)


@pytest_asyncio.fixture
async def mock_text_only_query_response() -> AsyncGenerator:
    yield message_generator()


@pytest.mark.asyncio
class TestStreamRequest:

    @pytest.fixture
    def tool_definitions_and_executables(
        self,
    ) -> tuple[list[ToolDefinition], list[Callable]]:
        def get_current_weather(location: str, unit: str = "fahrenheit") -> str:
            """Get the current weather in a given location"""
            if "tokyo" in location.lower():
                return json.dumps(
                    {"location": "Tokyo", "temperature": "11", "unit": unit}
                )
            elif "san francisco" in location.lower():
                return json.dumps(
                    {"location": "San Francisco", "temperature": "72", "unit": unit}
                )
            elif "paris" in location.lower():
                return json.dumps(
                    {"location": "Paris", "temperature": "22", "unit": unit}
                )
            else:
                return json.dumps({"location": location, "temperature": "unknown"})

        def get_current_mayor(location: str) -> str:
            """Get the current mayor of a given location."""
            if "tokyo" in location.lower():
                return json.dumps({"location": "Tokyo", "mayor": "Yuriko Koike"})
            elif "san francisco" in location.lower():
                return json.dumps(
                    {"location": "San Francisco", "mayor": "London Breed"}
                )
            elif "paris" in location.lower():
                return json.dumps({"location": "Paris", "mayor": "Anne Hidalgo"})
            else:
                return json.dumps({"location": location, "mayor": "unknown"})

        mock_tool_dict_list = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_mayor",
                    "description": "Get the current mayor of a given location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            }
                        },
                        "required": ["location"],
                    },
                },
            },
        ]

        tools = [ToolDefinition(**tool_dict) for tool_dict in mock_tool_dict_list]
        tool_executables = [get_current_weather, get_current_mayor]

        return tools, tool_executables

    def _create_mock_openai_response(self, delta: dict[str, Any]) -> dict[str, Any]:
        mock_tool_response_template = {
            "id": "chatcmpl-abcde",
            "object": "chat.completion.chunk",
            "created": 1738799163,
            "model": "gpt-3.5-turbo-0125",
            "service_tier": "default",
            "system_fingerprint": None,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": None,
                        "refusal": None,
                    },
                    "logprobs": None,
                    "finish_reason": None,
                }
            ],
            "usage": None,
        }

        mock_tool_response_template["choices"][0]["delta"] = delta
        return mock_tool_response_template

    async def mock_perform_query_request_for_tools(
        self,
    ) -> AsyncGenerator[BotMessage, None]:
        """Mock the OpenAI API response for tool calls."""

        mock_delta = [
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_current_weather", "arguments": ""},
                    }
                ]
            },
            {"tool_calls": [{"index": 0, "function": {"arguments": '{"'}}]},
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": 'location":"San Francisco, CA'},
                    }
                ]
            },
            {"tool_calls": [{"index": 0, "function": {"arguments": '"}'}}]},
            {
                "tool_calls": [
                    {
                        "index": 1,
                        "id": "call_456",
                        "type": "function",
                        "function": {"name": "get_current_mayor", "arguments": ""},
                    }
                ]
            },
            {"tool_calls": [{"index": 1, "function": {"arguments": '{"'}}]},
            {
                "tool_calls": [
                    {"index": 1, "function": {"arguments": 'location":"Tokyo, JP'}}
                ]
            },
            {"tool_calls": [{"index": 1, "function": {"arguments": '"}'}}]},
            {},
        ]
        mock_responses = [
            self._create_mock_openai_response(delta) for delta in mock_delta
        ]
        # last chunk has finish reason "tool_calls"
        mock_responses[-1]["choices"][0]["finish_reason"] = "tool_calls"

        return_values = [
            BotMessage(text="", data=response) for response in mock_responses
        ]

        for message in return_values:
            yield message

    async def mock_perform_query_request_with_no_tools_selected(
        self,
    ) -> AsyncGenerator[BotMessage, None]:
        """Mock the OpenAI API response for tool calls when no tools are selected."""

        mock_deltas = [
            {"content": "there were"},
            {"content": " no tool calls"},
            {"content": "!"},
            {},
        ]
        mock_responses = [
            self._create_mock_openai_response(delta) for delta in mock_deltas
        ]
        # last chunk has no choices array because it sends usage
        mock_responses[-1]["choices"] = []
        mock_responses[-1]["usage"] = {"completion_tokens": 1, "prompt_tokens": 1}
        return_values = [
            BotMessage(text="", data=response) for response in mock_responses
        ]
        for message in return_values:
            yield message

    @patch("fastapi_poe.client._BotContext.perform_query_request")
    async def test_stream_request_basic(
        self,
        mock_perform_query_request: Mock,
        mock_request: QueryRequest,
        mock_text_only_query_response: AsyncGenerator[BotMessage, None],
    ) -> None:
        mock_perform_query_request.return_value = mock_text_only_query_response
        concatenated_text = ""
        async for message in stream_request(mock_request, "test_bot"):
            concatenated_text += message.text
        assert concatenated_text == "Hello, world!"

    @patch("fastapi_poe.client._BotContext.perform_query_request")
    async def test_stream_request_with_tools(
        self,
        mock_perform_query_request_with_tools: Mock,
        mock_request: QueryRequest,
        tool_definitions_and_executables: tuple[list[ToolDefinition], list[Callable]],
        mock_text_only_query_response: AsyncGenerator[BotMessage, None],
    ) -> None:
        mock_perform_query_request_with_tools.side_effect = [
            self.mock_perform_query_request_for_tools(),
            mock_text_only_query_response,
        ]
        concatenated_text = ""
        tools, tool_executables = tool_definitions_and_executables
        async for message in stream_request(
            mock_request, "test_bot", tools=tools, tool_executables=tool_executables
        ):
            concatenated_text += message.text
        assert concatenated_text == "Hello, world!"

        expected_tool_calls = [
            ToolCallDefinition(
                id="call_123",
                type="function",
                function=ToolCallDefinition.FunctionDefinition(
                    name="get_current_weather",
                    arguments='{"location":"San Francisco, CA"}',
                ),
            ),
            ToolCallDefinition(
                id="call_456",
                type="function",
                function=ToolCallDefinition.FunctionDefinition(
                    name="get_current_mayor", arguments='{"location":"Tokyo, JP"}'
                ),
            ),
        ]
        expected_tool_results = [
            ToolResultDefinition(
                role="tool",
                name="get_current_weather",
                tool_call_id="call_123",
                content=json.dumps(
                    tool_executables[0]('{"location":"San Francisco, CA"}')
                ),
            ),
            ToolResultDefinition(
                role="tool",
                name="get_current_mayor",
                tool_call_id="call_456",
                content=json.dumps(tool_executables[1]('{"location":"Tokyo, JP"}')),
            ),
        ]
        # check that the tool calls and results are passed to the second perform_query_request
        assert {
            "tool_calls": expected_tool_calls,
            "tool_results": expected_tool_results,
        }.items() <= mock_perform_query_request_with_tools.call_args_list[
            1
        ].kwargs.items()

    @patch("fastapi_poe.client._BotContext.perform_query_request")
    async def test_stream_request_with_tools_when_no_tools_selected(
        self,
        mock_perform_query_request_with_tools: Mock,
        mock_request: QueryRequest,
        tool_definitions_and_executables: tuple[list[ToolDefinition], list[Callable]],
    ) -> None:
        """Test case where the model does not select any tools to call."""
        mock_perform_query_request_with_tools.side_effect = [
            self.mock_perform_query_request_with_no_tools_selected()
        ]
        concatenated_text = ""
        tools, tool_executables = tool_definitions_and_executables
        async for message in stream_request(
            mock_request, "test_bot", tools=tools, tool_executables=tool_executables
        ):
            concatenated_text += message.text
        assert concatenated_text == "there were no tool calls!"
        # we should not make a second request if no tools are selected
        assert mock_perform_query_request_with_tools.call_count == 1


@pytest.mark.asyncio
class Test_BotContext:

    @pytest.fixture
    def mock_bot_context(self) -> _BotContext:
        return _BotContext(
            endpoint="test_endpoint",
            session=AsyncMock(),
            api_key="test_api_key",
            on_error=Mock(),
        )

    def create_sse_mock(
        self, events: list[ServerSentEvent]
    ) -> Callable[..., AbstractAsyncContextManager[AsyncMock]]:
        async def mock_sse_connection(
            *args: Any, **kwargs: Any  # noqa: ANN401
        ) -> AsyncIterator[AsyncMock]:
            mock_source = AsyncMock()

            async def mock_aiter_sse() -> AsyncIterator[ServerSentEvent]:
                for event in events:
                    yield event

            mock_source.aiter_sse = mock_aiter_sse
            yield mock_source

        return asynccontextmanager(mock_sse_connection)

    async def test_perform_query_request_basic(
        self, mock_bot_context: _BotContext, mock_request: QueryRequest
    ) -> None:
        # basic text case
        events = [
            ServerSentEvent(event="text", data='{"text": "some"}'),
            ServerSentEvent(event="text", data='{"text": " response."}'),
            ServerSentEvent(event="done", data="{}"),
            ServerSentEvent(
                event="text", data='{"text": "blahblah"}'
            ),  # after done; ignored
        ]
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            concatenated_text = ""
            async for message in mock_bot_context.perform_query_request(
                request=mock_request, tools=None, tool_calls=None, tool_results=None
            ):
                concatenated_text += message.text
            assert concatenated_text == "some response."

        # other events
        events = [
            ServerSentEvent(
                event="meta",
                data=(
                    '{"suggested_replies": true, '
                    '"content_type": "text/markdown", '
                    '"linkify": true}'
                ),
            ),
            ServerSentEvent(event="text", data='{"text": "some"}'),
            ServerSentEvent(
                event="meta", data='{"suggested_replies": true}'
            ),  # non-first meta event ignored
            ServerSentEvent(event="replace_response", data='{"text": " response."}'),
            ServerSentEvent(
                event="suggested_reply", data='{"text": "what do you mean?"}'
            ),
            ServerSentEvent(event="json", data='{"fruit": "apple"}'),
            ServerSentEvent(event="ping", data="{}"),
            ServerSentEvent(event="done", data="{}"),
        ]
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            messages = []
            async for message in mock_bot_context.perform_query_request(
                request=mock_request, tools=None, tool_calls=None, tool_results=None
            ):
                messages.append(message)

            assert messages == [
                MetaMessage(
                    text="",
                    raw_response={
                        "suggested_replies": True,
                        "content_type": "text/markdown",
                        "linkify": True,
                    },
                    full_prompt=repr(mock_request),
                    linkify=True,
                    suggested_replies=True,
                    content_type="text/markdown",
                ),
                BotMessage(
                    text="some",
                    raw_response={"type": "text", "text": '{"text": "some"}'},
                    full_prompt=repr(mock_request),
                    is_replace_response=False,
                ),
                BotMessage(
                    text=" response.",
                    raw_response={
                        "type": "replace_response",
                        "text": '{"text": " response."}',
                    },
                    full_prompt=repr(mock_request),
                    is_replace_response=True,
                ),
                BotMessage(
                    text="what do you mean?",
                    raw_response={
                        "type": "suggested_reply",
                        "text": '{"text": "what do you mean?"}',
                    },
                    full_prompt=repr(mock_request),
                    is_suggested_reply=True,
                ),
                BotMessage(
                    text="", full_prompt=repr(mock_request), data={"fruit": "apple"}
                ),
            ]

        # no done event - should still work
        events = [
            ServerSentEvent(event="text", data='{"text": "some"}'),
            ServerSentEvent(event="text", data='{"text": " response."}'),
        ]
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            concatenated_text = ""
            async for message in mock_bot_context.perform_query_request(
                request=mock_request, tools=None, tool_calls=None, tool_results=None
            ):
                concatenated_text += message.text
            assert concatenated_text == "some response."

        # error with allow_retry=false
        events = [
            ServerSentEvent(event="text", data='{"text": "some"}'),
            ServerSentEvent(event="error", data='{"allow_retry": false}'),
        ]
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            with pytest.raises(BotErrorNoRetry):
                async for _ in mock_bot_context.perform_query_request(
                    request=mock_request, tools=None, tool_calls=None, tool_results=None
                ):
                    pass

        # error with allow_retry=true
        events = [
            ServerSentEvent(event="text", data='{"text": "some"}'),
            ServerSentEvent(event="error", data='{"allow_retry": true}'),
        ]
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            with pytest.raises(BotError):
                async for _ in mock_bot_context.perform_query_request(
                    request=mock_request, tools=None, tool_calls=None, tool_results=None
                ):
                    pass

    @pytest.mark.parametrize(
        "events",
        [
            [
                ServerSentEvent(
                    event="meta", data='{"suggested_replies": "true"}'
                ),  # not bool
                ServerSentEvent(event="done", data="{}"),
            ],
            [
                ServerSentEvent(event="meta", data='{"linkify": "banana"}'),  # not bool
                ServerSentEvent(event="done", data="{}"),
            ],
            [
                ServerSentEvent(event="meta", data='{"content_type": 123}'),  # not str
                ServerSentEvent(event="done", data="{}"),
            ],
            [ServerSentEvent(event="done", data="{}")],  # no text in response
            [
                ServerSentEvent(event="bad", data='{"text": "some"}'),  # unknown event
                ServerSentEvent(event="done", data="{}"),
            ],
            [
                ServerSentEvent(event="text", data='{"text": banana}'),  # improper json
                ServerSentEvent(event="done", data="{}"),
            ],
            [
                ServerSentEvent(event="text", data='{"text": 123}'),  # not str
                ServerSentEvent(event="done", data="{}"),
            ],
            [
                ServerSentEvent(event="meta", data="123"),  # not dict
                ServerSentEvent(event="done", data="{}"),
            ],
        ],
    )
    async def test_perform_query_request_with_error(
        self,
        mock_bot_context: _BotContext,
        mock_request: QueryRequest,
        events: list[ServerSentEvent],
    ) -> None:
        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(events)
            try:
                async for _ in mock_bot_context.perform_query_request(
                    request=mock_request, tools=None, tool_calls=None, tool_results=None
                ):
                    pass
                cast(Mock, mock_bot_context.on_error).assert_called_once()
            except Exception:
                pass


@pytest.mark.asyncio
@patch("fastapi_poe.client._BotContext.perform_query_request")
async def test_get_final_response(
    mock_perform_query_request: Mock,
    mock_request: QueryRequest,
    mock_text_only_query_response: AsyncGenerator[BotMessage, None],
) -> None:
    mock_perform_query_request.return_value = mock_text_only_query_response
    final_response = await get_final_response(mock_request, "test_bot")
    assert final_response == "Hello, world!"


@pytest.mark.asyncio
@patch("fastapi_poe.client._BotContext.perform_query_request")
async def test_get_bot_response(
    mock_perform_query_request: Mock,
    mock_text_only_query_response: AsyncGenerator[BotMessage, None],
) -> None:
    mock_perform_query_request.return_value = mock_text_only_query_response

    mock_protocol_messages = [ProtocolMessage(role="user", content="Hello, world!")]

    concatenated_text = ""
    async for message in get_bot_response(
        mock_protocol_messages,
        "test_bot",
        api_key="test_api_key",
        temperature=0.5,
        skip_system_prompt=True,
        logit_bias={},
        stop_sequences=["foo"],
    ):
        concatenated_text += message.text
    assert concatenated_text == "Hello, world!"


@patch("fastapi_poe.client._BotContext.perform_query_request")
def test_get_bot_response_sync(
    mock_perform_query_request: Mock,
    mock_text_only_query_response: AsyncGenerator[BotMessage, None],
) -> None:
    mock_perform_query_request.return_value = mock_text_only_query_response

    mock_protocol_messages = [ProtocolMessage(role="user", content="Hello, world!")]

    concatenated_text = ""
    for message in get_bot_response_sync(
        mock_protocol_messages,
        "test_bot",
        api_key="test_api_key",
        temperature=0.5,
        skip_system_prompt=True,
        logit_bias={},
        stop_sequences=["foo"],
    ):
        concatenated_text += message.text
    assert concatenated_text == "Hello, world!"


@pytest.mark.parametrize(
    "test_input, limit, expected",
    [
        ("hello world", 5, "he..."),
        ("test", 10, "test"),
        (123, 5, "123"),
        ([1, 2, 3], 7, "[1, ..."),
        (None, 6, "None"),
        ("", 5, ""),
    ],
)
def test__safe_ellipsis(test_input: object, limit: int, expected: str) -> None:
    result = _safe_ellipsis(test_input, limit)
    assert result == expected


@patch("httpx.post")
def test_sync_bot_settings(mock_httpx_post: Mock) -> None:
    mock_httpx_post.return_value = Mock(status_code=200, text="{}")
    sync_bot_settings("test_bot", access_key="test_access_key", settings={"foo": "bar"})
    mock_httpx_post.assert_called_once_with(
        "https://api.poe.com/bot/update_settings/test_bot/test_access_key/1.1",
        json={"foo": "bar"},
        headers={"Content-Type": "application/json"},
    )
    mock_httpx_post.reset_mock()

    sync_bot_settings("test_bot", access_key="test_access_key")
    mock_httpx_post.assert_called_once_with(
        "https://api.poe.com/bot/fetch_settings/test_bot/test_access_key/1.1",
        # TODO: pass headers?
        # headers={"Content-Type": "application/json"},
    )
    mock_httpx_post.reset_mock()

    mock_httpx_post.return_value = Mock(status_code=500, text="{}")
    with pytest.raises(BotError):
        sync_bot_settings("test_bot", access_key="test_access_key")

    mock_httpx_post.side_effect = httpx.ReadTimeout("timeout")
    with pytest.raises(BotError):
        sync_bot_settings("test_bot", access_key="test_access_key")


def _make_mock_async_client(
    fake_send: Callable[[httpx.Request], Awaitable[httpx.Response]]
) -> httpx.AsyncClient:
    """
    Builds an `httpx.AsyncClient` double whose `send` coroutine is supplied
    by the caller (`fake_send`).

    """
    client = AsyncMock(spec=httpx.AsyncClient)

    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    client.build_request = Mock(
        side_effect=lambda *args, **kwargs: httpx.Request(*args, **kwargs)
    )
    client.send = AsyncMock(side_effect=fake_send)

    return client


@pytest.mark.asyncio
async def test_upload_file_via_url() -> None:
    expected_json = {
        "attachment_url": "https://cdn.example.com/fake-id/file.txt",
        "mime_type": "text/plain",
    }

    async def fake_send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=json.dumps(expected_json).encode(),
            headers={"content-type": "application/json"},
        )

    mock_client = _make_mock_async_client(fake_send)
    with patch("httpx.AsyncClient", return_value=mock_client):
        attachment = await upload_file(
            file_url="https://example.com/file.txt",
            file_name="file.txt",
            api_key="secret-key",
        )

    # Attachment object
    assert attachment.url == expected_json["attachment_url"]
    assert attachment.content_type == expected_json["mime_type"]
    assert attachment.name == "file.txt"

    # HTTP request
    send_mock: AsyncMock = cast(AsyncMock, mock_client.send)  # satisfy pyright
    req: httpx.Request = send_mock.call_args.args[0]
    assert req.url.path.endswith("/file_upload_3RD_PARTY_POST")
    assert req.method == "POST"
    assert req.headers["Authorization"] == "secret-key"


@pytest.mark.asyncio
async def test_upload_file_raw_bytes() -> None:
    expected_json = {
        "attachment_url": "https://cdn.example.com/fake-id/hello.txt",
        "mime_type": "text/plain",
    }

    async def fake_send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=json.dumps(expected_json).encode(),
            headers={"content-type": "application/json"},
        )

    mock_client = _make_mock_async_client(fake_send)
    with patch("httpx.AsyncClient", return_value=mock_client):
        attachment = await upload_file(
            file=b"hello world", file_name="hello.txt", api_key="secret-key"
        )

    # Attachment object
    assert attachment.url == expected_json["attachment_url"]
    assert attachment.content_type == expected_json["mime_type"]
    assert attachment.name == "hello.txt"

    # HTTP request
    send_mock: AsyncMock = cast(AsyncMock, mock_client.send)  # satisfy pyright
    req: httpx.Request = send_mock.call_args.args[0]
    assert req.headers["Authorization"] == "secret-key"
    assert req.headers["Content-Type"].startswith("multipart/form-data")


@pytest.mark.asyncio
async def test_upload_file_error_raises() -> None:
    async def fake_send(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, content=b"internal error")

    with (
        patch("httpx.AsyncClient", return_value=_make_mock_async_client(fake_send)),
        pytest.raises(AttachmentUploadError),
    ):
        await upload_file(file_url="https://example.com/file.txt", api_key="secret-key")

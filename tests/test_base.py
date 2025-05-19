import json
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Callable, Union
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import Request
from fastapi_poe.base import CostRequestError, InsufficientFundError, PoeBot, make_app
from fastapi_poe.client import AttachmentUploadError
from fastapi_poe.templates import (
    IMAGE_VISION_ATTACHMENT_TEMPLATE,
    TEXT_ATTACHMENT_TEMPLATE,
    URL_ATTACHMENT_TEMPLATE,
)
from fastapi_poe.types import (
    Attachment,
    AttachmentUploadResponse,
    CostItem,
    DataResponse,
    ErrorResponse,
    MetaResponse,
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    RequestContext,
)
from sse_starlette import ServerSentEvent
from starlette.routing import Route


@pytest.fixture
def basic_bot() -> PoeBot:
    mock_bot = PoeBot(path="/bot/test_bot", bot_name="test_bot", access_key="123")

    async def get_response(
        request: QueryRequest,
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent, DataResponse]]:
        yield MetaResponse(
            text="",
            suggested_replies=True,
            content_type="text/markdown",
            refetch_settings=False,
        )
        yield PartialResponse(text="hello")
        yield PartialResponse(text="this is a suggested reply", is_suggested_reply=True)
        yield PartialResponse(
            text="this is a replace response", is_replace_response=True
        )
        yield DataResponse(metadata='{"foo": "bar"}')

    mock_bot.get_response = get_response
    return mock_bot


@pytest.fixture
def error_bot() -> PoeBot:
    mock_bot = PoeBot(path="/bot/error_bot", bot_name="error_bot", access_key="123")

    async def get_response(
        request: QueryRequest,
    ) -> AsyncIterable[Union[PartialResponse, ServerSentEvent, DataResponse]]:
        yield PartialResponse(text="hello")
        yield ErrorResponse(text="sample error", allow_retry=True)

    mock_bot.get_response = get_response
    return mock_bot


@pytest.fixture
def mock_request() -> QueryRequest:
    return QueryRequest(
        version="1.0",
        type="query",
        query=[ProtocolMessage(role="user", content="Hello, world!")],
        user_id="123",
        conversation_id="123",
        message_id="456",
        bot_query_id="123",
    )


@pytest.fixture
def mock_request_context() -> RequestContext:
    return RequestContext(http_request=Mock(spec=Request))


class TestPoeBot:

    @pytest.mark.asyncio
    async def test_handle_query_basic_bot(
        self,
        basic_bot: PoeBot,
        mock_request: QueryRequest,
        mock_request_context: RequestContext,
    ) -> None:
        expected_sse_events = [
            ServerSentEvent(
                event="meta",
                data=json.dumps(
                    {
                        "suggested_replies": True,
                        "content_type": "text/markdown",
                        "refetch_settings": False,
                        "linkify": True,
                    }
                ),
            ),
            ServerSentEvent(event="text", data=json.dumps({"text": "hello"})),
            ServerSentEvent(
                event="suggested_reply",
                data=json.dumps({"text": "this is a suggested reply"}),
            ),
            ServerSentEvent(
                event="replace_response",
                data=json.dumps({"text": "this is a replace response"}),
            ),
            ServerSentEvent(
                event="data", data=json.dumps({"metadata": '{"foo": "bar"}'})
            ),
            ServerSentEvent(event="done", data="{}"),
        ]
        actual_sse_events = [
            event
            async for event in basic_bot.handle_query(
                mock_request, mock_request_context
            )
        ]
        assert len(actual_sse_events) == len(expected_sse_events)

        for actual_event, expected_event in zip(actual_sse_events, expected_sse_events):
            assert actual_event.event == expected_event.event
            assert expected_event.data and actual_event.data
            assert json.loads(actual_event.data) == json.loads(expected_event.data)

    @pytest.mark.asyncio
    async def test_handle_query_error_bot(
        self,
        error_bot: PoeBot,
        mock_request: QueryRequest,
        mock_request_context: RequestContext,
    ) -> None:
        expected_sse_events_error = [
            ServerSentEvent(event="text", data=json.dumps({"text": "hello"})),
            ServerSentEvent(
                event="error",
                data=json.dumps({"text": "sample error", "allow_retry": True}),
            ),
            ServerSentEvent(event="done", data="{}"),
        ]
        actual_sse_events = [
            event
            async for event in error_bot.handle_query(
                mock_request, mock_request_context
            )
        ]
        assert len(actual_sse_events) == len(expected_sse_events_error)

        for actual_event, expected_event in zip(
            actual_sse_events, expected_sse_events_error
        ):
            assert actual_event.event == expected_event.event
            assert expected_event.data and actual_event.data
            assert json.loads(actual_event.data) == json.loads(expected_event.data)

    def test_insert_attachment_messages(self, basic_bot: PoeBot) -> None:
        # Create mock attachments
        mock_text_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            name="test.txt",
            content_type="text/plain",
            parsed_content="Hello, world!",
        )
        mock_image_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/image/test.png",
            name="test.png",
            content_type="image/png",
            parsed_content="test.png***Hello, world!",
        )
        mock_image_attachment_2 = Attachment(
            url="https://pfst.cf2.poecdn.net/base/image/test.png",
            name="testimage2.jpg",
            content_type="image/jpeg",
            parsed_content="Hello, world!",
        )
        mock_pdf_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/application/test.pdf",
            name="test.pdf",
            content_type="application/pdf",
            parsed_content="Hello, world!",
        )
        mock_html_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/text/test.html",
            name="test.html",
            content_type="text/html",
            parsed_content="Hello, world!",
        )
        mock_video_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/video/test.mp4",
            name="test.mp4",
            content_type="video/mp4",
            parsed_content="Hello, world!",
        )
        # Create mock protocol messages
        message_without_attachments = ProtocolMessage(
            role="user", content="Hello, world!"
        )
        message_with_attachments = ProtocolMessage(
            role="user",
            content="Here's some attachments",
            attachments=[
                mock_text_attachment,
                mock_image_attachment,
                mock_image_attachment_2,
                mock_pdf_attachment,
                mock_html_attachment,
                mock_video_attachment,
            ],
        )
        # Create mock query request
        mock_query_request = QueryRequest(
            version="1.0",
            type="query",
            query=[message_without_attachments, message_with_attachments],
            user_id="123",
            conversation_id="123",
            message_id="456",
        )

        assert (
            mock_image_attachment.parsed_content
        )  # satisfy pyright so split() works below
        expected_protocol_messages = [
            message_without_attachments,
            ProtocolMessage(
                role="user",
                content=TEXT_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_text_attachment.name,
                    attachment_parsed_content=mock_text_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=TEXT_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_pdf_attachment.name,
                    attachment_parsed_content=mock_pdf_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=URL_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_html_attachment.name,
                    content=mock_html_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                    filename=mock_image_attachment.parsed_content.split("***")[0],
                    parsed_image_description=mock_image_attachment.parsed_content.split(
                        "***"
                    )[1],
                ),
            ),
            ProtocolMessage(
                role="user",
                content=IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                    filename=mock_image_attachment_2.name,
                    parsed_image_description=mock_image_attachment_2.parsed_content,
                ),
            ),
            message_with_attachments,
        ]

        modified_query_request = basic_bot.insert_attachment_messages(
            mock_query_request
        )
        protocol_messages = modified_query_request.query

        assert protocol_messages == expected_protocol_messages

    def test_make_prompt_author_role_alternated(self, basic_bot: PoeBot) -> None:
        mock_protocol_messages = [
            ProtocolMessage(
                role="user",
                content="Hello, world!",
                attachments=[
                    Attachment(
                        url="https://pfst.cf2.poecdn.net/base/text/test.txt",
                        name="test.txt",
                        content_type="text/plain",
                        parsed_content="Hello, world!",
                    )
                ],
            ),
            ProtocolMessage(
                role="user",
                content="Hello, world!",
                attachments=[
                    Attachment(
                        url="https://pfst.cf2.poecdn.net/base/text/test2.txt",
                        name="test2.txt",
                        content_type="text/plain",
                        parsed_content="Bye!",
                    )
                ],
            ),
            ProtocolMessage(role="bot", content="Hello, world!"),
        ]
        expected_protocol_messages = [
            ProtocolMessage(
                role="user",
                content="Hello, world!\n\nHello, world!",
                attachments=[
                    Attachment(
                        url="https://pfst.cf2.poecdn.net/base/text/test2.txt",
                        name="test2.txt",
                        content_type="text/plain",
                        parsed_content="Bye!",
                    ),
                    Attachment(
                        url="https://pfst.cf2.poecdn.net/base/text/test.txt",
                        name="test.txt",
                        content_type="text/plain",
                        parsed_content="Hello, world!",
                    ),
                ],
            ),
            ProtocolMessage(role="bot", content="Hello, world!"),
        ]
        assert (
            basic_bot.make_prompt_author_role_alternated(mock_protocol_messages)
            == expected_protocol_messages
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.send")
    async def test_post_message_attachment_basic(
        self, mock_send: Mock, basic_bot: PoeBot
    ) -> None:
        mock_send.return_value = httpx.Response(
            200,
            json={
                "attachment_url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "mime_type": "text/plain",
            },
        )

        result = await basic_bot.post_message_attachment(
            message_id="123",
            download_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            download_filename="test.txt",
        )

        assert result == AttachmentUploadResponse(
            inline_ref=None,
            attachment_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            mime_type="text/plain",
        )
        file_events_to_yield = basic_bot._file_events_to_yield.get("123", [])
        assert len(file_events_to_yield) == 1
        assert file_events_to_yield.pop().data == json.dumps(
            {
                "url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "content_type": "text/plain",
                "name": "test.txt",
                "inline_ref": None,
            }
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.send")
    async def test_post_message_attachment_download_url(
        self, mock_send: Mock, basic_bot: PoeBot
    ) -> None:
        mock_send.return_value = httpx.Response(
            200,
            json={
                "attachment_url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "mime_type": "text/plain",
            },
        )

        result = await basic_bot.post_message_attachment(
            message_id="123",
            download_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
        )

        assert result == AttachmentUploadResponse(
            inline_ref=None,
            attachment_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            mime_type="text/plain",
        )
        file_events_to_yield = basic_bot._file_events_to_yield.get("123", [])
        assert len(file_events_to_yield) == 1
        assert file_events_to_yield.pop().data == json.dumps(
            {
                "url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "content_type": "text/plain",
                "name": "test.txt",  # extracted from url
                "inline_ref": None,
            }
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.send")
    @patch("fastapi_poe.base.generate_inline_ref")
    async def test_post_message_attachment_inline(
        self, mock_generate_inline_ref: Mock, mock_send: Mock, basic_bot: PoeBot
    ) -> None:
        mock_send.return_value = httpx.Response(
            200,
            json={
                "attachment_url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "mime_type": "text/plain",
            },
        )
        mock_generate_inline_ref.return_value = "ab32ef21"

        result = await basic_bot.post_message_attachment(
            message_id="123",
            download_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            download_filename="test.txt",
            is_inline=True,
        )

        assert result == AttachmentUploadResponse(
            inline_ref="ab32ef21",
            attachment_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            mime_type="text/plain",
        )

        # Add a second attachment
        mock_send.return_value = httpx.Response(
            200,
            json={
                "attachment_url": "https://pfst.cf2.poecdn.net/base/image/test.png",
                "mime_type": "image/png",
            },
        )

        result = await basic_bot.post_message_attachment(
            message_id="123",
            download_url="https://pfst.cf2.poecdn.net/base/image/test.png",
            download_filename="test.png",
            is_inline=False,
        )

        assert result == AttachmentUploadResponse(
            inline_ref=None,
            attachment_url="https://pfst.cf2.poecdn.net/base/image/test.png",
            mime_type="image/png",
        )
        # Check that the file events are added to the instance dictionary
        file_events_to_yield = basic_bot._file_events_to_yield.get("123", [])
        assert len(file_events_to_yield) == 2
        expected_items = [
            {
                "url": "https://pfst.cf2.poecdn.net/base/text/test.txt",
                "content_type": "text/plain",
                "name": "test.txt",
                "inline_ref": "ab32ef21",
            },
            {
                "url": "https://pfst.cf2.poecdn.net/base/image/test.png",
                "content_type": "image/png",
                "name": "test.png",
                "inline_ref": None,
            },
        ]
        expected_items_json = {json.dumps(item) for item in expected_items}
        actual_items_json = {file_event.data for file_event in file_events_to_yield}
        assert expected_items_json == actual_items_json

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.send")
    async def test_post_message_attachment_error(
        self, mock_send: Mock, basic_bot: PoeBot
    ) -> None:
        mock_send.return_value = httpx.Response(400, json={"error": "test"})
        with pytest.raises(AttachmentUploadError):
            await basic_bot.post_message_attachment(
                message_id="123",
                download_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
                download_filename="test.txt",
            )

        with pytest.raises(ValueError):
            await basic_bot.post_message_attachment(
                message_id="123",
                download_url="https://pfst.cf2.poecdn.net/base/text/test.txt",
                download_filename="test.txt",
                file_data=b"test",
                filename="test.txt",
            )

    def create_sse_mock(
        self,
        events: list[ServerSentEvent],
        status_code: int = 200,
        reason_phrase: str = "OK",
    ) -> Callable[..., AbstractAsyncContextManager[AsyncMock]]:
        @asynccontextmanager
        async def mock_sse_connection(
            *args: Any, **kwargs: Any  # noqa: ANN401
        ) -> AsyncIterator[AsyncMock]:
            mock_source = AsyncMock()
            mock_source.response.status_code = status_code
            mock_source.response.reason_phrase = reason_phrase

            async def mock_aiter_sse() -> AsyncIterator[ServerSentEvent]:
                for event in events:
                    yield event

            mock_source.aiter_sse = mock_aiter_sse
            yield mock_source

        return mock_sse_connection

    @pytest.mark.asyncio
    async def test_authorize_cost_success(
        self, basic_bot: PoeBot, mock_request: QueryRequest
    ) -> None:
        cost_item = CostItem(amount_usd_milli_cents=1000)
        url = "https://example.com"

        events = [ServerSentEvent(event="result", data='{"status": "success"}')]

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=200, reason_phrase="OK"
            )
            await basic_bot.authorize_cost(
                request=mock_request, amounts=cost_item, base_url=url
            )

            mock_connect_sse.assert_called_once()
            call_args = mock_connect_sse.call_args
            assert (
                call_args.kwargs["url"]
                == f"{url}bot/cost/{mock_request.bot_query_id}/authorize"
            )
            assert call_args.kwargs["json"]["amounts"] == [cost_item.model_dump()]
            assert call_args.kwargs["json"]["access_key"] == basic_bot.access_key

    @pytest.mark.asyncio
    async def test_authorize_cost_failure(
        self, basic_bot: PoeBot, mock_request: QueryRequest
    ) -> None:
        cost_item = CostItem(amount_usd_milli_cents=1000)
        url = "https://example.com"

        events = [
            ServerSentEvent(event="result", data='{"status": "insufficient funds"}')
        ]

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=400, reason_phrase="Bad Request"
            )
            with pytest.raises(CostRequestError):
                await basic_bot.authorize_cost(
                    request=mock_request, amounts=cost_item, base_url=url
                )

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=200, reason_phrase="OK"
            )
            with pytest.raises(InsufficientFundError):
                await basic_bot.authorize_cost(
                    request=mock_request, amounts=cost_item, base_url=url
                )

    @pytest.mark.asyncio
    async def test_capture_cost_success(
        self, basic_bot: PoeBot, mock_request: QueryRequest
    ) -> None:
        cost_item = CostItem(amount_usd_milli_cents=1000)
        url = "https://example.com"

        events = [ServerSentEvent(event="result", data='{"status": "success"}')]

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=200, reason_phrase="OK"
            )
            await basic_bot.capture_cost(
                request=mock_request, amounts=cost_item, base_url=url
            )

            mock_connect_sse.assert_called_once()
            call_args = mock_connect_sse.call_args
            assert (
                call_args.kwargs["url"]
                == f"{url}bot/cost/{mock_request.bot_query_id}/capture"
            )
            assert call_args.kwargs["json"]["amounts"] == [cost_item.model_dump()]
            assert call_args.kwargs["json"]["access_key"] == basic_bot.access_key

    @pytest.mark.asyncio
    async def test_capture_cost_failure(
        self, basic_bot: PoeBot, mock_request: QueryRequest
    ) -> None:
        cost_item = CostItem(amount_usd_milli_cents=1000)
        url = "https://example.com"

        events = [
            ServerSentEvent(event="result", data='{"status": "insufficient funds"}')
        ]

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=400, reason_phrase="Bad Request"
            )
            with pytest.raises(CostRequestError):
                await basic_bot.capture_cost(
                    request=mock_request, amounts=cost_item, base_url=url
                )

        with patch("httpx_sse.aconnect_sse") as mock_connect_sse:
            mock_connect_sse.side_effect = self.create_sse_mock(
                events, status_code=200, reason_phrase="OK"
            )
            with pytest.raises(InsufficientFundError):
                await basic_bot.capture_cost(
                    request=mock_request, amounts=cost_item, base_url=url
                )


def test_make_app(basic_bot: PoeBot, error_bot: PoeBot) -> None:
    app = make_app([basic_bot, error_bot])
    assert app is not None
    assert app.router is not None

    expected_routes = [
        {"path": "/bot/error_bot", "name": "poe_post", "methods": {"POST"}},
        {"path": "/bot/test_bot", "name": "poe_post", "methods": {"POST"}},
    ]

    routes = [route for route in app.router.routes if isinstance(route, Route)]

    for expected in expected_routes:
        route_exists = any(
            route.path == expected["path"]
            and route.name == expected["name"]
            and route.methods == expected["methods"]
            for route in routes
        )

        assert route_exists, f"Route not found: {expected}"

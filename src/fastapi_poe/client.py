"""

Client for talking to other Poe bots through the Poe bot query API.
For more details, see: https://creator.poe.com/docs/server-bots-functional-guides#accessing-other-bots-on-poe

"""

import asyncio
import contextlib
import inspect
import io
import json
import os
import warnings
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Callable, Optional, Union, cast

import httpx
import httpx_sse

from fastapi_poe.sync_utils import run_sync

from .types import (
    Attachment,
    ContentType,
    FunctionCallDefinition,
    Identifier,
    ProtocolMessage,
    QueryRequest,
    SettingsResponse,
    ToolCallDefinition,
    ToolCallDefinitionDelta,
    ToolDefinition,
    ToolResultDefinition,
)
from .types import MetaResponse as MetaMessage
from .types import PartialResponse as BotMessage

PROTOCOL_VERSION = "1.2"
MESSAGE_LENGTH_LIMIT = 10_000

IDENTIFIER_LENGTH = 32
MAX_EVENT_COUNT = 1000

ErrorHandler = Callable[[Exception, str], None]


class AttachmentUploadError(Exception):
    """Raised when there is an error uploading an attachment."""


class BotError(Exception):
    """Raised when there is an error communicating with the bot."""


class BotErrorNoRetry(BotError):
    """Subclass of BotError raised when we're not allowed to retry."""


class InvalidBotSettings(Exception):
    """Raised when a bot returns invalid settings."""


def _safe_ellipsis(obj: object, limit: int) -> str:
    if not isinstance(obj, str):
        obj = repr(obj)
    if len(obj) > limit:
        obj = obj[: limit - 3] + "..."
    return obj


@dataclass
class _BotContext:
    endpoint: str
    session: httpx.AsyncClient = field(repr=False)
    api_key: Optional[str] = field(default=None, repr=False)
    on_error: Optional[ErrorHandler] = field(default=None, repr=False)
    extra_headers: Optional[dict[str, str]] = field(default=None, repr=False)

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.extra_headers is not None:
            headers.update(self.extra_headers)
        return headers

    async def report_error(
        self, message: str, metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """Report an error to the bot server."""
        if self.on_error is not None:
            long_message = (
                f"Protocol bot error: {message} with metadata {metadata} "
                f"for endpoint {self.endpoint}"
            )
            self.on_error(BotError(message), long_message)
        await self.session.post(
            self.endpoint,
            headers=self.headers,
            json={
                "version": PROTOCOL_VERSION,
                "type": "report_error",
                "message": message,
                "metadata": metadata or {},
            },
        )

    async def report_feedback(
        self,
        message_id: Identifier,
        user_id: Identifier,
        conversation_id: Identifier,
        feedback_type: str,
    ) -> None:
        """Report message feedback to the bot server."""
        await self.session.post(
            self.endpoint,
            headers=self.headers,
            json={
                "version": PROTOCOL_VERSION,
                "type": "report_feedback",
                "message_id": message_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "feedback_type": feedback_type,
            },
        )

    async def report_reaction(
        self,
        message_id: Identifier,
        user_id: Identifier,
        conversation_id: Identifier,
        reaction: str,
    ) -> None:
        """Report message reaction to the bot server."""
        await self.session.post(
            self.endpoint,
            headers=self.headers,
            json={
                "version": PROTOCOL_VERSION,
                "type": "report_reaction",
                "message_id": message_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "reaction": reaction,
            },
        )

    async def fetch_settings(self) -> SettingsResponse:
        """Fetches settings from a Poe server bot endpoint."""
        resp = await self.session.post(
            self.endpoint,
            headers=self.headers,
            json={"version": PROTOCOL_VERSION, "type": "settings"},
        )
        return resp.json()

    async def perform_query_request(
        self,
        *,
        request: QueryRequest,
        tools: Optional[list[ToolDefinition]],
        tool_calls: Optional[list[ToolCallDefinition]],
        tool_results: Optional[list[ToolResultDefinition]],
    ) -> AsyncGenerator[BotMessage, None]:
        chunks: list[str] = []
        message_id = request.message_id
        event_count = 0
        error_reported = False
        payload = request.model_dump()
        if tools is not None:
            payload["tools"] = [tool.model_dump() for tool in tools]
        if tool_calls is not None:
            payload["tool_calls"] = [tool_call.model_dump() for tool_call in tool_calls]
        if tool_results is not None:
            payload["tool_results"] = [
                tool_result.model_dump() for tool_result in tool_results
            ]
        async with httpx_sse.aconnect_sse(
            self.session, "POST", self.endpoint, headers=self.headers, json=payload
        ) as event_source:
            async for event in event_source.aiter_sse():
                event_count += 1
                index: Optional[int] = await self._get_single_json_integer_field_safe(
                    event.data, event.event, message_id, "index"
                )
                if event.event == "done":
                    # Don't send a report if we already told the bot about some other mistake.
                    if not chunks and not error_reported and not tools:
                        await self.report_error(
                            "Bot returned no text in response",
                            {"message_id": message_id},
                        )
                    return
                elif event.event == "text":
                    text = await self._get_single_json_field(
                        event.data, "text", message_id
                    )
                elif event.event == "replace_response":
                    text = await self._get_single_json_field(
                        event.data, "replace_response", message_id
                    )
                    chunks.clear()
                elif event.event == "file":
                    yield BotMessage(
                        text="",
                        attachment=Attachment(
                            url=await self._get_single_json_field(
                                event.data, "file", message_id, "url"
                            ),
                            content_type=await self._get_single_json_field(
                                event.data, "file", message_id, "content_type"
                            ),
                            name=await self._get_single_json_field(
                                event.data, "file", message_id, "name"
                            ),
                            inline_ref=await self._get_single_json_string_field_safe(
                                event.data, "file", message_id, "inline_ref"
                            ),
                        ),
                        index=index,
                    )
                    continue
                elif event.event == "suggested_reply":
                    text = await self._get_single_json_field(
                        event.data, "suggested_reply", message_id
                    )
                    yield BotMessage(
                        text=text,
                        raw_response={"type": event.event, "text": event.data},
                        full_prompt=repr(request),
                        is_suggested_reply=True,
                        index=index,
                    )
                    continue
                elif event.event == "json":
                    yield BotMessage(
                        text="",
                        data=json.loads(event.data),
                        full_prompt=repr(request),
                        index=index,
                    )
                    continue
                elif event.event == "meta":
                    if event_count != 1:
                        # spec says a meta event that is not the first event is ignored
                        continue
                    data = await self._load_json_dict(event.data, "meta", message_id)
                    linkify = data.get("linkify", False)
                    if not isinstance(linkify, bool):
                        await self.report_error(
                            "Invalid linkify value in 'meta' event",
                            {"message_id": message_id, "linkify": linkify},
                        )
                        error_reported = True
                        continue
                    send_suggested_replies = data.get("suggested_replies", False)
                    if not isinstance(send_suggested_replies, bool):
                        await self.report_error(
                            "Invalid suggested_replies value in 'meta' event",
                            {
                                "message_id": message_id,
                                "suggested_replies": send_suggested_replies,
                            },
                        )
                        error_reported = True
                        continue
                    content_type = data.get("content_type", "text/markdown")
                    if not isinstance(content_type, str):
                        await self.report_error(
                            "Invalid content_type value in 'meta' event",
                            {"message_id": message_id, "content_type": content_type},
                        )
                        error_reported = True
                        continue
                    yield MetaMessage(
                        text="",
                        raw_response=data,
                        full_prompt=repr(request),
                        linkify=linkify,
                        suggested_replies=send_suggested_replies,
                        content_type=cast(ContentType, content_type),
                    )
                    continue
                elif event.event == "error":
                    data = await self._load_json_dict(event.data, "error", message_id)
                    if data.get("allow_retry", True):
                        raise BotError(event.data)
                    else:
                        raise BotErrorNoRetry(event.data)
                elif event.event == "ping":
                    # Not formally part of the spec, but FastAPI sends this; let's ignore it
                    # instead of sending error reports.
                    continue
                else:
                    # Truncate the type and message in case it's huge.
                    await self.report_error(
                        f"Unknown event type: {_safe_ellipsis(event.event, 100)}",
                        {
                            "event_data": _safe_ellipsis(event.data, 500),
                            "message_id": message_id,
                        },
                    )
                    error_reported = True
                    continue
                chunks.append(text)
                yield BotMessage(
                    text=text,
                    raw_response={"type": event.event, "text": event.data},
                    full_prompt=repr(request),
                    is_replace_response=(event.event == "replace_response"),
                    index=index,
                )
        await self.report_error(
            "Bot exited without sending 'done' event", {"message_id": message_id}
        )

    async def _get_single_json_field(
        self, data: str, context: str, message_id: Identifier, field: str = "text"
    ) -> str:
        data_dict = await self._load_json_dict(data, context, message_id)
        text = data_dict[field]
        if not isinstance(text, str):
            await self.report_error(
                f"Expected string in '{field}' field for '{context}' event",
                {"data": data_dict, "message_id": message_id},
            )
            raise BotErrorNoRetry(f"Expected string in '{context}' event")
        return text

    async def _get_single_json_string_field_safe(
        self, data: str, context: str, message_id: Identifier, field: str
    ) -> Optional[str]:
        data_dict = await self._load_json_dict(data, context, message_id)
        if field not in data_dict:
            return None
        result = data_dict[field]
        if not isinstance(result, str):
            return None
        return result

    async def _get_single_json_integer_field_safe(
        self, data: str, context: str, message_id: Identifier, field: str
    ) -> Optional[int]:
        data_dict = await self._load_json_dict(data, context, message_id)
        if field not in data_dict:
            return None
        result = data_dict[field]
        if not isinstance(result, int):
            return None
        return result

    async def _load_json_dict(
        self, data: str, context: str, message_id: Identifier
    ) -> dict[str, object]:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            await self.report_error(
                f"Invalid JSON in {context!r} event",
                {"data": data, "message_id": message_id},
            )
            # If they are returning invalid JSON, retrying immediately probably won't help
            raise BotErrorNoRetry(f"Invalid JSON in {context!r} event") from None
        if not isinstance(parsed, dict):
            await self.report_error(
                f"Expected JSON dict in {context!r} event",
                {"data": data, "message_id": message_id},
            )
            raise BotError(f"Expected JSON dict in {context!r} event")
        return cast(dict[str, object], parsed)


def _default_error_handler(e: Exception, msg: str) -> None:
    print("Error in Poe bot:", msg, "\n", repr(e))


async def stream_request(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: Optional[list[ToolDefinition]] = None,
    tool_executables: Optional[list[Callable]] = None,
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
    extra_headers: Optional[dict[str, str]] = None,
) -> AsyncGenerator[BotMessage, None]:
    """

    The Entry point for the Bot Query API. This API allows you to use other bots on Poe for
    inference in response to a user message. For more details, checkout:
    https://creator.poe.com/docs/server-bots-functional-guides#accessing-other-bots-on-poe

    #### Parameters:
    - `request` (`QueryRequest`): A QueryRequest object representing a query from Poe. This object
    also includes information needed to identify the user for compute point usage.
    - `bot_name` (`str`): The bot you want to invoke.
    - `api_key` (`str = ""`): Your Poe API key, available at poe.com/api_key. You will need
    this in case you are trying to use this function from a script/shell. Note that if an `api_key`
    is provided, compute points will be charged on the account corresponding to the `api_key`.
    - tools: (`Optional[list[ToolDefinition]] = None`): A list of ToolDefinition objects describing
    the functions you have. This is used for OpenAI function calling.
    - tool_executables: (`Optional[list[Callable]] = None`): A list of functions corresponding
    to the ToolDefinitions. This is used for OpenAI function calling. When this is set, the
    LLM-suggested tools will automatically run once, before passing the results back to the LLM for
    a final response.

    """
    if tools is not None:
        async for message in _stream_request_with_tools(
            request=request,
            bot_name=bot_name,
            api_key=api_key,
            tools=tools,
            tool_executables=tool_executables,
            access_key=access_key,
            access_key_deprecation_warning_stacklevel=access_key_deprecation_warning_stacklevel,
            session=session,
            on_error=on_error,
            num_tries=num_tries,
            retry_sleep_time=retry_sleep_time,
            base_url=base_url,
            extra_headers=extra_headers,
        ):
            yield message

    else:
        async for message in stream_request_base(
            request=request,
            bot_name=bot_name,
            api_key=api_key,
            access_key=access_key,
            access_key_deprecation_warning_stacklevel=access_key_deprecation_warning_stacklevel,
            session=session,
            on_error=on_error,
            num_tries=num_tries,
            retry_sleep_time=retry_sleep_time,
            base_url=base_url,
            extra_headers=extra_headers,
        ):
            yield message


async def _get_tool_results(
    tool_executables: list[Callable], tool_calls: list[ToolCallDefinition]
) -> list[ToolResultDefinition]:
    tool_executables_dict = {
        executable.__name__: executable for executable in tool_executables
    }
    tool_results = []
    for tool_call in tool_calls:
        tool_call_id = tool_call.id
        name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        _func = tool_executables_dict[name]
        if inspect.iscoroutinefunction(_func):
            content = await _func(**arguments)
        else:
            content = _func(**arguments)
        tool_results.append(
            ToolResultDefinition(
                role="tool",
                tool_call_id=tool_call_id,
                name=name,
                content=json.dumps(content),
            )
        )
    return tool_results


async def _stream_request_with_tools(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: list[ToolDefinition],
    tool_executables: Optional[list[Callable]] = None,
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
    extra_headers: Optional[dict[str, str]] = None,
) -> AsyncGenerator[BotMessage, None]:
    aggregated_tool_calls: dict[int, ToolCallDefinition] = {}
    async for message in stream_request_base(
        request=request,
        bot_name=bot_name,
        api_key=api_key,
        tools=tools,
        access_key=access_key,
        access_key_deprecation_warning_stacklevel=access_key_deprecation_warning_stacklevel,
        session=session,
        on_error=on_error,
        num_tries=num_tries,
        retry_sleep_time=retry_sleep_time,
        base_url=base_url,
        extra_headers=extra_headers,
    ):
        if (
            message.data is None
            or "choices" not in message.data
            or not message.data["choices"]
        ):
            yield message
            continue

        # If there is a finish reason, skip the chunk. This should be the same as breaking out of
        # the loop for most models, but we continue to cover situations where other kinds of
        # chunks might stream in after the finish chunk.
        finish_reason = message.data["choices"][0]["finish_reason"]
        if finish_reason is not None:
            continue

        if "tool_calls" in message.data["choices"][0]["delta"]:
            tool_call_deltas: list[ToolCallDefinitionDelta] = [
                ToolCallDefinitionDelta(**tool_call_object)
                for tool_call_object in message.data["choices"][0]["delta"][
                    "tool_calls"
                ]
            ]
            # If tool_executables is not set, return the tool calls without executing them,
            # allowing the caller to manage the tool call loop.
            if tool_executables is None:
                yield BotMessage(
                    text="", tool_calls=tool_call_deltas, index=message.index
                )
                continue

            for tool_call_delta in tool_call_deltas:
                if tool_call_delta.index not in aggregated_tool_calls:
                    # The first chunk of a given index must contain id, type, and function.name.
                    # If this first chunk is missing, the tool call for that index cannot be
                    # aggregated.
                    if (
                        tool_call_delta.id is None
                        or tool_call_delta.type is None
                        or tool_call_delta.function.name is None
                    ):
                        continue

                    aggregated_tool_calls[tool_call_delta.index] = ToolCallDefinition(
                        id=tool_call_delta.id,
                        type=tool_call_delta.type,
                        function=FunctionCallDefinition(
                            name=tool_call_delta.function.name,
                            arguments=tool_call_delta.function.arguments,
                        ),
                    )
                else:
                    aggregated_tool_calls[
                        tool_call_delta.index
                    ].function.arguments += tool_call_delta.function.arguments

        # if no tool calls are selected, the deltas contain content instead of tool_calls
        elif "content" in message.data["choices"][0]["delta"]:
            yield BotMessage(
                text=message.data["choices"][0]["delta"]["content"], index=message.index
            )

    # If tool_executables is not set, exit early since there are no functions to execute.
    if not tool_executables:
        return

    tool_calls: list[ToolCallDefinition] = list(aggregated_tool_calls.values())
    tool_results = await _get_tool_results(tool_executables, tool_calls)

    # If we have tool calls and tool results, we still need to get the final response from the
    # LLM.
    if tool_calls and tool_results:
        async for message in stream_request_base(
            request=request,
            bot_name=bot_name,
            api_key=api_key,
            tools=tools,
            tool_calls=tool_calls,
            tool_results=tool_results,
            access_key=access_key,
            access_key_deprecation_warning_stacklevel=access_key_deprecation_warning_stacklevel,
            session=session,
            on_error=on_error,
            num_tries=num_tries,
            retry_sleep_time=retry_sleep_time,
            base_url=base_url,
            extra_headers=extra_headers,
        ):
            yield message


async def stream_request_base(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: Optional[list[ToolDefinition]] = None,
    tool_calls: Optional[list[ToolCallDefinition]] = None,
    tool_results: Optional[list[ToolResultDefinition]] = None,
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
    extra_headers: Optional[dict[str, str]] = None,
) -> AsyncGenerator[BotMessage, None]:
    if access_key != "":
        warnings.warn(
            "the access_key param is no longer necessary when using this function.",
            DeprecationWarning,
            stacklevel=access_key_deprecation_warning_stacklevel,
        )

    async with contextlib.AsyncExitStack() as stack:
        if session is None:
            session = await stack.enter_async_context(httpx.AsyncClient(timeout=600))
        url = f"{base_url}{bot_name}"
        ctx = _BotContext(
            endpoint=url,
            api_key=api_key,
            session=session,
            on_error=on_error,
            extra_headers=extra_headers,
        )
        got_response = False
        for i in range(num_tries):
            try:
                async for message in ctx.perform_query_request(
                    request=request,
                    tools=tools,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                ):
                    got_response = True
                    yield message
                break
            except BotErrorNoRetry:
                raise
            except Exception as e:
                on_error(e, f"Bot request to {bot_name} failed on try {i}")
                # Want to retry on some errors even if we have streamed part of the request
                # RemoteProtocolError: peer closed connection without sending complete message body
                allow_retry_after_response = isinstance(e, httpx.RemoteProtocolError)
                if (
                    got_response and not allow_retry_after_response
                ) or i == num_tries - 1:
                    # If it's a BotError, it probably has a good error message
                    # that we want to show directly.
                    if isinstance(e, BotError):
                        raise
                    # But if it's something else (maybe an HTTP error or something),
                    # wrap it in a BotError that makes it clear which bot is broken.
                    raise BotError(f"Error communicating with bot {bot_name}") from e
                await asyncio.sleep(retry_sleep_time)


def get_bot_response(
    messages: list[ProtocolMessage],
    bot_name: str,
    api_key: str,
    *,
    tools: Optional[list[ToolDefinition]] = None,
    tool_executables: Optional[list[Callable]] = None,
    temperature: Optional[float] = None,
    skip_system_prompt: Optional[bool] = None,
    adopt_current_bot_name: Optional[bool] = None,
    logit_bias: Optional[dict[str, float]] = None,
    stop_sequences: Optional[list[str]] = None,
    base_url: str = "https://api.poe.com/bot/",
    session: Optional[httpx.AsyncClient] = None,
) -> AsyncGenerator[BotMessage, None]:
    """

    Use this function to invoke another Poe bot from your shell.

    #### Parameters:
    - `messages` (`list[ProtocolMessage]`): A list of messages representing your conversation.
    - `bot_name` (`str`): The bot that you want to invoke.
    - `api_key` (`str`): Your Poe API key. Available at [poe.com/api_key](https://poe.com/api_key)
    - `tools` (`Optional[list[ToolDefinition]] = None`): An list of ToolDefinition objects
    describing the functions you have. This is used for OpenAI function calling.
    - `tool_executables` (`Optional[list[Callable]] = None`): An list of functions corresponding
    to the ToolDefinitions. This is used for OpenAI function calling.
    - `temperature` (`Optional[float] = None`): The temperature to use for the bot.
    - `skip_system_prompt` (`Optional[bool] = None`): Whether to skip the system prompt.
    - `logit_bias` (`Optional[dict[str, float]] = None`): The logit bias to use for the bot.
    - `stop_sequences` (`Optional[list[str]] = None`): The stop sequences to use for the bot.
    - `base_url` (`str = "https://api.poe.com/bot/"`): The base URL to use for the bot. This is
    mainly for internal testing and is not expected to be changed.
    - `adopt_current_bot_name` (`Optional[bool] = None`): Makes the called bot adopt
    the identity of the calling bot
    - `session` (`Optional[httpx.AsyncClient] = None`): The session to use for the bot.
    """
    additional_params = {}
    # This is so that we don't have to redefine the default values for these params.
    if temperature is not None:
        additional_params["temperature"] = temperature
    if skip_system_prompt is not None:
        additional_params["skip_system_prompt"] = skip_system_prompt
    if logit_bias is not None:
        additional_params["logit_bias"] = logit_bias
    if stop_sequences is not None:
        additional_params["stop_sequences"] = stop_sequences
    if adopt_current_bot_name is not None:
        additional_params["adopt_current_bot_name"] = adopt_current_bot_name

    query = QueryRequest(
        query=messages,
        user_id="",
        conversation_id="",
        message_id="",
        version=PROTOCOL_VERSION,
        type="query",
        **additional_params,
    )
    return stream_request(
        request=query,
        bot_name=bot_name,
        api_key=api_key,
        tools=tools,
        tool_executables=tool_executables,
        base_url=base_url,
        session=session,
    )


def get_bot_response_sync(
    messages: list[ProtocolMessage],
    bot_name: str,
    api_key: str,
    *,
    tools: Optional[list[ToolDefinition]] = None,
    tool_executables: Optional[list[Callable]] = None,
    temperature: Optional[float] = None,
    skip_system_prompt: Optional[bool] = None,
    logit_bias: Optional[dict[str, float]] = None,
    adopt_current_bot_name: Optional[bool] = None,
    stop_sequences: Optional[list[str]] = None,
    base_url: str = "https://api.poe.com/bot/",
    session: Optional[httpx.AsyncClient] = None,
) -> Generator[BotMessage, None, None]:
    """

    This function wraps the async generator `fp.get_bot_response` and returns
    partial responses synchronously.

    For asynchronous streaming, or integration into an existing event loop, use
    `fp.get_bot_response` directly.

    #### Parameters:
    - `messages` (`list[ProtocolMessage]`): A list of messages representing your conversation.
    - `bot_name` (`str`): The bot that you want to invoke.
    - `api_key` (`str`): Your Poe API key. This is available at: [poe.com/api_key](https://poe.com/api_key)
    - `tools` (`Optional[list[ToolDefinition]] = None`): An list of ToolDefinition objects
    describing the functions you have. This is used for OpenAI function calling.
    - `tool_executables` (`Optional[list[Callable]] = None`): An list of functions corresponding
    to the ToolDefinitions. This is used for OpenAI function calling.
    - `temperature` (`Optional[float] = None`): The temperature to use for the bot.
    - `skip_system_prompt` (`Optional[bool] = None`): Whether to skip the system prompt.
    - `logit_bias` (`Optional[dict[str, float]] = None`): The logit bias to use for the bot.
    - `stop_sequences` (`Optional[list[str]] = None`): The stop sequences to use for the bot.
    - `base_url` (`str = "https://api.poe.com/bot/"`): The base URL to use for the bot. This is
    mainly for internal testing and is not expected to be changed.
    - `adopt_current_bot_name` (`Optional[bool] = None`): Makes the called bot adopt
    the identity of the calling bot
    - `session` (`Optional[httpx.AsyncClient] = None`): The session to use for the bot.

    """

    async def _async_generator() -> AsyncGenerator[BotMessage, None]:
        async for partial in get_bot_response(
            messages=messages,
            bot_name=bot_name,
            api_key=api_key,
            tools=tools,
            tool_executables=tool_executables,
            temperature=temperature,
            skip_system_prompt=skip_system_prompt,
            adopt_current_bot_name=adopt_current_bot_name,
            logit_bias=logit_bias,
            stop_sequences=stop_sequences,
            base_url=base_url,
            session=session,
        ):
            yield partial

    def _sync_generator() -> Generator[BotMessage, None, None]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async_gen = _async_generator().__aiter__()
        try:
            while True:
                # Pull one item from the async generator at a time,
                # blocking until it’s ready.
                yield loop.run_until_complete(async_gen.__anext__())

        except StopAsyncIteration:
            pass

        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    return _sync_generator()


async def get_final_response(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    access_key: str = "",
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
) -> str:
    """

    A helper function for the bot query API that waits for all the tokens and concatenates the full
    response before returning.

    #### Parameters:
    - `request` (`QueryRequest`): A QueryRequest object representing a query from Poe. This object
    also includes information needed to identify the user for compute point usage.
    - `bot_name` (`str`): The bot you want to invoke.
    - `api_key` (`str = ""`): Your Poe API key, available at poe.com/api_key. You will need this in
    case you are trying to use this function from a script/shell. Note that if an `api_key` is
    provided, compute points will be charged on the account corresponding to the `api_key`.

    """
    chunks: list[str] = []
    async for message in stream_request(
        request,
        bot_name,
        api_key,
        access_key=access_key,
        access_key_deprecation_warning_stacklevel=3,
        session=session,
        on_error=on_error,
        num_tries=num_tries,
        retry_sleep_time=retry_sleep_time,
        base_url=base_url,
    ):
        if isinstance(message, MetaMessage):
            continue
        if message.is_suggested_reply:
            continue
        if message.is_replace_response:
            chunks.clear()
        chunks.append(message.text)
    if not chunks:
        raise BotError(f"Bot {bot_name} sent no response")
    return "".join(chunks)


def sync_bot_settings(
    bot_name: str,
    access_key: str = "",
    *,
    settings: Optional[dict[str, Any]] = None,
    base_url: str = "https://api.poe.com/bot/",
) -> None:
    """Fetch settings from the running bot server, and then sync them with Poe."""
    try:
        if settings is None:
            response = httpx.post(
                f"{base_url}fetch_settings/{bot_name}/{access_key}/{PROTOCOL_VERSION}"
            )
        else:
            headers = {"Content-Type": "application/json"}
            response = httpx.post(
                f"{base_url}update_settings/{bot_name}/{access_key}/{PROTOCOL_VERSION}",
                headers=headers,
                json=settings,
            )
        if response.status_code != 200:
            raise BotError(
                f"Error syncing settings for bot {bot_name}: {response.text}"
            )
    except httpx.ReadTimeout as e:
        error_message = f"Timeout syncing settings for bot {bot_name}."
        if not settings:
            error_message += " Check that the bot server is running."
        raise BotError(error_message) from e
    print(response.text)


async def upload_file(
    file: Optional[Union[bytes, BinaryIO]] = None,
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
    api_key: str = "",
    *,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://www.quora.com/poe_api/",
    extra_headers: Optional[dict[str, str]] = None,
) -> Attachment:
    """
    Upload a file (raw bytes *or* via URL) to Poe and receive an Attachment
    object that can be returned directly from a bot or stored for later use.

    #### Parameters:
    - `file` (`Optional[Union[bytes, BinaryIO]] = None`): The file to upload.
    - `file_url` (`Optional[str] = None`): The URL of the file to upload.
    - `file_name` (`Optional[str] = None`): The name of the file to upload. Required if
    `file` is provided as raw bytes.
    - `api_key` (`str = ""`): Your Poe API key, available at poe.com/api_key. This can
    also be the `access_key` if called from a Poe server bot.

    #### Returns:
    - `Attachment`: An Attachment object representing the uploaded file.

    """
    if not api_key:
        raise ValueError(
            "`api_key` is required (generate one at https://poe.com/api_key)"
        )
    if (file is None and file_url is None) or (file and file_url):
        raise ValueError("Provide either `file` or `file_url`, not both.")

    if file is not None and not file_name:
        if isinstance(file, io.IOBase):
            potential = getattr(file, "name", "")
            if potential:
                file_name = os.path.basename(potential)
            if not file_name:
                raise ValueError(
                    "`file_name` is mandatory when file object has no name attribute."
                )
        elif isinstance(file, (bytes, bytearray)):
            raise ValueError("`file_name` is mandatory when sending raw bytes.")
        else:
            raise ValueError("unsupported file type")

    endpoint = base_url.rstrip("/") + "/file_upload_3RD_PARTY_POST"

    async def _do_upload(_session: httpx.AsyncClient) -> Attachment:
        headers = {"Authorization": api_key}
        if extra_headers is not None:
            headers.update(extra_headers)

        if file_url:
            data: dict[str, str] = {"download_url": file_url}
            if file_name:
                data["download_filename"] = file_name
            request = _session.build_request(
                "POST", endpoint, data=data, headers=headers
            )
        else:  # raw bytes / BinaryIO
            assert (
                file is not None
            ), "file is required if file_url is not provided"  # pyright
            file_data = (
                file.read() if not isinstance(file, (bytes, bytearray)) else file
            )
            files = {"file": (file_name, file_data)}
            request = _session.build_request(
                "POST", endpoint, files=files, headers=headers
            )

        response = await _session.send(request)

        if response.status_code != 200:
            # collect full error text (endpoint streams errors)
            try:
                err_txt = await response.aread()
            except Exception:
                err_txt = response.text
            raise AttachmentUploadError(
                f"{response.status_code} {response.reason_phrase}: {err_txt}"
            )

        data = response.json()
        if not {"attachment_url", "mime_type"}.issubset(data):
            raise AttachmentUploadError(f"Unexpected response format: {data}")

        return Attachment(
            url=data["attachment_url"],
            content_type=data["mime_type"],
            name=file_name or "file",
        )

    # retry wrapper
    _sess = session or httpx.AsyncClient(timeout=120)
    async with _sess:
        for attempt in range(num_tries):
            try:
                return await _do_upload(_sess)
            except Exception as e:
                on_error(e, f"upload attempt {attempt+1}/{num_tries} failed")
                if attempt == num_tries - 1:
                    raise
                await asyncio.sleep(retry_sleep_time)

    raise AssertionError("retries exhausted")  # unreachable, but satisfies pyright


def upload_file_sync(
    file: Optional[Union[bytes, BinaryIO]] = None,
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
    api_key: str = "",
    *,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://www.quora.com/poe_api/",
    extra_headers: Optional[dict[str, str]] = None,
) -> Attachment:
    """
    This is a synchronous wrapper around the async `upload_file`.

    """
    coro = upload_file(
        file=file,
        file_url=file_url,
        file_name=file_name,
        api_key=api_key,
        session=session,
        on_error=on_error,
        num_tries=num_tries,
        retry_sleep_time=retry_sleep_time,
        base_url=base_url,
        extra_headers=extra_headers,
    )
    return run_sync(coro, session=session)

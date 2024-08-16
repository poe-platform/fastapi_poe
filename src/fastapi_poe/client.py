"""

Client for talking to other Poe bots through the Poe bot query API.
For more details, see: https://creator.poe.com/docs/server-bots-functional-guides#accessing-other-bots-on-poe

"""

import asyncio
import contextlib
import inspect
import json
import warnings
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, cast

import httpx
import httpx_sse

from .types import (
    ContentType,
    Identifier,
    ProtocolMessage,
    QueryRequest,
    SettingsResponse,
    ToolCallDefinition,
    ToolDefinition,
    ToolResultDefinition,
)
from .types import MetaResponse as MetaMessage
from .types import PartialResponse as BotMessage

PROTOCOL_VERSION = "1.0"
MESSAGE_LENGTH_LIMIT = 10_000

IDENTIFIER_LENGTH = 32
MAX_EVENT_COUNT = 1000

ErrorHandler = Callable[[Exception, str], None]


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

    @property
    def headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def report_error(
        self, message: str, metadata: Optional[Dict[str, Any]] = None
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
        tools: Optional[List[ToolDefinition]],
        tool_calls: Optional[List[ToolCallDefinition]],
        tool_results: Optional[List[ToolResultDefinition]],
    ) -> AsyncGenerator[BotMessage, None]:
        chunks: List[str] = []
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
                elif event.event == "suggested_reply":
                    text = await self._get_single_json_field(
                        event.data, "suggested_reply", message_id
                    )
                    yield BotMessage(
                        text=text,
                        raw_response={"type": event.event, "text": event.data},
                        full_prompt=repr(request),
                        is_suggested_reply=True,
                    )
                    continue
                elif event.event == "json":
                    yield BotMessage(
                        text="", data=json.loads(event.data), full_prompt=repr(request)
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

    async def _load_json_dict(
        self, data: str, context: str, message_id: Identifier
    ) -> Dict[str, object]:
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
        return cast(Dict[str, object], parsed)


def _default_error_handler(e: Exception, msg: str) -> None:
    print("Error in Poe bot:", msg, "\n", repr(e))


async def stream_request(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: Optional[List[ToolDefinition]] = None,
    tool_executables: Optional[List[Callable]] = None,
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
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
    - tools: (`Optional[List[ToolDefinition]] = None`): An list of ToolDefinition objects describing
    the functions you have. This is used for OpenAI function calling.
    - tool_executables: (`Optional[List[Callable]] = None`): An list of functions corresponding
    to the ToolDefinitions. This is used for OpenAI function calling.

    """
    tool_calls = None
    tool_results = None
    if tools is not None:
        assert tool_executables is not None
        tool_calls = await _get_tool_calls(
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
        )
        tool_results = await _get_tool_results(
            tool_executables=tool_executables, tool_calls=tool_calls
        )
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
    ):
        yield message


async def _get_tool_results(
    tool_executables: List[Callable], tool_calls: List[ToolCallDefinition]
) -> List[ToolResultDefinition]:
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


async def _get_tool_calls(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: List[ToolDefinition],
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
) -> List[ToolCallDefinition]:
    tool_call_object_dict: Dict[int, Dict[str, Any]] = {}
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
    ):
        if message.data is not None:
            finish_reason = message.data["choices"][0]["finish_reason"]
            if finish_reason is None:
                try:
                    tool_call_object = message.data["choices"][0]["delta"][
                        "tool_calls"
                    ][0]
                    index = tool_call_object.pop("index")
                    if index not in tool_call_object_dict:
                        tool_call_object_dict[index] = tool_call_object
                    else:
                        function_info = tool_call_object["function"]
                        tool_call_object_dict[index]["function"][
                            "arguments"
                        ] += function_info["arguments"]
                except KeyError:
                    continue
    tool_call_object_list = [
        tool_call_object
        for index, tool_call_object in sorted(tool_call_object_dict.items())
    ]
    return [
        ToolCallDefinition(**tool_call_object)
        for tool_call_object in tool_call_object_list
    ]


async def stream_request_base(
    request: QueryRequest,
    bot_name: str,
    api_key: str = "",
    *,
    tools: Optional[List[ToolDefinition]] = None,
    tool_calls: Optional[List[ToolCallDefinition]] = None,
    tool_results: Optional[List[ToolResultDefinition]] = None,
    access_key: str = "",
    access_key_deprecation_warning_stacklevel: int = 2,
    session: Optional[httpx.AsyncClient] = None,
    on_error: ErrorHandler = _default_error_handler,
    num_tries: int = 2,
    retry_sleep_time: float = 0.5,
    base_url: str = "https://api.poe.com/bot/",
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
            endpoint=url, api_key=api_key, session=session, on_error=on_error
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
    messages: List[ProtocolMessage],
    bot_name: str,
    api_key: str,
    *,
    tools: Optional[List[ToolDefinition]] = None,
    tool_executables: Optional[List[Callable]] = None,
    temperature: Optional[float] = None,
    skip_system_prompt: Optional[bool] = None,
    logit_bias: Optional[Dict[str, float]] = None,
    stop_sequences: Optional[List[str]] = None,
    base_url: str = "https://api.poe.com/bot/",
    session: Optional[httpx.AsyncClient] = None,
) -> AsyncGenerator[BotMessage, None]:
    """

    Use this function to invoke another Poe bot from your shell.
    #### Parameters:
    - `messages` (`List[ProtocolMessage]`): A list of messages representing your conversation.
    - `bot_name` (`str`): The bot that you want to invoke.
    - `api_key` (`str`): Your Poe API key. This is available at: [poe.com/api_key](https://poe.com/api_key)

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
    chunks: List[str] = []
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
    base_url: str = "https://api.poe.com/bot/fetch_settings/",
) -> None:
    """Sync bot settings with the Poe server using bot name and its Access Key."""
    try:
        response = httpx.post(f"{base_url}{bot_name}/{access_key}/{PROTOCOL_VERSION}")
        if response.status_code != 200:
            raise BotError(
                f"Error fetching settings for bot {bot_name}: {response.text}"
            )
    except httpx.ReadTimeout as e:
        raise BotError(
            f"Timeout fetching settings for bot {bot_name}. Try sync manually later."
        ) from e
    print(response.text)

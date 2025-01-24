

The following is the API reference for the [fastapi_poe](https://github.com/poe-platform/fastapi_poe) client library. The reference assumes that you used `import fastapi_poe as fp`.

## `fp.PoeBot`

The class that you use to define your bot behavior. Once you define your PoeBot class, you
pass it to `make_app` to create a FastAPI app that serves your bot.

#### Parameters:
- `path` (`str = "/"`): This is the path at which your bot is served. By default, it's
set to "/" but this is something you can adjust. This is especially useful if you want to serve
multiple bots from one server.
- `access_key` (`Optional[str] = None`): This is the access key for your bot and when
provided is used to validate that the requests are coming from a trusted source. This access key
should be the same one that you provide when integrating your bot with Poe at:
https://poe.com/create_bot?server=1. You can also set this to None but certain features like
file output that mandate an `access_key` will not be available for your bot.
- `should_insert_attachment_messages` (`bool = True`): A flag to decide whether to parse out
content from attachments and insert them as messages into the conversation. This is set to
`True`by default and we recommend leaving on since it allows your bot to comprehend attachments
uploaded by users by default.
- `concat_attachments_to_message` (`bool = False`): **DEPRECATED**: Please set
`should_insert_attachment_messages` instead.

### `PoeBot.get_response`

Override this to define your bot's response given a user query.
#### Parameters:
- `request` (`QueryRequest`): an object representing the chat response request from Poe.
This will contain information about the chat state among other things.

#### Returns:
- `AsyncIterable[PartialResponse]`: objects representing your
response to the Poe servers. This is what gets displayed to the user.

Example usage:
```python
async def get_response(self, request: fp.QueryRequest) -> AsyncIterable[fp.PartialResponse]:
    last_message = request.query[-1].content
    yield fp.PartialResponse(text=last_message)
```

### `PoeBot.get_response_with_context`

A version of `get_response` that also includes the request context information. By
default, this will call `get_response`.
#### Parameters:
- `request` (`QueryRequest`): an object representing the chat response request from Poe.
This will contain information about the chat state among other things.
- `context` (`RequestContext`): an object representing the current HTTP request.

#### Returns:
- `AsyncIterable[Union[PartialResponse, ErrorResponse]]`: objects representing your
response to the Poe servers. This is what gets displayed to the user.

### `PoeBot.get_settings`

Override this to define your bot's settings.

#### Parameters:
- `setting` (`SettingsRequest`): An object representing the settings request.

#### Returns:
- `SettingsResponse`: An object representing the settings you want to use for your bot.

### `PoeBot.get_settings_with_context`

A version of `get_settings` that also includes the request context information. By
default, this will call `get_settings`.

#### Parameters:
- `setting` (`SettingsRequest`): An object representing the settings request.
- `context` (`RequestContext`): an object representing the current HTTP request.

#### Returns:
- `SettingsResponse`: An object representing the settings you want to use for your bot.

### `PoeBot.on_feedback`

Override this to record feedback from the user.
#### Parameters:
- `feedback_request` (`ReportFeedbackRequest`): An object representing the Feedback rqeuest
from Poe. This is sent out when a user provides feedback on a response on your bot.
#### Returns: `None`

### `PoeBot.on_feedback_with_context`

A version of `on_feedback` that also includes the request context information. By
default, this will call `on_feedback`.

#### Parameters:
- `feedback_request` (`ReportFeedbackRequest`): An object representing a feedback rqeuest
from Poe. This is sent out when a user provides feedback on a response on your bot.
- `context` (`RequestContext`): an object representing the current HTTP request.
#### Returns: `None`

### `PoeBot.on_reaction_with_context`

Override this to record reaction from the user. This also includes the request context
information.

#### Parameters:
- `reaction_request` (`ReportReactionRequest`): An object representing a reaction request
from Poe. This is sent out when a user provides reaction on a response on your bot.
- `context` (`RequestContext`): an object representing the current HTTP request.
#### Returns: `None`

### `PoeBot.on_error`

Override this to record errors from the Poe server.
#### Parameters:
- `error_request` (`ReportErrorRequest`): An object representing an error request from Poe.
This is sent out when the Poe server runs into an issue processing the response from your
bot.
#### Returns: `None`

### `PoeBot.on_error_with_context`

A version of `on_error` that also includes the request context information. By
default, this will call `on_error`.

#### Parameters:
- `error_request` (`ReportErrorRequest`): An object representing an error request from Poe.
This is sent out when the Poe server runs into an issue processing the response from your
bot.
- `context` (`RequestContext`): an object representing the current HTTP request.
#### Returns: `None`

### `PoeBot.post_message_attachment`

Used to output an attachment in your bot's response.

#### Parameters:
- `message_id` (`Identifier`): The message id associated with the current QueryRequest
object. **Important**: This must be the request that is currently being handled by
get_response. Attempting to attach files to previously handled requests will fail.
- `download_url` (`Optional[str] = None`): A url to the file to be attached to the message.
- `download_filename` (`Optional[str] = None`): A filename to be used when storing the
downloaded attachment. If not set, the filename from the `download_url` is used.
- `file_data` (`Optional[Union[bytes, BinaryIO]] = None`): The contents of the file to be
uploaded. This should be a bytes-like or file object.
- `filename` (`Optional[str] = None`): The name of the file to be attached.
- `access_key` (`str`): **DEPRECATED**: Please set the access_key when creating the Bot
object instead.
#### Returns:
- `AttachmentUploadResponse`

**Note**: You need to provide either the `download_url` or both of `file_data` and
`filename`.

### `PoeBot.concat_attachment_content_to_message_body`

**DEPRECATED**: This method is deprecated. Use `insert_attachment_messages` instead.

Concatenate received attachment file content into the message body. This will be called
by default if `concat_attachments_to_message` is set to `True` but can also be used
manually if needed.

#### Parameters:
- `query_request` (`QueryRequest`): the request object from Poe.
#### Returns:
- `QueryRequest`: the request object after the attachments are unpacked and added to the
message body.

### `PoeBot.insert_attachment_messages`

Insert messages containing the contents of each user attachment right before the last user
message. This ensures the bot can consider all relevant information when generating a
response. This will be called by default if `should_insert_attachment_messages` is set to
`True` but can also be used manually if needed.

#### Parameters:
- `query_request` (`QueryRequest`): the request object from Poe.
#### Returns:
- `QueryRequest`: the request object after the attachments are unpacked and added to the
message body.

### `PoeBot.make_prompt_author_role_alternated`

Concatenate consecutive messages from the same author into a single message. This is useful
for LLMs that require role alternation between user and bot messages.

#### Parameters:
- `protocol_messages` (`Sequence[ProtocolMessage]`): the messages to make alternated.
#### Returns:
- `Sequence[ProtocolMessage]`: the modified messages.

### `PoeBot.capture_cost`

Used to capture variable costs for monetized and eligible bot creators.
Visit https://creator.poe.com/docs/creator-monetization for more information.

#### Parameters:
- `request` (`QueryRequest`): The currently handled QueryRequest object.
- `amounts` (`Union[list[CostItem], CostItem]`): The to be captured amounts.

#### Returns: `None`

### `PoeBot.authorize_cost`

Used to authorize a cost for monetized and eligible bot creators.
Visit https://creator.poe.com/docs/creator-monetization for more information.

#### Parameters:
- `request` (`QueryRequest`): The currently handled QueryRequest object.
- `amounts` (`Union[list[CostItem], CostItem]`): The to be authorized amounts.

#### Returns: `None`



---

## `fp.make_app`

Create an app object for your bot(s).

#### Parameters:
- `bot` (`Union[PoeBot, Sequence[PoeBot]]`): A bot object or a list of bot objects if you want
to host multiple bots on one server.
- `access_key` (`str = ""`): The access key to use.  If not provided, the server tries to
read the POE_ACCESS_KEY environment variable. If that is not set, the server will
refuse to start, unless `allow_without_key` is True. If multiple bots are provided,
the access key must be provided as part of the bot object.
- `bot_name` (`str = ""`): The name of the bot as it appears on poe.com.
- `api_key` (`str = ""`): **DEPRECATED**: Please set the access_key when creating the Bot
object instead.
- `allow_without_key` (`bool = False`): If True, the server will start even if no access
key is provided. Requests will not be checked against any key. If an access key is provided, it
is still checked.
- `app` (`Optional[FastAPI] = None`): A FastAPI app instance. If provided, the app will be
configured with the provided bots, access keys, and other settings. If not provided, a new
FastAPI application instance will be created and configured.
#### Returns:
- `FastAPI`: A FastAPI app configured to serve your bot when run.



---

## `fp.run`

Serve a poe bot using a FastAPI app. This function should be used when you are running the
bot locally. The parameters are the same as they are for `make_app`.

#### Returns: `None`



---

## `fp.stream_request`

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
- tools: (`Optional[list[ToolDefinition]] = None`): An list of ToolDefinition objects describing
the functions you have. This is used for OpenAI function calling.
- tool_executables: (`Optional[list[Callable]] = None`): An list of functions corresponding
to the ToolDefinitions. This is used for OpenAI function calling.



---

## `fp.get_bot_response`

Use this function to invoke another Poe bot from your shell.
#### Parameters:
- `messages` (`list[ProtocolMessage]`): A list of messages representing your conversation.
- `bot_name` (`str`): The bot that you want to invoke.
- `api_key` (`str`): Your Poe API key. This is available at: [poe.com/api_key](https://poe.com/api_key)



---

## `fp.get_final_response`

A helper function for the bot query API that waits for all the tokens and concatenates the full
response before returning.

#### Parameters:
- `request` (`QueryRequest`): A QueryRequest object representing a query from Poe. This object
also includes information needed to identify the user for compute point usage.
- `bot_name` (`str`): The bot you want to invoke.
- `api_key` (`str = ""`): Your Poe API key, available at poe.com/api_key. You will need this in
case you are trying to use this function from a script/shell. Note that if an `api_key` is
provided, compute points will be charged on the account corresponding to the `api_key`.



---

## `fp.QueryRequest`

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



---

## `fp.ProtocolMessage`

A message as used in the Poe protocol.
#### Fields:
- `role` (`Literal["system", "user", "bot"]`)
- `sender_id` (`Optional[str]`)
- `content` (`str`)
- `content_type` (`ContentType="text/markdown"`)
- `timestamp` (`int = 0`)
- `message_id` (`str = ""`)
- `feedback` (`list[MessageFeedback] = []`)
- `attachments` (`list[Attachment] = []`)



---

## `fp.PartialResponse`

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



---

## `fp.ErrorResponse`

Similar to `PartialResponse`. Yield this to communicate errors from your bot.

#### Fields:
- `allow_retry` (`bool = False`): Whether or not to allow a user to retry on error.
- `error_type` (`Optional[ErrorType] = None`): An enum indicating what error to display.



---

## `fp.MetaResponse`

Similar to `Partial Response`. Yield this to communicate `meta` events from server bots.

#### Fields:
- `suggested_replies` (`bool = False`): Whether or not to enable suggested replies.
- `content_type` (`ContentType = "text/markdown"`): Used to describe the format of the response.
The currently supported values are `text/plain` and `text/markdown`.
- `refetch_settings` (`bool = False`): Used to trigger a settings fetch request from Poe. A more
robust way to trigger this is documented at:
https://creator.poe.com/docs/server-bots-functional-guides#updating-bot-settings



---

## `fp.SettingsRequest`

Request parameters for a settings request. Currently, this contains no fields but this
might get updated in the future.



---

## `fp.SettingsResponse`

An object representing your bot's response to a settings object.
#### Fields:
- `server_bot_dependencies` (`dict[str, int] = {}`): Information about other bots that your bot
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



---

## `fp.ReportFeedbackRequest`

Request parameters for a report_feedback request.
#### Fields:
- `message_id` (`Identifier`)
- `user_id` (`Identifier`)
- `conversation_id` (`Identifier`)
- `feedback_type` (`FeedbackType`)



---

## `fp.ReportErrorRequest`

Request parameters for a report_error request.
#### Fields:
- `message` (`str`)
- `metadata` (`dict[str, Any]`)



---

## `fp.Attachment`

Attachment included in a protocol message.
#### Fields:
- `url` (`str`)
- `content_type` (`str`)
- `name` (`str`)
- `parsed_content` (`Optional[str] = None`)



---

## `fp.MessageFeedback`

Feedback for a message as used in the Poe protocol.
#### Fields:
- `type` (`FeedbackType`)
- `reason` (`Optional[str]`)



---

## `fp.ToolDefinition`

An object representing a tool definition used for OpenAI function calling.
#### Fields:
- `type` (`str`)
- `function` (`FunctionDefinition`): Look at the source code for a detailed description
of what this means.



---

## `fp.ToolCallDefinition`

An object representing a tool call. This is returned as a response by the model when using
OpenAI function calling.
#### Fields:
- `id` (`str`)
- `type` (`str`)
- `function` (`FunctionDefinition`): Look at the source code for a detailed description
of what this means.



---

## `fp.ToolResultDefinition`

An object representing a function result. This is passed to the model in the last step
when using OpenAI function calling.
#### Fields:
- `role` (`str`)
- `name` (`str`)
- `tool_call_id` (`str`)
- `content` (`str`)

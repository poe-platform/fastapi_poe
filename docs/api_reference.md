The following it the API reference for the
[fastapi_poe](https://github.com/poe-platform/fastapi_poe) client library.

# `class PoeBot`

The class that you use to define your bot behavior.Once you define your PoeBot class,
you pass it to make_run to serve that bot.

#### Parameters:

- `path`: This is the path at which your bot is served. By default, it's set to "/" but
  this is something you can adjust. This is especially useful if you want to serve
  multiple bots from one server.
- `access_key`: This is the access key for your bot and when provided is used to
  validate that requests are coming from a trusted source. This access key should be the
  same one that you provide when integrating your bot with Poe at:
  https://poe.com/create_bot?server=1. You can also set this to None but certain
  features like file-output that mandate an `access_key` will not be available to your
  bot.
- `concat_attachments_to_message`: A flag to decide whether to parse out content from
  attachments and concatenate it to the conversation message. This is set to `True` by
  default and we recommend leaving it at that for most developers since it allows your
  bot to comprehent attachments uploaded by users by default.

### `PoeBot.get_response`

Override this to return a response to user queries.

### `PoeBot.get_response_with_context`

A version of `get_response` that also passes in the request context information. By
default, this will call `get_response`.

### `PoeBot.get_settings`

Override this to return non-standard settings.

### `PoeBot.get_settings_with_context`

A version of `get_settings` that also passes in the request context information. By
default, this will call `get_settings`.

### `PoeBot.on_feedback`

Override this to record feedback from the user.

### `PoeBot.on_feedback_with_context`

A version of `on_feedback` that also passes in the request context information. By
default, this will call `on_feedback`.

### `PoeBot.on_error`

Override this to record errors from the Poe server.

### `PoeBot.on_error_with_context`

A version of `on_error` that also passes in the request context information. By default,
this will call `on_error`.

### `PoeBot.post_message_attachment`

Used to output an attachment in the response.

#### Parameters:

- `message_id` (str): the message id associated with the currentQueryRequest object
  being processed. **Important**: This must be the request that is currently being
  handled by get_response. Attempting to attach files to previously handled requests
  will fail.
- `download_url` (str): provide a url to a file that will be attached to the message.
- `file_data` (bytes): the contents of the file to be uploaded. This should be a
  bytes-like or file object.
- `filename` - the name of the file to be attached.

**Note**: You need to provide either the `download_url` or both of `file_data` and
`filename`.

### `PoeBot.concat_attachment_content_to_message_body`

Concatenate received attachment file content into the message body.

# `def make_app`

Create an app object for your bot(s).

#### Parameters:

- `bot`: A bot object or a list of bot objects if you want to host multiple bots on one
  server.
- `access_key`: The access key to use. If not provided, the server tries to read the
  POE_ACCESS_KEY environment variable. If that is not set, the server will refuse to
  start, unless `allow_without_key` is True. If multiple bots are provided, the access
  key must be provided as part of the bot object.
- `api_key`: The previous name of access_key. This is not to be confused with the
  api_key param needed by `stream_request`. This param is deprecated and will be removed
  in a future version.
- allow_without_key`: If True, the server will start even if no access key is provided.
  Requests will not be checked against any key. If an access key is provided, it is
  still checked.
- `app`: A FastAPI app instance. If provided, the app will be configured with the
  provided bots, access keys, and other settings. If not provided, a new FastAPI
  application instance will be created and configured.

# `def run`

Run a Poe bot server using FastAPI. This function should be used when you are running
the bot locally. The arguments are the same as that for `make_app`.

# `def stream_request`

Entry point for the Bot Query API. This API allows you to use other bots on Poe for
inference in response to a user message. For more details, checkout:
https://creator.poe.com/docs/accessing-other-bots-on-poe

#### Parameters:

- `request`: A QueryRequest object representing a query from Poe. This object also
  includes information needed to identify the user for compute point usage.
- `bot_name`: The bot you want to invoke.
- `api_key`: Your Poe API key, available at poe.com/api_key. You will need this in case
  you are trying to use this function from a script/shell. compute points may apply
  depending on the bot you call.

# `def get_bot_response`

Use this function to invoke another Poe bot from your shell.

#### Parameters:

- `messages`: A list of protocol messages representing your conversation
- `bot_name`: The bot that you want to invoke.
- `api_key`: Your Poe API key. This is available at: poe.com/api_key

# `def get_final_response`

Another helper function for you to be able to use the bot query API. Waits for all the
tokens and concatenates the full response before returning.

#### Parameters:

- `request`: A QueryRequest object representing a query from Poe. This object also
  includes information needed to identify the user for compute point usage.
- `bot_name`: The bot you want to invoke.
- `api_key`: Your Poe API key, available at poe.com/api_key. You will need this in case
  you are trying to use this function from a script/shell. compute points may apply
  depending on the bot you call.

# `class PartialResponse`

Representation of a (possibly partial) response from a bot. Yield this in your
`PoeBot.get_response` or `PoeBot.get_response_with_context` while setting values
appropriately to communicate your response to Poe.

#### Parameters:

- `text`: The actual text you want to display to the user. Note that this solely be the
  text in the next token as Poe will automatically concatenate all tokens before
  displaying the response to the user.
- `data`: Used to send json data to Poe. This is currently only used in the context of
  OpenAI function calling.
- `is_suggested_reply`: Seting this to true will create a suggested reply with the
  provided text string.
- `is_replace_response`: Setting this to true will clear out the previously displayed
  text to the user and replace it with the provided str.

# `class ErrorResponse`

Similar to `PartialResponse`. Yield this to communicate errors from your bot.

#### Parameters:

- `allow_retry`: Whether or not to allow a user to retry on error.
- `error_type`: An enum indicating what error to display.

# `class MetaResponse`

Similar to `Partial Response`. Yield this to communicate 'meta' events from server bots.

#### Parameters:

- `suggested_replies`: Whether or not enable suggested replies.
- `content_type`: Used to describe the format of the response. The currently supported
  values are `text/plain` and `text/markdown`.
- `refetch_settings`: Used to trigger a settings fetch request from Poe. A more robust
  way to trigger this is documented at:
  https://creator.poe.com/docs/updating-bot-settings

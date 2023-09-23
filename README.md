# fastapi_poe

An implementation of the Poe protocol using FastAPI.

To run it:

- Create a virtual environment (Python 3.7 or higher)
- `pip install .`
- `python -m fastapi_poe`
- In a different terminal, run [ngrok](https://ngrok.com/) to make it publicly
  accessible

## Write your own bot

This package can also be used as a base to write your own bot. You can inherit from
`fastapi_poe.PoeBot` to make a bot:

```python
from fastapi_poe import PoeBot, run
from fastapi_poe.types import PartialResponse

class EchoBot(PoeBot):
    async def get_response(self, request):
        last_message = request.query[-1].content
        yield PartialResponse(text=last_message)

if __name__ == "__main__":
    run(EchoBot())
```

## Enable authentication

Poe servers send requests containing Authorization HTTP header in the format "Bearer
<access_key>"; the access key is configured in the bot settings page.

To validate that the request is from the Poe servers, you can either set the environment
variable POE_ACCESS_KEY or pass the parameter access_key in the run function like:

```python
if __name__ == "__main__":
    run(EchoBot(), access_key=<key>)
```

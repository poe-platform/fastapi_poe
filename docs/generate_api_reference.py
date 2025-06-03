"""

- To generate reference documentation:
  - Add/update docstrings in the codebase. If you are adding a new class/function, add
    it's name to `documented_items` in `docs/generate_api_reference.py`
  - Install local version of fastapi_poe: `pip install -e .`
  - run `python3 generate_api_reference.py`
  - [Internal only] Copy the contents of `api_reference.md` to the reference page in
    README.

"""

import inspect
import sys
import types
from dataclasses import dataclass, field
from typing import Callable, Optional, Union

sys.path.append("../src")
import fastapi_poe

INITIAL_TEXT = """

The following is the API reference for the \
[fastapi_poe](https://github.com/poe-platform/fastapi_poe) client library. The reference assumes \
that you used `import fastapi_poe as fp`.

"""


@dataclass
class DocumentationData:
    name: str
    docstring: Optional[str]
    data_type: str
    children: list = field(default_factory=lambda: [])


def _unwrap_func(func_obj: Union[staticmethod, Callable]) -> Callable:
    """Grab the underlying func_obj."""
    if isinstance(func_obj, staticmethod):
        return _unwrap_func(func_obj.__func__)
    return func_obj


def get_documentation_data(
    *, module: types.ModuleType, documented_items: list[str]
) -> dict[str, DocumentationData]:
    data_dict = {}
    for name, obj in inspect.getmembers(module):
        if (
            inspect.isclass(obj) or inspect.isfunction(obj)
        ) and name in documented_items:
            doc = inspect.getdoc(obj)
            data_type = "class" if inspect.isclass(obj) else "function"
            dd_obj = DocumentationData(name=name, docstring=doc, data_type=data_type)

            if inspect.isclass(obj):
                children = []
                # for func_name, func_obj in inspect.getmembers(obj, inspect.isfunction):
                for func_name, func_obj in obj.__dict__.items():
                    if not inspect.isfunction(func_obj):
                        continue
                    if not func_name.startswith("_"):
                        func_obj = _unwrap_func(func_obj)
                        func_doc = inspect.getdoc(func_obj)
                        children.append(
                            DocumentationData(
                                name=func_name, docstring=func_doc, data_type="function"
                            )
                        )
                dd_obj.children = children
            data_dict[name] = dd_obj
    return data_dict


def generate_documentation(
    *,
    data_dict: dict[str, DocumentationData],
    documented_items: list[str],
    output_filename: str,
) -> None:
    # reset the file first
    with open(output_filename, "w") as f:
        f.write("")

    with open(output_filename, "w") as f:
        f.write(INITIAL_TEXT)

        first = True
        for item in documented_items:
            if first is True:
                first = False
            else:
                f.write("---\n\n")
            item_data = data_dict[item]
            f.write(f"## `fp.{item_data.name}`\n\n")
            f.write(f"{item_data.docstring}\n\n")
            for child in item_data.children:
                if not child.docstring:
                    continue
                f.write(f"### `{item}.{child.name}`\n\n")
                f.write(f"{child.docstring}\n\n")
            f.write("\n\n")


# Specify the names of classes and functions to document
documented_items = [
    "PoeBot",
    "make_app",
    "run",
    "stream_request",
    "get_bot_response",
    "get_bot_response_sync",
    "get_final_response",
    "upload_file",
    "upload_file_sync",
    "QueryRequest",
    "ProtocolMessage",
    "PartialResponse",
    "ErrorResponse",
    "MetaResponse",
    "DataResponse",
    "AttachmentUploadResponse",
    "SettingsRequest",
    "SettingsResponse",
    "ReportFeedbackRequest",
    "ReportReactionRequest",
    "ReportErrorRequest",
    "Attachment",
    "MessageFeedback",
    "ToolDefinition",
    "ToolCallDefinition",
    "ToolResultDefinition",
]

data_dict = get_documentation_data(
    module=fastapi_poe, documented_items=documented_items
)
output_filename = "api_reference.md"
generate_documentation(
    data_dict=data_dict,
    documented_items=documented_items,
    output_filename=output_filename,
)

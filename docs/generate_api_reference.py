import inspect
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

INITIAL_TEXT = """

The following it the API reference for the
[fastapi_poe](https://github.com/poe-platform/fastapi_poe) client library.

"""


@dataclass
class DocumentationData:
    name: str
    docstring: Optional[str]
    data_type: str
    children: List = field(default_factory=lambda: [])


def _unwrap_func(func_obj):
    """This is to ensure we get the docstring from the actual func and not a decorator."""
    if isinstance(func_obj, staticmethod):
        return _unwrap_func(func_obj.__func__)
    if hasattr(func_obj, "__wrapped__"):
        return _unwrap_func(func_obj.__wrapped__)
    return func_obj


def get_documentation_data(*, module, documented_items) -> Dict[str, DocumentationData]:
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
    *, data_dict: Dict[str, DocumentationData], documented_items, output_filename
):
    # reset the file first
    with open(output_filename, "w") as f:
        f.write("")

    with open(output_filename, "w") as f:
        f.write(INITIAL_TEXT)

        for item in documented_items:
            item_data = data_dict[item]
            prefix = "class" if item_data.data_type == "class" else "def"
            f.write(f"# `{prefix} {item_data.name}`\n\n")
            f.write(f"{item_data.docstring}\n\n")
            for child in item_data.children:
                if not child.docstring:
                    continue
                f.write(f"### `{item}.{child.name}`\n\n")
                f.write(f"{child.docstring}\n\n")
            f.write("\n\n")


# Usage example
sys.path.append("../src")
import fastapi_poe

# Specify the names of classes and functions to document
documented_items = [
    "PoeBot",
    "make_app",
    "run",
    "stream_request",
    "get_bot_response",
    "get_final_response",
    "PartialResponse",
    "ErrorResponse",
    "MetaResponse",
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

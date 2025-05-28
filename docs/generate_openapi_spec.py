"""Generate an OpenAPI spec and simple endpoint summary."""

import json
import sys
from pathlib import Path

# Ensure local imports use the source tree regardless of the cwd
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from fastapi_poe import PoeBot, make_app


def main() -> None:
    bot = PoeBot(path="/bot", access_key="test")
    app = make_app(bot, allow_without_key=True)
    spec = app.openapi()

    out_dir = Path(__file__).parent
    json_path = out_dir / "openapi.json"
    with json_path.open("w") as f:
        json.dump(spec, f, indent=2)

    md_path = out_dir / "openapi_endpoints.md"
    with md_path.open("w") as f:
        f.write("# FastAPI Poe Endpoints\n\n")
        for route, methods in spec.get("paths", {}).items():
            f.write(f"## `{route}`\n\n")
            f.write("Methods:\n")
            for method in methods:
                f.write(f"- `{method.upper()}`\n")
            f.write("\n")


if __name__ == "__main__":
    main()

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    os.environ.setdefault("DATABASE_URL", "sqlite://")
    sys.path.insert(0, str(PROJECT_ROOT))

    from minutes.api import app

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

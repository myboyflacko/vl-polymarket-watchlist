import json
import sys
import traceback
from typing import Any


def log_error(event: str, exc: Exception, **context: Any) -> None:
    payload = {
        "level": "error",
        "event": event,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "context": context,
        "traceback": traceback.format_exc(),
    }

    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
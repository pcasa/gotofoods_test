"""Central logging seam — all application code logs through these helpers.

Lives in `core` (framework-free, no Django or domain imports) so any app in
this project — or a future sibling service — can use it unchanged.

Events are emitted as `event_name key=value ...` lines to the `app` stdlib
logger, so call sites never touch a vendor SDK. To add sinks later, pick one of
two extension points (no call-site changes either way):

1. Handler-based (preferred): attach a handler/formatter to the "app" logger
   in settings.LOGGING — e.g. a JSON formatter shipped by a Datadog agent
   tail, `datadog.dogstatsd`'s log handler, or `sentry_sdk`'s
   LoggingIntegration (which turns ERROR records into Sentry events).
2. In-band: for sinks needing richer payloads than a formatted line, call the
   vendor SDK inside _emit() with the structured `context` dict — it is kept
   intact here for exactly that purpose.
"""

import logging
from typing import Any

_logger = logging.getLogger("app")


def info(event: str, **context: Any) -> None:
    _emit(logging.INFO, event, context)


def warning(event: str, **context: Any) -> None:
    _emit(logging.WARNING, event, context)


def error(event: str, exc: BaseException | None = None, **context: Any) -> None:
    _emit(logging.ERROR, event, context, exc=exc)


def _emit(
    level: int, event: str, context: dict[str, Any], exc: BaseException | None = None
) -> None:
    parts = [event, *(f"{key}={value}" for key, value in context.items())]
    _logger.log(level, " ".join(parts), exc_info=exc)

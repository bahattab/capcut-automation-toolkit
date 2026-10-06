"""Public error boundary; raw tracebacks are logged to stderr only."""
from functools import wraps
import logging
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
LOG = logging.getLogger("capcut-kit")


class BridgeError(Exception):
    """A safe, actionable validation error."""


def backend(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return function(*args, **kwargs)
        except BridgeError:
            LOG.exception("Backend validation failed in %s", function.__name__)
            raise
        except Exception as error:
            LOG.exception("Unexpected backend error in %s", function.__name__)
            raise BridgeError("An unexpected error occurred. Please try again later.") from error
    return guarded


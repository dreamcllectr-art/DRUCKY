"""Exponential backoff + jitter decorator for all API fetchers.

Usage:
    from tools.utils.rate_limiter import rate_limited

    @rate_limited(max_retries=4, base_delay=1.0, max_delay=60.0)
    def _fetch_symbol(symbol):
        ...

Triggers on: HTTP 429, 503, requests.ConnectionError, requests.Timeout.
Final retry failure: re-raises so module_logger can capture it upstream.
"""

import logging
import random
import time
from functools import wraps

import requests

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 503}


def rate_limited(max_retries: int = 4, base_delay: float = 1.0,
                 max_delay: float = 60.0, jitter: bool = True):
    """Decorator factory for HTTP functions that may hit rate limits.

    Backoff formula: min(base * 2^attempt + uniform(0, 1), max_delay)
    attempt is 0-indexed, so first retry waits base_delay seconds.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    result = fn(*args, **kwargs)
                    # If the function returns a requests.Response, check status
                    if isinstance(result, requests.Response):
                        if result.status_code in _RETRYABLE_STATUS:
                            raise _RateLimitError(result.status_code)
                    return result
                except _RateLimitError as e:
                    last_exc = e
                    if attempt == max_retries:
                        break
                    delay = _backoff(attempt, base_delay, max_delay, jitter)
                    logger.warning(
                        f"{fn.__name__} rate-limited (HTTP {e.status}), "
                        f"retry {attempt+1}/{max_retries} in {delay:.1f}s"
                    )
                    time.sleep(delay)
                except (requests.ConnectionError, requests.Timeout) as e:
                    last_exc = e
                    if attempt == max_retries:
                        break
                    delay = _backoff(attempt, base_delay, max_delay, jitter)
                    logger.warning(
                        f"{fn.__name__} connection error, "
                        f"retry {attempt+1}/{max_retries} in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


def _backoff(attempt: int, base: float, max_delay: float, jitter: bool) -> float:
    delay = min(base * (2 ** attempt), max_delay)
    if jitter:
        delay += random.uniform(0, 1)
    return delay


class _RateLimitError(Exception):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"HTTP {status}")

import time

DEFAULT_RETRY_TIMEOUT_S = 45  # tiempo total máximo de reintentos
BACKOFF_BASE_S = 1.5


def retry(fn, timeout_s=DEFAULT_RETRY_TIMEOUT_S):
    deadline = time.monotonic() + timeout_s
    delay = BACKOFF_BASE_S
    while True:
        try:
            return fn()
        except ConnectionError:
            if time.monotonic() + delay > deadline:
                raise
            time.sleep(delay)
            delay *= 2

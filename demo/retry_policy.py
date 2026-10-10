"""Demo-only backoff for completed 429 responses; no replay of unknown outcomes."""

SAMPLE_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 30


def retry_delay(error, attempts, remaining):
    if not error.retry_allowed or attempts >= MAX_ATTEMPTS:
        return None
    delay = max(2 ** attempts, error.retry_after_seconds)
    if delay > MAX_WAIT_SECONDS or delay >= remaining:
        return None
    return delay

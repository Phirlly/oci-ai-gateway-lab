"""Verify the presenter journey and synthetic workload with bounded model calls."""

import time

from runtime.gateway_http import GatewayError, GatewayHTTP
from runtime.presenter_api import presenter_session

from .results import completion, streamed_completion
from .response_errors import ModelRouteError
from .retry_policy import MAX_ATTEMPTS, SAMPLE_TIMEOUT_SECONDS, retry_delay
from .samples import CATEGORIES, load_samples, request_body


def check_health(public):
    if public.request("GET", "/health/liveliness", timeout=10).status != 200:
        raise GatewayError("Gateway process is not available")
    response = public.request("GET", "/health/readiness", timeout=10)
    if response.status != 200:
        raise GatewayError("Gateway database is not ready")
    value = response.json()
    if not isinstance(value, dict) or value.get("db") != "connected":
        raise GatewayError("Gateway database is not connected")


class PresenterUnavailable(GatewayError):
    """The configured account cannot yet log in; bootstrap may still be running."""


def presenter_client(public, presenter, password):
    if not isinstance(password, str) or not 0 < len(password) <= 256:
        raise GatewayError("A current presenter password is required")
    response = public.request("POST", "/v2/login", {"username": presenter.email, "password": password})
    if response.status != 200:
        raise PresenterUnavailable("Presenter login failed; verify the current DEMO_PASSWORD")
    value = response.json()
    if not isinstance(value, dict):
        raise GatewayError("Presenter login returned invalid data")
    session = GatewayHTTP(public.base_url, presenter_session(value, presenter), allow_loopback=True)
    response = session.request("GET", "/model_group/info")
    try:
        value = response.json()
        rows = value["data"]
        if (response.status != 200 or not isinstance(rows, list) or len(rows) != 2
                or {row["model_group"] for row in rows} != set(presenter.models)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise GatewayError("Presenter model access does not match the two configured routes") from None
    if session.request("GET", "/user/list").status != 403:
        raise GatewayError("Presenter administrative access restriction could not be verified")
    return session


def _sample(client, sample, model, stream):
    result = {"model": model, "sample": sample.identifier, "stream": stream,
              "expected": sample.expected, "category": None, "usage": None,
              "cost_usd": None, "status": "ERROR", "error": None, "error_details": None,
              "attempts": 0, "retry_wait_seconds": 0}
    started = time.monotonic()
    deadline = started + SAMPLE_TIMEOUT_SECONDS
    body = request_body(sample, model, stream=stream)
    while result['attempts'] < MAX_ATTEMPTS:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        result['attempts'] += 1
        try:
            response = client.request("POST", "/chat/completions", body, timeout=remaining)
            answer, usage = (streamed_completion if stream else completion)(response, model)
            category = answer.upper()
            result.update(category=category if category in CATEGORIES else "INVALID_CATEGORY", usage=usage,
                          status="PASS" if category == sample.expected else "FAIL", error=None, error_details=None)
        except ModelRouteError as error:
            result.update(error=str(error), error_details=error.details)
            delay = retry_delay(error, result['attempts'], deadline - time.monotonic())
            if delay is not None:
                waiting = time.monotonic()
                time.sleep(delay)
                result['retry_wait_seconds'] += time.monotonic() - waiting
                continue
        except GatewayError as error:
            # Owned errors contain categories/status only, never upstream response bodies.
            result.update(error=str(error), error_details=None)
        except TimeoutError:
            result.update(error="Model request timed out; no further retry was made", error_details=None)
        break
    result['retry_wait_seconds'] = round(result['retry_wait_seconds'], 3)
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def verify_demo(public, presenter, password):
    """Caller supplies a verified-HTTPS client; explicit loopback is for contracts only."""
    samples = load_samples()
    check_health(public)
    session = presenter_client(public, presenter, password)
    results = []
    for model in presenter.models:
        results.extend(_sample(session, sample, model, False) for sample in samples)
        results.append(_sample(session, samples[0], model, True))
    return {"ready": all(result["status"] == "PASS" for result in results),
            "login": "PASS", "model_access": "PASS", "admin_denial": "PASS", "samples": results}

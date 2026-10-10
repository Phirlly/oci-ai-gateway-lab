"""Accept only complete, nonempty responses attributed to the requested route."""

import json

from runtime.gateway_http import GatewayError


def _attributed(response, model):
    if response.status != 200:
        raise GatewayError(f"Model route returned HTTP {response.status}")
    if response.headers.get("x-litellm-model-id") != model:
        raise GatewayError("Model route attribution is missing or does not match")


def _usage(value):
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    if (not isinstance(value, dict)
            or any(type(value.get(name)) is not int or value[name] < 0 for name in fields)):
        return None
    return {name: value[name] for name in fields}


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError
    return value.strip()


def completion(response, model):
    _attributed(response, model)
    try:
        value = response.json()
        choices = value["choices"]
        if (not isinstance(choices, list) or len(choices) != 1
                or choices[0].get("index", 0) != 0 or choices[0]["finish_reason"] != "stop"):
            raise ValueError
        return _text(choices[0]["message"]["content"]), _usage(value.get("usage"))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise GatewayError("Model completion is empty, truncated or invalid") from None


def streamed_completion(response, model):
    _attributed(response, model)
    try:
        events = [line[5:].lstrip(" ") for line in response.body.decode("utf-8").splitlines() if line.startswith("data:")]
        if not 2 <= len(events) <= 512 or events[-1] != "[DONE]" or "[DONE]" in events[:-1]:
            raise ValueError
        text, stopped, usage = "", False, None
        for raw in events[:-1]:
            value = json.loads(raw)
            if not isinstance(value, dict) or "error" in value:
                raise ValueError
            if value.get("usage") is not None:
                usage = _usage(value["usage"])
            choices = value["choices"]
            if not isinstance(choices, list) or len(choices) > 1:
                raise ValueError
            if not choices:
                continue
            choice = choices[0]
            if stopped:
                # Pinned LiteLLM retains an empty choice in its final usage chunk.
                if (choice.get('index') == 0 and choice.get('delta') == {}
                        and choice.get('finish_reason') is None and _usage(value.get('usage')) is not None):
                    continue
                raise ValueError
            if choice.get("index", 0) != 0 or choice.get("finish_reason") not in (None, "stop"):
                raise ValueError
            fragment = choice["delta"].get("content")
            if fragment is not None:
                if not isinstance(fragment, str):
                    raise ValueError
                text += fragment
                if len(text) > 512:
                    raise ValueError
            stopped = choice.get("finish_reason") == "stop"
        if not stopped:
            raise ValueError
        return _text(text), usage
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise GatewayError("Model stream is incomplete or invalid") from None

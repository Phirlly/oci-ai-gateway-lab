"""Three synthetic support requests, identical across both configured routes."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from runtime.gateway_http import GatewayError

CATEGORIES = frozenset({"BILLING", "ACCESS", "TECHNICAL"})
INSTRUCTION = (
    "Classify the support request into exactly one category: BILLING for payments or invoices, "
    "ACCESS for signing in or account access, TECHNICAL for product failures. "
    "Reply with only the category name."
)


@dataclass(frozen=True)
class Sample:
    identifier: str
    text: str
    expected: str


def load_samples():
    directory = Path(__file__).parent
    try:
        requests = json.loads((directory / "support-requests.json").read_text())
        expected = json.loads((directory / "expected-categories.json").read_text())
        if not isinstance(requests, list) or not 1 <= len(requests) <= 10 or not isinstance(expected, dict):
            raise ValueError
        samples, identifiers = [], set()
        for row in requests:
            if (not isinstance(row, dict) or set(row) != {"id", "text"}
                    or not isinstance(row["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", row["id"])
                    or row["id"] in identifiers or not isinstance(row["text"], str)
                    or not 0 < len(row["text"]) <= 2000 or expected[row["id"]] not in CATEGORIES):
                raise ValueError
            identifiers.add(row["id"])
            samples.append(Sample(row["id"], row["text"], expected[row["id"]]))
        if identifiers != set(expected):
            raise ValueError
        return tuple(samples)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise GatewayError("Bundled sample requests and expected categories are inconsistent") from None


def request_body(sample, model, *, stream=False):
    body = {"model": model, "max_tokens": 32, "messages": [
        {"role": "system", "content": INSTRUCTION}, {"role": "user", "content": sample.text},
    ]}
    if stream:
        body.update(stream=True, stream_options={"include_usage": True})
    return body

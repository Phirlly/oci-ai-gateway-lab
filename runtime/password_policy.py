"""Preflight the pinned default password strength rules without exposing input."""

import re


def valid_presenter_password(value):
    return (
        isinstance(value, str) and 12 <= len(value) <= 256
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        and all(re.search(pattern, value) for pattern in
                (r"[A-Z]", r"[a-z]", r"[0-9]", r"[^a-zA-Z0-9]"))
    )

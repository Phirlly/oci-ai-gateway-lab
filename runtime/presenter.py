"""Create one owned presenter without replaying uncertain invitation or password writes."""

import hashlib
import json
import re
from dataclasses import dataclass

from .gateway_http import GatewayError
from .password_policy import valid_presenter_password


@dataclass(frozen=True, repr=False)
class Presenter:
    deployment_id: str
    email: str
    models: tuple[str, str]

    def __post_init__(self):
        if (not isinstance(self.deployment_id, str)
                or re.fullmatch(r"[a-z][a-z0-9-]{2,39}", self.deployment_id) is None
                or not isinstance(self.email, str) or len(self.email) > 255
                or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email) is None
                or not isinstance(self.models, tuple) or len(self.models) != 2
                or any(not isinstance(model, str)
                       or re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", model) is None for model in self.models)
                or self.models[0] == self.models[1]):
            raise GatewayError("Invalid presenter configuration")

    @property
    def user_id(self):
        return "gateway-presenter-" + hashlib.sha256(self.deployment_id.encode()).hexdigest()[:24]

    @property
    def fingerprint(self):
        identity = [self.deployment_id, self.email, self.models]
        return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def initialize_presenter(api, state, presenter, initial_password):
    """Caller serializes this operation; state writes must be durable before API writes."""
    record = state.load()
    if record is not None and record["phase"] == "complete":
        if not api.user(presenter):
            raise GatewayError("Initialized presenter is missing; explicit recovery is required")
        return
    if not valid_presenter_password(initial_password):
        raise GatewayError("Presenter password does not satisfy the required policy")
    exists = api.user(presenter)
    if record is None:
        if exists:
            raise GatewayError("Presenter exists without deployment ownership evidence")
        state.save("user-started")
        record = state.load()
    if record["phase"] == "user-started":
        if not exists:
            api.create_user(presenter)
        if not api.user(presenter):
            raise GatewayError("Presenter creation could not be verified")
        api.seed_inviter()
        state.save("invitation-started")
        invitation = api.create_invitation(presenter)
        state.save("invitation-created", invitation)
        record = state.load()
    elif not exists:
        raise GatewayError("Owned presenter is missing; explicit recovery is required")
    if record["phase"] == "invitation-started":
        raise GatewayError("Invitation creation outcome is uncertain; explicit recovery is required")
    invitation = record["invitation"]
    if record["phase"] == "invitation-created":
        accepted = api.invitation_accepted(presenter, invitation)
        if not accepted:
            state.save("claim-started", invitation)
            api.claim(presenter, invitation, initial_password)
    # A failed session mint can leave a password set but acceptance rolled back.
    # Never infer that a false acceptance flag authorizes another password write.
    if not api.login(presenter, initial_password):
        if not api.invitation_accepted(presenter, invitation):
            raise GatewayError("Presenter claim is ambiguous; do not reset the account")
    state.save("complete", invitation)

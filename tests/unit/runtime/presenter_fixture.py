"""Small in-memory account API with explicit interruption points."""

from runtime.presenter import Presenter
from runtime.gateway_http import GatewayError

PRESENTER = Presenter("synthetic-demo", "presenter@example.invalid", ("oci-managed", "external-anthropic"))
PASSWORD = "Synthetic9!Password"


class MemoryState:
    def __init__(self):
        self.record = None
        self.saved = []

    def load(self):
        return self.record

    def save(self, phase, invitation=None):
        self.record = {"phase": phase, "invitation": invitation}
        self.saved.append(phase)


class AccountAPI:
    def __init__(self):
        self.user_exists = False
        self.accepted = False
        self.password = None
        self.calls = []
        self.lose_invitation_reply = False
        self.lose_claim_reply = False
        self.rollback_acceptance = False
        self.conflicting_user = False

    def user(self, presenter):
        if self.conflicting_user:
            raise GatewayError("Presenter identity or access does not match")
        return self.user_exists

    def create_user(self, presenter):
        self.calls.append("create-user")
        self.user_exists = True

    def seed_inviter(self):
        self.calls.append("seed-inviter")

    def create_invitation(self, presenter):
        self.calls.append("create-invitation")
        if self.lose_invitation_reply:
            raise GatewayError("Reply unavailable")
        return "synthetic-invitation"

    def invitation_accepted(self, presenter, invitation):
        return self.accepted

    def claim(self, presenter, invitation, password):
        self.calls.append("claim")
        self.password = password
        self.accepted = not self.rollback_acceptance
        if self.lose_claim_reply:
            raise GatewayError("Reply unavailable")

    def login(self, presenter, password):
        self.calls.append("login")
        return self.password == password

"""Pinned LiteLLM account APIs used only by the private bootstrap service."""

import re
from urllib.parse import quote

from .gateway_http import GatewayError, GatewayHTTP, session_key, token_payload


def _result(response, operation):
    if response.status != 200:
        raise GatewayError(f"Presenter {operation} returned HTTP {response.status}")
    value = response.json()
    if not isinstance(value, dict):
        raise GatewayError(f"Presenter {operation} returned invalid data")
    return value


def _invitation(value, presenter, expected=None):
    identifier = value.get("id")
    if (not isinstance(identifier, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier) is None
            or (expected is not None and identifier != expected)
            or value.get("user_id") != presenter.user_id
            or value.get("created_by") != "default_user_id"
            or type(value.get("is_accepted")) is not bool):
        raise GatewayError("Presenter invitation ownership could not be verified")
    return identifier


def presenter_session(value, presenter):
    """Validate the supported UI identity and return its gateway-verified session key."""
    token = value.get("token")
    payload = token_payload(token)
    if (payload.get("user_id") != presenter.user_id or payload.get("user_role") != "internal_user"
            or payload.get("user_email") != presenter.email
            or payload.get("password_reset_required") is not False):
        raise GatewayError("Presenter session identity or access does not match")
    return session_key(token)


class PresenterAPI:
    def __init__(self, admin, public):
        if admin.base_url != public.base_url:
            raise GatewayError("Presenter clients must use the same gateway")
        self.admin, self.public = admin, public

    def user(self, presenter):
        response = self.admin.request("GET", "/user/info?user_id=" + quote(presenter.user_id, safe=""))
        if response.status == 404:
            return False
        value = _result(response, "lookup")
        info = value.get("user_info")
        if (value.get("user_id") != presenter.user_id or not isinstance(info, dict)
                or info.get("user_id") != presenter.user_id or info.get("user_email") != presenter.email
                or info.get("user_role") != "internal_user" or info.get("teams", [])
                or not isinstance(info.get("models"), list)
                or sorted(info["models"]) != sorted(presenter.models)):
            raise GatewayError("Presenter identity or access does not match")
        return True

    def create_user(self, presenter):
        _result(self.admin.request("POST", "/user/new", {
            "user_id": presenter.user_id, "user_email": presenter.email,
            "user_role": "internal_user", "models": list(presenter.models),
            "auto_create_key": False, "send_invite_email": False,
        }), "creation")

    def seed_inviter(self):
        response = self.admin.request("GET", "/user/info?user_id=default_user_id")
        if response.status == 404:
            _result(self.admin.request("POST", "/user/new", {
                "user_id": "default_user_id", "user_role": "proxy_admin",
                "auto_create_key": False, "send_invite_email": False,
            }), "inviter creation")
            response = self.admin.request("GET", "/user/info?user_id=default_user_id")
        info = _result(response, "inviter lookup").get("user_info")
        if not isinstance(info, dict) or info.get("user_id") != "default_user_id" or info.get("user_role") != "proxy_admin":
            raise GatewayError("Presenter inviter identity does not match")

    def create_invitation(self, presenter):
        value = _result(self.admin.request("POST", "/invitation/new", {
            "user_id": presenter.user_id,
        }), "invitation creation")
        identifier = _invitation(value, presenter)
        if value["is_accepted"]:
            raise GatewayError("New presenter invitation was already accepted")
        return identifier

    def invitation_accepted(self, presenter, invitation):
        value = _result(self.admin.request("GET", "/invitation/info?invitation_id=" + quote(invitation, safe="")), "invitation lookup")
        _invitation(value, presenter, invitation)
        return value["is_accepted"]

    def claim(self, presenter, invitation, password):
        value = _result(self.public.request("GET", "/onboarding/get_token?invite_link=" + quote(invitation, safe="")), "onboarding")
        credential = presenter_session(value, presenter)
        client = GatewayHTTP(self.public.base_url, credential, allow_loopback=True)
        _result(client.request("POST", "/onboarding/claim_token", {
            "invitation_link": invitation, "user_id": presenter.user_id, "password": password,
        }), "claim")

    def login(self, presenter, password):
        response = self.public.request("POST", "/v2/login", {"username": presenter.email, "password": password})
        if response.status == 401:
            return False
        presenter_session(_result(response, "login"), presenter)
        return True

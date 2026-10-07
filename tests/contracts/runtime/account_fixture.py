"""Disposable account setup shared only by the runtime contract suites."""

import os
import secrets
from dataclasses import dataclass, field

from .gateway_client import GatewayClient, require_status, token_payload


@dataclass(repr=False)
class Account:
    user_id: str
    email: str
    password: str = field(repr=False)
    invitation: str = field(default="", repr=False)
    onboarding_key: str = field(default="", repr=False)

    def login(self, password=None):
        return GatewayClient().request(
            "POST", "/v2/login",
            {"username": self.email, "password": password or self.password},
        )

    def session(self):
        result = require_status(self.login(), 200, "account login").json()
        return GatewayClient(token_payload(result["token"])["key"])


def admin():
    return GatewayClient(os.environ["GATEWAY_TEST_MASTER_KEY"])


def seed_invitation_creator():
    """The pinned schema requires a user row for the master-key invite creator."""
    require_status(admin().request("POST", "/user/new", {
        "user_id": "default_user_id",
        "user_role": "proxy_admin",
        "auto_create_key": False,
        "send_invite_email": False,
    }), 200, "seed invitation creator in fresh database")


def new_account(models=("local-fixture-a", "local-fixture-b")):
    user_id = "contract-" + secrets.token_hex(8)
    account = Account(
        user_id, user_id + "@example.invalid", "Aa9!" + secrets.token_urlsafe(24)
    )
    require_status(admin().request("POST", "/user/new", {
        "user_id": account.user_id,
        "user_email": account.email,
        "user_role": "internal_user",
        "models": list(models),
        "auto_create_key": False,
        "send_invite_email": False,
    }), 200, "create disposable account")
    invitation = require_status(admin().request(
        "POST", "/invitation/new", {"user_id": account.user_id}
    ), 200, "create invitation").json()
    account.invitation = invitation["id"]
    token = require_status(GatewayClient().request(
        "GET", "/onboarding/get_token?invite_link=" + account.invitation
    ), 200, "get onboarding token").json()["token"]
    account.onboarding_key = token_payload(token)["key"]
    return account


def claim(account):
    return GatewayClient(account.onboarding_key).request(
        "POST", "/onboarding/claim_token", {
            "invitation_link": account.invitation,
            "user_id": account.user_id,
            "password": account.password,
        },
    )


def activated_account(models=("local-fixture-a", "local-fixture-b")):
    account = new_account(models)
    require_status(claim(account), 200, "activate disposable account")
    return account

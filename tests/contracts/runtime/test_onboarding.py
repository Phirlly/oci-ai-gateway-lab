"""Pinned invitation, password and login contracts; no direct database writes."""

import unittest

from .account_fixture import activated_account, admin, claim, new_account
from .gateway_client import token_payload


class OnboardingContracts(unittest.TestCase):
    def test_fresh_claim_allows_login_without_password_reset(self):
        account = new_account()
        self.assertEqual(claim(account).status, 200)
        login = account.login()
        self.assertEqual(login.status, 200)
        self.assertFalse(token_payload(login.json()["token"])["password_reset_required"])
        self.assertTrue(
            "token=" in login.headers.get("Set-Cookie", ""),
            "Login must set the session cookie",
        )

    def test_invitation_replay_cannot_reset_password(self):
        account = activated_account()
        original = account.password
        account.password = "Changed9!" + original
        self.assertEqual(claim(account).status, 401)
        self.assertEqual(account.login(password=original).status, 200)

    def test_duplicate_user_creation_is_rejected(self):
        account = activated_account()
        response = admin().request("POST", "/user/new", {
            "user_id": account.user_id,
            "user_email": account.email,
            "auto_create_key": False,
            "send_invite_email": False,
        })
        self.assertEqual(response.status, 409)
        self.assertEqual(account.login().status, 200)

    def test_wrong_password_is_rejected(self):
        account = activated_account()
        self.assertEqual(account.login(password="Incorrect9!Password").status, 401)

    def test_user_creation_rejects_direct_password_input(self):
        response = admin().request("POST", "/user/new", {
            "user_id": "direct-password-contract",
            "password": "Fixture9!Password",
            "auto_create_key": False,
        })
        self.assertEqual(response.status, 422)

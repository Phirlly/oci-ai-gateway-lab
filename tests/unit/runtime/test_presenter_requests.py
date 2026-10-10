"""Pinned presenter API requests and identity validation without containers."""

import json
import unittest

from runtime.gateway_http import GatewayError, Response
from runtime.presenter_api import PresenterAPI
from .presenter_fixture import PRESENTER


class Client:
    base_url = "http://127.0.0.1:4000"

    def __init__(self):
        self.calls, self.responses = [], []

    def request(self, method, path, data=None, **kwargs):
        self.calls.append((method, path, data))
        status, value = self.responses.pop(0)
        return Response(status, json.dumps(value).encode(), {})


class PresenterRequestTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.public = Client(), Client()
        self.api = PresenterAPI(self.admin, self.public)

    def test_user_creation_does_not_generate_keys_send_email_or_set_password(self):
        self.admin.responses = [(200, {})]
        self.api.create_user(PRESENTER)
        self.assertEqual(self.admin.calls, [("POST", "/user/new", {
            "user_id": PRESENTER.user_id, "user_email": PRESENTER.email,
            "user_role": "internal_user", "models": list(PRESENTER.models),
            "auto_create_key": False, "send_invite_email": False,
        })])

    def test_user_lookup_requires_exact_role_email_and_models(self):
        info = {"user_id": PRESENTER.user_id, "user_email": PRESENTER.email,
                "user_role": "internal_user", "models": list(PRESENTER.models)}
        self.admin.responses = [(200, {"user_id": PRESENTER.user_id, "user_info": info})]
        self.assertTrue(self.api.user(PRESENTER))
        for field, value in (("user_role", "proxy_admin"), ("models", ["all-proxy-models"]),
                             ("user_email", "other@example.invalid")):
            self.admin.responses = [(200, {"user_id": PRESENTER.user_id, "user_info": info | {field: value}})]
            with self.subTest(field=field), self.assertRaises(GatewayError):
                self.api.user(PRESENTER)

    def test_missing_user_is_distinct_from_service_failure(self):
        self.admin.responses = [(404, {}), (503, {"secret": "do-not-echo"})]
        self.assertFalse(self.api.user(PRESENTER))
        with self.assertRaises(GatewayError) as raised:
            self.api.user(PRESENTER)
        self.assertNotIn("do-not-echo", str(raised.exception))

    def test_invitation_lookup_rejects_a_different_user(self):
        self.admin.responses = [(200, {"id": "invitation", "user_id": "other",
                                      "created_by": "default_user_id", "is_accepted": False})]
        with self.assertRaises(GatewayError):
            self.api.invitation_accepted(PRESENTER, "invitation")

    def test_login_401_is_false_but_a_service_failure_is_not_wrong_password(self):
        self.public.responses = [(401, {}), (500, {"secret": "do-not-echo"})]
        self.assertFalse(self.api.login(PRESENTER, "synthetic-password"))
        with self.assertRaises(GatewayError):
            self.api.login(PRESENTER, "synthetic-password")

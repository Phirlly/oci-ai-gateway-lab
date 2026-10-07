"""Compare's session API: discover, infer, stream and enforce model/role limits."""

import json
import unittest

from .account_fixture import activated_account, admin


class SessionAccessContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.account = activated_account()
        cls.session = cls.account.session()

    def test_session_discovers_two_allowed_models(self):
        response = self.session.request("GET", "/model_group/info")
        self.assertEqual(response.status, 200)
        names = {model["model_group"] for model in response.json()["data"]}
        self.assertEqual(names, {"local-fixture-a", "local-fixture-b"})

    def test_both_mocked_completions_use_session_credentials(self):
        for model, expected in (("local-fixture-a", "fixture A"),
                                ("local-fixture-b", "fixture B")):
            with self.subTest(model=model):
                response = self.session.request("POST", "/chat/completions", {
                    "model": model,
                    "messages": [{"role": "user", "content": "Local contract only"}],
                    "max_tokens": 16,
                })
                self.assertEqual(response.status, 200)
                self.assertEqual(response.json()["choices"][0]["message"]["content"], expected)

    def test_stream_completes_with_fixture_text_and_done_marker(self):
        response = self.session.request("POST", "/chat/completions", {
            "model": "local-fixture-a",
            "messages": [{"role": "user", "content": "Local contract only"}],
            "stream": True,
            "max_tokens": 16,
        })
        self.assertEqual(response.status, 200)
        events = [line[6:] for line in response.body.decode().splitlines()
                  if line.startswith("data: ")]
        self.assertEqual(events[-1], "[DONE]")
        chunks = [json.loads(event) for event in events[:-1]]
        content = "".join(
            chunk["choices"][0]["delta"].get("content") or ""
            for chunk in chunks if chunk.get("choices")
        )
        self.assertEqual(content, "fixture A")

    def test_configured_but_ungranted_model_is_denied(self):
        restricted = activated_account(models=("local-fixture-a",)).session()
        response = restricted.request("POST", "/chat/completions", {
            "model": "local-fixture-b",
            "messages": [{"role": "user", "content": "Must be denied"}],
        })
        self.assertEqual(response.status, 403)

    def test_internal_session_cannot_create_proxy_admin(self):
        self.assertEqual(self.session.request("GET", "/model_group/info").status, 200)
        response = self.session.request("POST", "/user/new", {
            "user_id": "forbidden-admin",
            "user_role": "proxy_admin",
            "auto_create_key": False,
            "send_invite_email": False,
        })
        # The pinned route guard denies before the user/new handler (HTTP 401).
        self.assertEqual(response.status, 401)
        self.assertTrue(
            "Only proxy admin" in response.json()["error"]["message"],
            "Denial must identify the administrative route restriction",
        )
        self.assertEqual(
            admin().request("GET", "/user/info?user_id=forbidden-admin").status, 404
        )

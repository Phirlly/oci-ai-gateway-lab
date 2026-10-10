"""Ready requires login, restricted access and every attributed sample/stream."""

import base64
import json
import unittest
from unittest.mock import Mock, patch

from demo.verification import check_health, verify_demo
from runtime.gateway_http import GatewayError, Response
from runtime.presenter import Presenter

PRESENTER = Presenter("synthetic-demo", "presenter@example.invalid", ("oci-managed", "external-anthropic"))


def reply(value, status=200, model=None):
    return Response(status, json.dumps(value).encode(), {"x-litellm-model-id": model})


class VerificationTests(unittest.TestCase):
    def setUp(self):
        payload = {"user_id": PRESENTER.user_id, "user_email": PRESENTER.email, "user_role": "internal_user",
                   "password_reset_required": False, "key": "synthetic-session"}
        token = "header." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + ".signature"
        self.public = Mock(base_url="https://8.8.4.4")
        self.public.request.side_effect = [reply({}), reply({"db": "connected"}), reply({"token": token})]
        self.session = Mock()
        self.session.request.side_effect = self.session_reply
        self.enterContext(patch("demo.verification.GatewayHTTP", return_value=self.session))
        self.mode = "valid"

    def session_reply(self, method, path, data=None, **kwargs):
        if path == "/model_group/info":
            return reply({"data": [{"model_group": model} for model in PRESENTER.models]})
        if path == "/user/list":
            return reply({}, 200 if self.mode == "admin" else 403)
        model = data["model"]
        if self.mode == "provider-error":
            return Response(429, json.dumps({'error': {'type': 'throttling_error',
                                                      'message': 'private provider error'}}).encode(),
                            {'retry-after': '3', 'llm_provider-retry-after': '8'})
        text = data["messages"][1]["content"]
        answer = "BILLING" if "invoice" in text else "ACCESS" if "locked" in text else "TECHNICAL"
        if self.mode == "wrong-answer":
            answer = "ACCESS"
        if data.get("stream"):
            chunk = {"choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": "stop"}]}
            return Response(200, ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode(), {"x-litellm-model-id": model})
        return reply({"choices": [{"index": 0, "message": {"content": answer}, "finish_reason": "stop"}]}, model=model)

    def test_success_uses_eight_single_attempt_samples(self):
        report = verify_demo(self.public, PRESENTER, "Synthetic9!Password")
        self.assertTrue(report["ready"])
        self.assertEqual(len(report["samples"]), 8)
        calls = [call for call in self.session.request.call_args_list if call.args[1] == "/chat/completions"]
        self.assertEqual(len(calls), 8)
        self.assertTrue(all(0 < call.kwargs["timeout"] <= 90 for call in calls))
        self.assertTrue(all(row['attempts'] == 1 and row['retry_wait_seconds'] == 0 for row in report['samples']))
        self.assertTrue(all(row["cost_usd"] is None for row in report["samples"]))

    def test_wrong_classification_is_distinct_from_transport_failure(self):
        self.mode = "wrong-answer"
        report = verify_demo(self.public, PRESENTER, "Synthetic9!Password")
        self.assertFalse(report["ready"])
        self.assertIn("FAIL", {row["status"] for row in report["samples"]})
        self.assertNotIn("ERROR", {row["status"] for row in report["samples"]})

    @patch('demo.verification.time.sleep')
    def test_persistent_rate_limits_stay_sanitized_and_stop_after_24_attempts(self, sleep):
        self.mode = "provider-error"
        report = verify_demo(self.public, PRESENTER, "Synthetic9!Password")
        self.assertFalse(report["ready"])
        self.assertEqual({row["status"] for row in report["samples"]}, {"ERROR"})
        self.assertNotIn("private provider error", json.dumps(report))
        self.assertTrue(all(row['error_details'] == {'type': 'throttling_error',
                                                     'retry_after_seconds': 3,
                                                     'provider_retry_after_seconds': 8}
                            for row in report['samples']))
        self.assertEqual(len(self.session.request.call_args_list), 26)
        self.assertTrue(all(row['attempts'] == 3 for row in report['samples']))
        self.assertEqual(sleep.call_count, 16)

    def test_administrative_access_stops_before_inference(self):
        self.mode = "admin"
        with self.assertRaises(GatewayError):
            verify_demo(self.public, PRESENTER, "Synthetic9!Password")
        self.assertEqual(len(self.session.request.call_args_list), 2)

    def test_status_health_makes_no_model_or_login_request(self):
        check_health(self.public)
        self.assertEqual([call.args[1] for call in self.public.request.call_args_list],
                         ["/health/liveliness", "/health/readiness"])

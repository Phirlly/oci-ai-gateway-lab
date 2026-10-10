"""Attribution, complete responses and bounded streaming success."""

import json
import unittest

from demo.results import completion, streamed_completion
from runtime.gateway_http import GatewayError, Response


def response(value, *, model="oci-managed", status=200):
    body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
    return Response(status, body, {"x-litellm-model-id": model})


class ResultTests(unittest.TestCase):
    def test_complete_attributed_result_preserves_reported_usage(self):
        body = {"choices": [{"index": 0, "finish_reason": "stop", "message": {"content": "BILLING"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}}
        self.assertEqual(completion(response(body), "oci-managed"), ("BILLING", body["usage"]))

    def test_response_alias_does_not_replace_route_attribution(self):
        body = {"model": "oci-managed", "choices": [{"index": 0, "finish_reason": "stop", "message": {"content": "BILLING"}}]}
        for model in ("wrong-route", None):
            with self.subTest(model=model), self.assertRaises(GatewayError):
                completion(response(body, model=model), "oci-managed")

    def test_truncated_empty_or_structurally_invalid_output_fails(self):
        for choice in ({"finish_reason": "length", "message": {"content": "BILLING"}},
                       {"finish_reason": "stop", "message": {"content": ""}},
                       {"finish_reason": "stop", "message": {"content": ["BILLING"]}}):
            with self.subTest(choice=choice), self.assertRaises(GatewayError):
                completion(response({"choices": [choice]}), "oci-managed")

    def test_provider_error_omits_raw_content(self):
        with self.assertRaises(GatewayError) as error:
            completion(response({"error": "secret upstream message"}, status=429), "oci-managed")
        self.assertIn("429", str(error.exception))
        self.assertNotIn("secret", str(error.exception))

    def test_stream_requires_content_finish_and_terminal_done(self):
        chunks = [{"choices": [{"index": 0, "delta": {"content": "BILL"}, "finish_reason": None}]},
                  {"choices": [{"index": 0, "delta": {"content": "ING"}, "finish_reason": "stop"}]}]
        body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
        self.assertEqual(streamed_completion(response(body + "data: [DONE]\n\n"), "oci-managed"), ("BILLING", None))
        for invalid in (body, "data: [DONE]\n\n", body + 'data: {"error":"secret"}\n\ndata: [DONE]\n\n',
                        body + 'data: [DONE]\n\ndata: {}\n\n'):
            with self.subTest(invalid=invalid[:20]), self.assertRaises(GatewayError):
                streamed_completion(response(invalid), "oci-managed")

    def test_malformed_usage_is_not_presented_as_verified_measurement(self):
        body = {"choices": [{"index": 0, "finish_reason": "stop", "message": {"content": "ACCESS"}}],
                "usage": {"prompt_tokens": "unavailable", "completion_tokens": -1}}
        self.assertEqual(completion(response(body), "oci-managed"), ("ACCESS", None))

    def test_complete_stream_accepts_standard_and_pinned_usage_only_tail(self):
        usage = {'prompt_tokens': 20, 'completion_tokens': 3, 'total_tokens': 23}
        for choices in ([], [{'index': 0, 'delta': {}}]):
            with self.subTest(choices=choices):
                chunks = [{'choices': [{'index': 0, 'delta': {'content': 'BILLING'}, 'finish_reason': 'stop'}]},
                          {'choices': choices, 'usage': usage}]
                body = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
                self.assertEqual(streamed_completion(response(body), 'oci-managed'), ('BILLING', usage))

    def test_usage_tail_cannot_hide_content_second_finish_or_invalid_usage(self):
        usage = {'prompt_tokens': 20, 'completion_tokens': 3, 'total_tokens': 23}
        tails = [({'index': 0, 'delta': {'content': 'EXTRA'}}, usage),
                 ({'index': 0, 'delta': {}, 'finish_reason': 'stop'}, usage),
                 ({'index': 1, 'delta': {}}, usage), ({'delta': {}}, usage),
                 ({'index': 0, 'delta': {}}, {'total_tokens': 'invalid'}),
                 ({'index': 0, 'delta': {}}, None)]
        for choice, tail_usage in tails:
            with self.subTest(choice=choice, usage=tail_usage), self.assertRaises(GatewayError):
                chunks = [{'choices': [{'index': 0, 'delta': {'content': 'BILLING'}, 'finish_reason': 'stop'}]},
                          {'choices': [choice], 'usage': tail_usage}]
                body = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
                streamed_completion(response(body), 'oci-managed')

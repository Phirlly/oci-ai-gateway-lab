"""Rate-limit metadata stays bounded, ambiguous and free of raw content."""

from email.message import Message
import json
import unittest

from demo.results import completion, streamed_completion
from runtime.gateway_http import GatewayError, Response


def response(body, headers=None, status=429):
    if not isinstance(body, bytes):
        body = json.dumps(body).encode()
    return Response(status, body, {} if headers is None else headers)


class ResponseErrorTests(unittest.TestCase):
    def details(self, reply, parser=completion):
        with self.assertRaises(GatewayError) as error:
            parser(reply, 'oci-managed')
        self.assertEqual(str(error.exception), f'Model route returned HTTP {reply.status}')
        return error.exception.details

    def test_both_paths_keep_only_known_type_and_separate_retry_guidance(self):
        headers = {'Retry-After': '5', 'LLM_PROVIDER-Retry-After': '12', 'private-header': 'sentinel'}
        for kind in ('all_deployments_in_cooldown', 'rate_limit_error', 'throttling_error'):
            for parser in (completion, streamed_completion):
                with self.subTest(kind=kind, parser=parser.__name__):
                    result = self.details(response({'error': {'type': kind, 'message': 'private-sentinel'}}, headers), parser)
                    self.assertEqual(result, {'type': kind, 'retry_after_seconds': 5,
                                              'provider_retry_after_seconds': 12})
                    self.assertNotIn('sentinel', json.dumps(result))

    def test_unsupported_types_and_structures_remain_unknown(self):
        for value in ({'error': {'type': 'private-sentinel'}}, {'error': {'type': ['throttling_error']}},
                      {'error': 'throttling_error'}, [], None):
            with self.subTest(value=value):
                self.assertEqual(self.details(response(value))['type'], 'UNKNOWN')

    def test_malformed_duplicate_oversized_and_deep_json_cannot_supply_type(self):
        bodies = [b'not-json', b'\xff', b'{"error":{"type":"rate_limit_error","type":"throttling_error"}}',
                  b'{"error":{"type":"throttling_error"},"other":NaN}',
                  json.dumps({'error': {'type': 'throttling_error'}, 'padding': 'x' * 16384}).encode(),
                  b'{"error":{"type":"throttling_error"},"nested":' + b'[' * 20 + b'0' + b']' * 20 + b'}']
        for index, body in enumerate(bodies):
            with self.subTest(case=index):
                self.assertEqual(self.details(response(body))['type'], 'UNKNOWN')

    def test_only_bounded_ascii_integer_retry_values_are_reported(self):
        for value in ('-1', '1.5', '3601', '99999', 'NaN', '1, 2', ' 1', '\u0661', 'Fri, 31 Dec 1999 23:59:59 GMT'):
            with self.subTest(value=value):
                details = self.details(response({}, {'retry-after': value, 'llm_provider-retry-after': value}))
                self.assertIsNone(details['retry_after_seconds'])
                self.assertIsNone(details['provider_retry_after_seconds'])
        for value in ('0', '3600'):
            with self.subTest(value=value):
                self.assertEqual(self.details(response({}, {'retry-after': value}))['retry_after_seconds'], int(value))

    def test_duplicate_http_message_headers_are_not_treated_as_one_value(self):
        headers = Message()
        headers['Retry-After'] = '5'
        headers['retry-after'] = '5'
        headers['llm_provider-retry-after'] = '7'
        result = self.details(response({}, headers))
        self.assertIsNone(result['retry_after_seconds'])
        self.assertEqual(result['provider_retry_after_seconds'], 7)

    def test_non429_failure_does_not_report_body_or_headers(self):
        for status in (401, 403, 500, 503):
            with self.subTest(status=status):
                self.assertIsNone(self.details(response({'error': {'type': 'throttling_error'}},
                                                       {'retry-after': '5'}, status)))

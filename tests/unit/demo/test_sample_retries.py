"""Explicit 429 retries share one deadline and expose every model attempt."""

from email.message import Message
import json
import unittest
from unittest.mock import Mock, patch

from demo.samples import Sample
from demo.verification import _sample
from runtime.gateway_http import GatewayError, Response

MODEL = 'oci-managed'
SAMPLE = Sample('invoice', 'An incorrect invoice', 'BILLING')


def limited(headers=None, status=429):
    return Response(status, b'{"error":{"type":"throttling_error"}}', headers or {})


def answered(answer='BILLING'):
    body = {'choices': [{'index': 0, 'message': {'content': answer}, 'finish_reason': 'stop'}]}
    return Response(200, json.dumps(body).encode(), {'x-litellm-model-id': MODEL})


class Clock:
    def __init__(self):
        self.now, self.waits, self.extra_sleep = 0, [], 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds + self.extra_sleep


class SampleRetryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.enterContext(patch('demo.verification.time', self.clock))
        self.client = Mock()

    def run_sample(self, responses, *, stream=False):
        self.client.request.side_effect = responses
        return _sample(self.client, SAMPLE, MODEL, stream)

    def test_rejected_then_successful_request_reports_both_attempts_and_wait(self):
        result = self.run_sample([limited(), answered()])
        self.assertEqual((result['status'], result['attempts'], result['retry_wait_seconds']), ('PASS', 2, 2))
        self.assertEqual(result['seconds'], 2)
        self.assertIsNone(result['error'])
        self.assertIsNone(result['error_details'])
        self.assertEqual([call.kwargs['timeout'] for call in self.client.request.call_args_list], [90, 88])

    def test_three_rejections_exhaust_attempts_with_two_bounded_waits(self):
        result = self.run_sample([limited()] * 3)
        self.assertEqual((result['status'], result['attempts'], result['retry_wait_seconds']), ('ERROR', 3, 6))
        self.assertEqual(self.clock.waits, [2, 4])
        self.assertEqual(result['error'], 'Model route returned HTTP 429')
        self.assertEqual(self.client.request.call_count, 3)

    def test_largest_guidance_is_honored_with_backoff_as_the_minimum(self):
        result = self.run_sample([limited({'Retry-After': '3', 'llm_provider-retry-after': '8'}),
                                  limited({'Retry-After': '0'}), answered()])
        self.assertEqual((result['status'], result['attempts'], result['retry_wait_seconds']), ('PASS', 3, 12))
        self.assertEqual(self.clock.waits, [8, 4])

    def test_unsupported_duplicate_or_long_guidance_stops_without_shortening_it(self):
        duplicate = Message()
        duplicate['Retry-After'] = '2'
        duplicate['Retry-After'] = '2'
        for headers in ({'Retry-After': '31'}, {'llm_provider-retry-after': '3601'},
                        {'Retry-After': 'Fri, 31 Dec 1999 23:59:59 GMT'},
                        {'Retry-After': 'invalid', 'llm_provider-retry-after': '2'}, duplicate):
            with self.subTest(headers=headers):
                result = self.run_sample([limited(headers)])
                self.assertEqual((result['status'], result['attempts']), ('ERROR', 1))
                self.assertEqual(result['retry_wait_seconds'], 0)
        self.assertEqual(self.clock.waits, [])

    def test_no_wait_or_retry_when_request_uses_remaining_budget(self):
        def slow(*args, **kwargs):
            self.clock.now += 89
            return limited()

        result = self.run_sample(slow)
        self.assertEqual((result['attempts'], result['seconds']), (1, 89))
        self.assertEqual(self.clock.waits, [])

    def test_wait_that_overshoots_deadline_cannot_start_another_request(self):
        self.clock.extra_sleep = 90
        result = self.run_sample([limited(), answered()])
        self.assertEqual(self.client.request.call_count, 1)
        self.assertEqual((result['status'], result['attempts']), ('ERROR', 1))

    def test_request_elapsed_time_reduces_next_http_deadline(self):
        def timed(*args, **kwargs):
            self.clock.now += 10
            return limited() if self.client.request.call_count == 1 else answered()

        result = self.run_sample(timed)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual([call.kwargs['timeout'] for call in self.client.request.call_args_list], [90, 78])
        self.assertEqual(result['seconds'], 22)

    def test_timeouts_connection_failures_other_statuses_and_invalid_output_never_retry(self):
        for response in (TimeoutError(), GatewayError('Gateway connection failed'), limited(status=503),
                         limited(status=401), Response(200, b'{}', {'x-litellm-model-id': MODEL}), answered('UNKNOWN')):
            with self.subTest(response=type(response).__name__):
                result = self.run_sample([response])
                self.assertEqual(result['attempts'], 1)
                self.assertNotEqual(result['status'], 'PASS')
                self.assertEqual(result['retry_wait_seconds'], 0)
        self.assertEqual(self.clock.waits, [])

    def test_truncated_stream_is_not_replayed(self):
        result = self.run_sample([Response(200, b'data: {}\n\n', {'x-litellm-model-id': MODEL})], stream=True)
        self.assertEqual((result['status'], result['attempts']), ('ERROR', 1))
        self.assertEqual(result['error'], 'Model stream is incomplete or invalid')

    def test_later_timeout_or_wrong_answer_clears_stale_429_details(self):
        for response in (TimeoutError(), answered('ACCESS')):
            with self.subTest(response=type(response).__name__):
                result = self.run_sample([limited(), response])
                self.assertEqual(result['attempts'], 2)
                self.assertIsNone(result['error_details'])
                if isinstance(response, TimeoutError):
                    self.assertEqual(result['status'], 'ERROR')
                    self.assertEqual(result['error'], 'Model request timed out; no further retry was made')
                else:
                    self.assertEqual(result['status'], 'FAIL')
                    self.assertIsNone(result['error'])

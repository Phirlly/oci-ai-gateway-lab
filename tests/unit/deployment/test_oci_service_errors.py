"""Service diagnostics expose fixed status/code summaries, never arbitrary data."""

import json
import unittest

from deployment.oci_service_errors import service_error_summary


def response(**changes):
    value = {'status': 409, 'code': 'Conflict', 'message': 'secret-sentinel',
             'request_endpoint': 'https://private.example/secret-sentinel',
             'opc-request-id': 'private-request-sentinel'}
    return 'ServiceError:\n' + json.dumps(value | changes)


class OCIServiceErrorTests(unittest.TestCase):
    def test_known_service_categories_exclude_all_other_fields(self):
        for status, code in ((409, 'Conflict'), (409, 'IncorrectState'),
                             (400, 'InvalidParameter'), (412, 'NoEtagMatch'),
                             (404, 'NotAuthorizedOrNotFound')):
            with self.subTest(status=status, code=code):
                self.assertEqual(service_error_summary(response(status=status, code=code)),
                                 f'OCI service response: HTTP {status}; code {code}.')

    def test_unknown_nonstring_or_mismatched_code_is_withheld(self):
        for code in ('secret-sentinel', 'NoEtagMatch', None, [], {'secret': 'sentinel'}, 123):
            with self.subTest(code=code):
                self.assertEqual(service_error_summary(response(code=code)),
                                 'OCI service response: HTTP 409; code unavailable.')

    def test_invalid_or_nonerror_status_produces_no_diagnostic(self):
        for status in (True, False, '409', 409.0, None, [], 200, 399, 600):
            with self.subTest(status=status):
                self.assertIsNone(service_error_summary(response(status=status)))

    def test_nonservice_contaminated_or_malformed_documents_are_rejected(self):
        for content in (None, b'error', '', 'secret-sentinel', response().replace('ServiceError:', 'ClientError:'),
                        'debug-sentinel\n' + response(), response() + '\nsecret-sentinel',
                        response() + '{}', 'ServiceError:\n[]', 'ServiceError:\nnull',
                        'ServiceError:\n{"status":409,'):
            with self.subTest(content=content):
                self.assertIsNone(service_error_summary(content))

    def test_duplicate_nonfinite_and_excessively_nested_fields_are_rejected(self):
        for body in ('{"status":409,"status":400}',
                     '{"status":409,"extra":{"field":1,"field":2}}',
                     '{"status":409,"extra":NaN}', '{"status":409,"extra":Infinity}',
                     '{"status":409,"extra":' + '[' * 1500 + '0' + ']' * 1500 + '}'):
            with self.subTest(body=body[:80]):
                self.assertIsNone(service_error_summary('ServiceError:\n' + body))

    def test_byte_bound_and_invalid_unicode_are_rejected(self):
        for content in (response(message='x' * 16_384),
                        response(message='é' * 9000).replace('\\u00e9', 'é'),
                        response() + '\ud800'):
            self.assertIsNone(service_error_summary(content))

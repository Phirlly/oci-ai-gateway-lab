"""Apply history permits one original and one same-input recovery attempt."""

import unittest
from dataclasses import replace

from deployment.apply_attempts import latest_applies
from deployment.credential_errors import DeliveryError
from deployment.submission_records import Intent


class ApplyAttemptTests(unittest.TestCase):
    def setUp(self):
        self.first = Intent('c' * 64, 'd' * 64, 'apply', 'a' * 32, 'b' * 64, 'e' * 64)
        self.retry = replace(self.first, operation_id='f' * 32, retry_of=self.first.operation_id)

    def test_original_payload_remains_exactly_version_one(self):
        self.assertEqual(self.first.payload(), {
            'version': 1, 'controller_id': 'c' * 64, 'target_hash': 'd' * 64,
            'kind': 'apply', 'operation_id': 'a' * 32,
            'request_hash': 'b' * 64, 'package_hash': 'e' * 64,
        })
        self.assertEqual(Intent.parse(self.first.payload()), self.first)

    def test_retry_payload_round_trips_with_explicit_parent(self):
        payload = self.retry.payload()
        self.assertEqual(payload['version'], 2)
        self.assertEqual(payload['retry_of'], self.first.operation_id)
        self.assertEqual(Intent.parse(payload), self.retry)

    def test_invalid_retry_schema_is_rejected(self):
        payload = self.retry.payload()
        changes = ({'version': 1}, {'version': True}, {'retry_of': None},
                   {'retry_of': ''}, {'retry_of': self.retry.operation_id},
                   {'kind': 'destroy'}, {'kind': 'create-stack'}, {'extra': 'unknown'})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DeliveryError):
                Intent.parse(payload | change)
        with self.assertRaises(DeliveryError):
            Intent.parse(self.first.payload() | {'version': 2})

    def test_retry_is_selected_regardless_of_listing_order(self):
        for rows in ([self.first, self.retry], [self.retry, self.first]):
            with self.subTest(first=rows[0].operation_id):
                self.assertEqual(latest_applies(rows), {self.first.request_hash: self.retry})
        self.assertEqual(latest_applies([self.first]), {self.first.request_hash: self.first})

    def test_orphan_duplicate_and_recursive_attempts_are_rejected(self):
        invalid = (
            [self.retry],
            [self.first, replace(self.first, operation_id='0' * 32)],
            [self.first, self.retry, replace(self.retry, operation_id='0' * 32)],
            [self.first, replace(self.retry, retry_of='0' * 32)],
            [self.first, self.retry, replace(self.retry, operation_id='0' * 32,
                                            retry_of=self.retry.operation_id)],
        )
        for index, rows in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(DeliveryError):
                latest_applies(rows)

    def test_parent_cannot_cross_controller_target_request_or_package(self):
        for field in ('controller_id', 'target_hash', 'request_hash', 'package_hash'):
            with self.subTest(field=field), self.assertRaises(DeliveryError):
                latest_applies([self.first, replace(self.retry, **{field: '0' * 64})])

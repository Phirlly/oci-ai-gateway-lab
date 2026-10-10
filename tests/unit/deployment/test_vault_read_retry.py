"""Read verification has finite attempts; writes and semantic failures do not retry."""

import traceback
import unittest
from unittest.mock import Mock, patch

from deployment.credential_errors import DeliveryError, MutationUncertain, VaultReadError
from deployment.vault_cli import VaultCLI


class VaultReadRetryTests(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(VaultCLI)
        self.sleep = patch("time.sleep").start()
        self.addCleanup(patch.stopall)

    def test_each_read_keeps_its_exact_selector_when_retrying(self):
        operations = (
            lambda: self.client.metadata("secret"),
            lambda: self.client.versions("secret"),
            lambda: self.client.bundle("secret", version_name="intent-fixed"),
            lambda: self.client.bundle("secret", version_number=3),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                self.sleep.reset_mock()
                self.client.request = Mock(side_effect=[VaultReadError("unavailable")] * 2 + [{"data": []}])
                self.assertEqual(operation(), {"data": []})
                calls = self.client.request.call_args_list
                self.assertEqual(len(calls), 3)
                self.assertTrue(all(call == calls[0] for call in calls))
                self.assertFalse(calls[0].kwargs["mutation"])
                self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4])

    def test_exhaustion_is_bounded_and_sanitized(self):
        self.client.request = Mock(side_effect=VaultReadError("synthetic-secret-sentinel"))
        with self.assertRaises(VaultReadError) as error:
            self.client.bundle("secret", version_name="intent-fixed")
        self.assertEqual(self.client.request.call_count, 6)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4, 8, 16, 30])
        self.assertNotIn("sentinel", "".join(traceback.format_exception(error.exception)))

    def test_stage_and_promote_never_retry_uncertain_mutations(self):
        for operation in (
            lambda: self.client.stage("secret", "intent-fixed", b"secret", "etag"),
            lambda: self.client.promote("secret", 3, "etag"),
        ):
            with self.subTest(operation=operation):
                self.client.request = Mock(side_effect=MutationUncertain("uncertain"))
                with self.assertRaises(MutationUncertain):
                    operation()
                self.assertEqual(self.client.request.call_count, 1)
        self.sleep.assert_not_called()

    def test_semantic_failure_is_not_a_transport_retry(self):
        self.client.request = Mock(side_effect=DeliveryError("ownership conflict"))
        with self.assertRaisesRegex(DeliveryError, "ownership"):
            self.client.metadata("secret")
        self.assertEqual(self.client.request.call_count, 1)
        self.sleep.assert_not_called()

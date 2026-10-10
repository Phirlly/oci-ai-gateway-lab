"""Presenter verification through both pinned provider adapters, including zero retries."""

import secrets
import tempfile
import unittest

from demo.samples import Sample, request_body
from demo.results import completion
from demo.verification import verify_demo
from runtime.gateway_http import GatewayError
from runtime.presenter import Presenter, initialize_presenter
from runtime.presenter_api import PresenterAPI
from runtime.presenter_state import PresenterState
from tests.contracts.runtime.account_fixture import Account, admin
from tests.contracts.runtime.gateway_client import GatewayClient

STACK = None


class AdapterContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if STACK is None:
            raise RuntimeError("Use python3.12 -m tests.contracts.demo")
        identifier = "adapter-" + secrets.token_hex(6)
        cls.presenter = Presenter(identifier, identifier + "@example.invalid", ("oci-managed", "external-anthropic"))
        cls.password = "Aa9!" + secrets.token_urlsafe(24)
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        initialize_presenter(PresenterAPI(admin(), GatewayClient()), PresenterState(directory.name, cls.presenter),
                             cls.presenter, cls.password)

    def test_both_protocols_run_all_samples_and_stream_with_attribution(self):
        before = STACK.counts()
        report = verify_demo(GatewayClient(), self.presenter, self.password)
        self.assertTrue(report["ready"], report)
        self.assertEqual({row["status"] for row in report["samples"]}, {"PASS"})
        self.assertTrue(all(row["usage"] is not None for row in report["samples"]))
        after = STACK.counts()
        self.assertEqual({name: after[name] - before[name] for name in after}, {"oci": 4, "anthropic": 4})

    def test_each_provider_rate_limit_has_no_implicit_adapter_retry(self):
        session = Account(self.presenter.user_id, self.presenter.email, self.password).session()
        before = STACK.counts()
        for model in self.presenter.models:
            with self.subTest(model=model):
                response = session.request("POST", "/chat/completions",
                                           request_body(Sample("rate-limit", "fixture-rate-limit", "TECHNICAL"), model), timeout=30)
                self.assertEqual(response.status, 429)
                with self.assertRaises(GatewayError) as error:
                    completion(response, model)
                self.assertEqual(error.exception.details['type'], 'throttling_error')
                self.assertEqual(error.exception.details['provider_retry_after_seconds'], 7)
                self.assertIsNone(error.exception.details['retry_after_seconds'])
        after = STACK.counts()
        self.assertEqual({name: after[name] - before[name] for name in after}, {"oci": 1, "anthropic": 1})

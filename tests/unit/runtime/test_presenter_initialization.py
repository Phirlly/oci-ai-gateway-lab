"""Presenter creation is owned, bounded and preserves completed accounts."""

import unittest

from runtime.gateway_http import GatewayError
from runtime.presenter import Presenter, initialize_presenter
from .presenter_fixture import AccountAPI, MemoryState, PASSWORD, PRESENTER


class PresenterInitializationTests(unittest.TestCase):
    def test_deployment_id_accepts_the_settings_contract_maximum_length(self):
        presenter = Presenter("a" * 40, PRESENTER.email, PRESENTER.models)
        self.assertTrue(presenter.user_id.startswith("gateway-presenter-"))

    def setUp(self):
        self.api, self.state = AccountAPI(), MemoryState()

    def initialize(self):
        return initialize_presenter(self.api, self.state, PRESENTER, PASSWORD)

    def test_fresh_account_is_claimed_and_verified_once(self):
        self.initialize()
        self.assertEqual(self.state.record["phase"], "complete")
        self.assertEqual(self.api.password, PASSWORD)
        self.assertEqual(self.api.calls.count("create-user"), 1)
        self.assertEqual(self.api.calls.count("create-invitation"), 1)
        self.assertEqual(self.api.calls.count("claim"), 1)

    def test_completed_rerun_preserves_a_changed_password(self):
        self.initialize()
        self.api.password = "Changed9!Password"
        self.api.calls.clear()
        self.initialize()
        self.assertEqual(self.api.password, "Changed9!Password")
        self.assertEqual(self.api.calls, [])

    def test_existing_account_without_ownership_record_is_not_modified(self):
        self.api.user_exists = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.api.calls, [])
        self.assertIsNone(self.state.record)

    def test_unexpected_role_or_models_blocks_initialization(self):
        self.api.conflicting_user = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.api.calls, [])

    def test_invalid_password_fails_before_any_account_write(self):
        with self.assertRaises(GatewayError):
            initialize_presenter(self.api, self.state, PRESENTER, "weak")
        self.assertIsNone(self.state.record)
        self.assertEqual(self.api.calls, [])

"""Owned presenter initialization and uncertain writes against the pinned gateway."""

import secrets
import tempfile
import unittest
from unittest.mock import patch

from runtime.gateway_http import GatewayError
from runtime.presenter import Presenter, initialize_presenter
from runtime.presenter_api import PresenterAPI
from runtime.presenter_state import PresenterState
from .account_fixture import admin
from .gateway_client import GatewayClient


class PresenterBootstrapContracts(unittest.TestCase):
    def setUp(self):
        identifier = "bootstrap-" + secrets.token_hex(6)
        self.presenter = Presenter(identifier, identifier + "@example.invalid",
                                   ("local-fixture-a", "local-fixture-b"))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.state = PresenterState(directory, self.presenter)
        self.api = PresenterAPI(admin(), GatewayClient())
        self.password = "Aa9!" + secrets.token_urlsafe(24)

    def initialize(self):
        initialize_presenter(self.api, self.state, self.presenter, self.password)

    def test_fresh_and_repeated_initialization_preserves_working_login(self):
        self.initialize()
        self.assertEqual(self.state.load()["phase"], "complete")
        self.assertTrue(self.api.login(self.presenter, self.password))
        with patch.object(self.api, "create_user") as create, patch.object(self.api, "claim") as claim:
            self.initialize()
        create.assert_not_called()
        claim.assert_not_called()
        self.assertTrue(self.api.login(self.presenter, self.password))

    def test_lost_claim_reply_recovers_without_reclaiming_password(self):
        actual_claim = self.api.claim

        def committed_but_reply_lost(*arguments):
            actual_claim(*arguments)
            raise GatewayError("Synthetic lost claim reply")

        with patch.object(self.api, "claim", side_effect=committed_but_reply_lost):
            with self.assertRaises(GatewayError):
                self.initialize()
        self.assertEqual(self.state.load()["phase"], "claim-started")
        with patch.object(self.api, "claim") as claim:
            self.initialize()
        claim.assert_not_called()
        self.assertEqual(self.state.load()["phase"], "complete")

    def test_lost_invitation_reply_stops_without_creating_a_duplicate(self):
        actual_create = self.api.create_invitation

        def committed_but_reply_lost(*arguments):
            actual_create(*arguments)
            raise GatewayError("Synthetic lost invitation reply")

        with patch.object(self.api, "create_invitation", side_effect=committed_but_reply_lost):
            with self.assertRaises(GatewayError):
                self.initialize()
        self.assertEqual(self.state.load()["phase"], "invitation-started")
        with patch.object(self.api, "create_invitation") as create:
            with self.assertRaises(GatewayError):
                self.initialize()
        create.assert_not_called()

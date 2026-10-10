"""Uncertain invitation or password writes cannot trigger blind resets."""

import unittest

from runtime.gateway_http import GatewayError
from runtime.presenter import initialize_presenter
from .presenter_fixture import AccountAPI, MemoryState, PASSWORD, PRESENTER


class PresenterRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.api, self.state = AccountAPI(), MemoryState()

    def initialize(self):
        return initialize_presenter(self.api, self.state, PRESENTER, PASSWORD)

    def test_lost_invitation_reply_never_creates_another_invitation(self):
        self.api.lose_invitation_reply = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.state.record["phase"], "invitation-started")
        self.api.lose_invitation_reply = False
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.api.calls.count("create-invitation"), 1)

    def test_lost_claim_reply_recovers_through_login(self):
        self.api.lose_claim_reply = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.state.record["phase"], "claim-started")
        self.initialize()
        self.assertEqual(self.api.calls.count("claim"), 1)
        self.assertEqual(self.state.record["phase"], "complete")

    def test_committed_password_with_acceptance_rollback_still_recovers_by_login(self):
        self.api.lose_claim_reply = self.api.rollback_acceptance = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.initialize()
        self.assertFalse(self.api.accepted)
        self.assertEqual(self.api.calls.count("claim"), 1)
        self.assertEqual(self.state.record["phase"], "complete")

    def test_failed_login_after_ambiguous_claim_never_resets_changed_password(self):
        self.api.lose_claim_reply = self.api.rollback_acceptance = True
        with self.assertRaises(GatewayError):
            self.initialize()
        self.api.password = "Changed9!Password"
        with self.assertRaises(GatewayError):
            self.initialize()
        self.assertEqual(self.api.calls.count("claim"), 1)
        self.assertEqual(self.api.password, "Changed9!Password")

    def test_interrupted_user_creation_recovers_by_stable_identity(self):
        self.state.save("user-started")
        self.api.user_exists = True
        self.initialize()
        self.assertNotIn("create-user", self.api.calls)
        self.assertEqual(self.state.record["phase"], "complete")

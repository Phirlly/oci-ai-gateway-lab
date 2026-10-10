"""Presenter ownership and interruption phases persist in private bounded files."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from runtime.gateway_http import GatewayError
from runtime.presenter import Presenter
from runtime.presenter_state import PresenterState
from .presenter_fixture import PRESENTER


class PresenterStateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = PresenterState(self.root, PRESENTER)

    def test_private_record_survives_a_new_process_owner(self):
        self.assertIsNone(self.state.load())
        self.state.save("user-started")
        self.state.save("invitation-started")
        self.state.save("invitation-created", "synthetic-invitation")
        restored = PresenterState(self.root, PRESENTER).load()
        self.assertEqual(restored["phase"], "invitation-created")
        self.assertEqual(restored["invitation"], "synthetic-invitation")
        self.assertEqual((self.root / "presenter.json").stat().st_mode & 0o777, 0o600)

    def test_changed_presenter_configuration_cannot_reuse_ownership(self):
        self.state.save("user-started")
        other = Presenter(PRESENTER.deployment_id, "other@example.invalid", PRESENTER.models)
        with self.assertRaises(GatewayError):
            PresenterState(self.root, other).load()

    def test_world_readable_records_are_rejected(self):
        self.state.save("user-started")
        (self.root / "presenter.json").chmod(0o644)
        with self.assertRaises(GatewayError):
            self.state.load()

    def test_symlink_record_is_not_followed_or_replaced(self):
        target = self.root / "other.json"
        target.write_text("preserve")
        (self.root / "presenter.json").symlink_to(target)
        with self.assertRaises(GatewayError):
            self.state.load()
        with self.assertRaises(GatewayError):
            self.state.save("user-started")
        self.assertEqual(target.read_text(), "preserve")

    def test_malformed_state_never_looks_like_a_fresh_account(self):
        self.state.save("user-started")
        path = self.root / "presenter.json"
        path.write_text(json.dumps({"password": "do-not-echo"}))
        with self.assertRaises(GatewayError) as raised:
            self.state.load()
        self.assertNotIn("do-not-echo", str(raised.exception))

    def test_failed_atomic_replace_preserves_the_previous_phase(self):
        from unittest.mock import patch
        self.state.save("user-started")
        with patch("os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(GatewayError):
                self.state.save("invitation-started")
        self.assertEqual(self.state.load()["phase"], "user-started")
        self.assertEqual(os.listdir(self.root), ["presenter.json"])

"""The HTTP deadline must not take a caller's timer or run on another thread."""

import unittest
from threading import Thread
from unittest.mock import patch

from tests.contracts.runtime import gateway_client


class DeadlineGuardTests(unittest.TestCase):
    def test_active_timer_is_preserved_and_request_rejected(self):
        with patch("signal.getitimer", return_value=(10.0, 0.0)):
            with patch("signal.setitimer") as timer:
                with self.assertRaisesRegex(RuntimeError, "active timer"):
                    with gateway_client.request_deadline(1):
                        self.fail("A caller's timer must not be replaced")
                timer.assert_not_called()

    def test_invalid_budgets_are_rejected(self):
        for budget in (0, -1, float("inf"), float("nan")):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                with gateway_client.request_deadline(budget):
                    self.fail("Invalid budgets must not execute requests")

    def test_non_main_thread_is_rejected_without_executing_request(self):
        failures = []

        def attempt():
            try:
                with gateway_client.request_deadline(1):
                    failures.append("request executed")
            except RuntimeError as error:
                failures.append(str(error))

        worker = Thread(target=attempt)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIn("main thread", failures[0])

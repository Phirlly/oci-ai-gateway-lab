"""Workflow polling has a finite budget and never retries arbitrary failures."""

import unittest

from deployment.action_wait import PollBudget
from deployment.credential_errors import DeliveryError


class ActionWaitTests(unittest.TestCase):
    def test_wait_reports_progress_and_stops_at_deadline(self):
        now, messages = [0], []
        budget = PollBudget(30, clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
                            progress=messages.append)
        budget.pause('IN_PROGRESS')
        budget.pause('IN_PROGRESS')
        with self.assertRaisesRegex(DeliveryError, 'Timed out'):
            budget.pause('IN_PROGRESS')
        self.assertEqual(now[0], 30)
        self.assertEqual(messages, ['IN_PROGRESS', 'IN_PROGRESS'])

    def test_invalid_budgets_fail_before_waiting(self):
        for value in (True, -1, 0, float('inf'), 3601):
            with self.subTest(value=value), self.assertRaises(DeliveryError):
                PollBudget(value)

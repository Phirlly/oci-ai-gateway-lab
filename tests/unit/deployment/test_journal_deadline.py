"""GitHub HTTP deadlines cannot replace caller timers or run on worker threads."""

import signal
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.github_http import GitHubHTTP, request_deadline


class JournalDeadlineTests(unittest.TestCase):
    def test_active_caller_timer_is_not_modified(self):
        with patch('signal.getitimer', return_value=(1., 0.)), patch('signal.setitimer') as timer:
            with self.assertRaises(DeliveryError):
                with request_deadline(.1):
                    self.fail('entered')
        timer.assert_not_called()

    def test_worker_thread_cannot_install_deadline(self):
        def request():
            with request_deadline(.1):
                self.fail('entered')
        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.assertRaises(DeliveryError):
                executor.submit(request).result()

    def test_invalid_timeout_is_rejected_before_request(self):
        for timeout in (0, -1, float('nan'), float('inf'), True, 61):
            with self.subTest(timeout=timeout), self.assertRaises(DeliveryError):
                GitHubHTTP('synthetic', timeout=timeout)

"""Finite workflow polling; callers choose only verified retryable states."""

import time

from .credential_errors import DeliveryError


class PollTimeout(DeliveryError):
    """A finite progress deadline expired without an ownership failure."""


class PollBudget:
    def __init__(self, seconds, *, clock=time.monotonic, sleep=time.sleep, progress=None):
        if type(seconds) is not int or not 1 <= seconds <= 3600:
            raise DeliveryError('Polling budget must be between1 and3600 seconds.')
        self.clock, self.sleep, self.progress = clock, sleep, progress or (lambda phase: None)
        self.deadline = clock() + seconds

    def pause(self, phase):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise PollTimeout('Timed out waiting for deployment progress; rerun the same action to reconcile.')
        self.progress(phase)
        self.sleep(min(15, remaining))

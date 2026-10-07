"""Run focused runtime suites with automatic, project-scoped cleanup."""

import argparse
import signal
import sys
import unittest

from .stack import GatewayStack
from .account_fixture import seed_invitation_creator

SUITES = ("configuration", "health", "onboarding", "access", "persistence")


def interrupted(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, action="append")
    arguments = parser.parse_args()
    selected = arguments.suite or list(SUITES)
    signal.signal(signal.SIGTERM, interrupted)
    success = False
    try:
        with GatewayStack() as stack:
            # Configuration assertions execute before any container is started.
            if "configuration" in selected:
                suite = unittest.defaultTestLoader.loadTestsFromName(
                    "tests.contracts.runtime.test_configuration"
                )
                if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
                    return 1
            runtime_suites = [name for name in selected if name != "configuration"]
            if runtime_suites:
                stack.start()
                seed_invitation_creator()
                suite = unittest.defaultTestLoader.loadTestsFromNames([
                    "tests.contracts.runtime.test_" + name for name in runtime_suites
                ])
                success = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
            else:
                success = True
    except KeyboardInterrupt:
        print("Interrupted; owned-resource cleanup attempted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Runtime verification failed: {error}", file=sys.stderr)
        return 1
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

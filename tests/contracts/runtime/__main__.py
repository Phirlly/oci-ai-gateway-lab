"""Run focused runtime suites with automatic, project-scoped cleanup."""

import argparse
import signal
import sys
import unittest

from .stack import GatewayStack
from .account_fixture import seed_invitation_creator

SUITES = ("configuration", "cloud_configuration", "health", "onboarding", "access", "persistence", "presenter_bootstrap")


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
            config_suites = [name for name in selected if name.endswith("configuration")]
            if config_suites:
                suite = unittest.defaultTestLoader.loadTestsFromNames([
                    "tests.contracts.runtime.test_" + name for name in config_suites
                ])
                if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
                    return 1
            runtime_suites = [name for name in selected if name not in config_suites]
            if runtime_suites:
                stack.start()
                if any(name != "presenter_bootstrap" for name in runtime_suites):
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

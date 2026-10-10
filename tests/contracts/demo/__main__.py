"""Run the two-provider adapter fixture with project-scoped cleanup."""

import signal
import sys

from tests.contracts.runtime.__main__ import interrupted
from .stack import ProviderStack


def main():
    signal.signal(signal.SIGTERM, interrupted)
    try:
        with ProviderStack() as stack:
            stack.start()
            return stack.run_contracts()
    except KeyboardInterrupt:
        print("Adapter verification interrupted; owned-resource cleanup attempted", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Adapter fixture failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

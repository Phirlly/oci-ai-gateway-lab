"""Keep bridged containers away from OCI IMDS before Docker restores them."""

import subprocess
import sys

from .gateway_http import GatewayError

COMMAND = ["/usr/sbin/iptables", "-w", "5", "-t", "raw"]
RULE = ["-d", "169.254.169.254/32", "-m", "comment", "--comment", "oci-ai-gateway-imds", "-j", "DROP"]


def _iptables(arguments):
    try:
        return subprocess.run(COMMAND + arguments, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=10).returncode
    except (OSError, subprocess.TimeoutExpired):
        raise GatewayError("Container metadata guard could not be verified") from None


def protect_metadata():
    # Confirm the table/chain is readable before interpreting a missing rule.
    if _iptables(["-S", "PREROUTING"]) != 0:
        raise GatewayError("Container metadata guard table is unavailable")
    exists = _iptables(["-C", "PREROUTING", *RULE])
    if exists == 0:
        return
    if exists != 1:
        raise GatewayError("Container metadata guard could not be inspected")
    if (_iptables(["-I", "PREROUTING", "1", *RULE]) != 0
            or _iptables(["-C", "PREROUTING", *RULE]) != 0):
        raise GatewayError("Container metadata guard installation failed")


def main():
    try:
        protect_metadata()
        return 0
    except GatewayError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

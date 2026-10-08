"""Synthetic OCI executable: process-boundary tests only, never a cloud client."""

import json
import os
import sys
import time

mode = sys.argv[1]
if "--version" in sys.argv:
    print("3.90.3" if mode == "old-version" else "3.94.0")
    raise SystemExit(0)

request = json.load(sys.stdin)
if mode == "timeout":
    print("secret-sentinel", flush=True)
    print("secret-sentinel", file=sys.stderr, flush=True)
    time.sleep(5)
elif mode == "failure":
    print("secret-sentinel")
    print("secret-sentinel", file=sys.stderr)
    raise SystemExit(7)
elif mode == "contaminated":
    print("HTTP debug secret-sentinel")
    print('{"data": {}}')
else:
    print(json.dumps({"data": {
        "request": request,
        "argv": sys.argv[2:],
        "environment_keys": sorted(os.environ),
    }}))

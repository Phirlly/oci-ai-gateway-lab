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
if mode in ("service-error", "service-unknown", "service-timeout"):
    print("secret-sentinel", flush=True)
    print('ServiceError:\n' + json.dumps({
        "status": 409, "code": "secret-sentinel" if mode == "service-unknown" else "IncorrectState",
        "message": "secret-sentinel", "request_endpoint": "https://private.example/secret-sentinel",
        "opc-request-id": "request-secret-sentinel", "extra": request,
    }), file=sys.stderr, flush=True)
    if mode == "service-timeout":
        time.sleep(5)
    raise SystemExit(1)
elif mode == "empty-list":
    raise SystemExit(0)
elif mode == "zero-total":
    print('{"opc-total-items": "0"}')
elif mode == "timeout":
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

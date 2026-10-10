"""Finite synthetic binary CLI output; never accesses cloud services."""

import json
import sys
import time

if '--version' in sys.argv:
    print('3.94.0')
    raise SystemExit(0)
mode = sys.argv[1]
if mode == 'no-input':
    time.sleep(.5)
    raise SystemExit(0)
request = json.load(sys.stdin)
if mode == 'timeout':
    sys.stdout.buffer.write(b'PK')
    sys.stdout.flush()
    time.sleep(5)
elif mode == 'large':
    sys.stdout.buffer.write(b'x' * (1024 * 1024 + 1))
elif mode == 'failure':
    print('secret-sentinel', file=sys.stderr)
    raise SystemExit(4)
else:
    kind = "stack" if mode == "stack" else "job"
    assert request == {kind + "Id": "ocid1.orm" + kind + ".oc1.iad.synthetic"}
    suffix = "-tf-state" if mode == "state" else "-tf-config"
    assert ["resource-manager", kind, "get-" + kind + suffix] == sys.argv[-7:-4]
    assert sys.argv[-4:] == ['--file', '-', '--from-json', 'file:///dev/stdin']
    sys.stdout.buffer.write(b'{"version":4,"resources":[]}' if mode == 'state' else b'PK\x00\xffsynthetic')

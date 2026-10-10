"""Synthetic conditional failures; never calls OCI or reads credentials."""

import json
import sys
import time

mode = sys.argv[1]
if '--version' in sys.argv:
    print('3.94.0')
    raise SystemExit(0)

request = json.load(sys.stdin)
secret = request.get('secretId', 'missing')
etag = request.get('ifMatch', 'missing')
if mode == 'gzip-tag':
    etag = etag.removesuffix('--gzip')
message = f'Entity Secret with ID {secret} has a computed tag of newer, but is passed a tag of {etag}'
if mode == 'wrong-secret':
    message = message.replace(secret, 'ocid1.vaultsecret.oc1.iad.other')
if mode == 'wrong-tag':
    message = message.replace(etag, 'other-tag')
if mode == 'generic':
    message = 'Unrelated secret-sentinel conflict'
print('secret-sentinel', flush=True)
print('ServiceError:\n' + json.dumps({
    'status': 412 if mode == 'precondition' else 409,
    'code': 'NoEtagMatch' if mode == 'precondition' else 'Conflict',
    'message': message, 'extra': 'secret-sentinel',
}), file=sys.stderr, flush=True)
if mode == 'timeout':
    time.sleep(5)
raise SystemExit(1)

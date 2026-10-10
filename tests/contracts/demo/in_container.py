"""Run only synthetic adapter contracts on the isolated container network."""

import json
import os
import sys
import unittest
import urllib.request

from demo.verification import check_health
from runtime.gateway_entrypoint import entry_environment
from tests.contracts.runtime.gateway_client import GatewayClient
from . import test_adapters


class ProviderCounts:
    def counts(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://provider:8080/stats', timeout=3) as response:
            return json.loads(response.read(4096))


def main():
    os.environ['GATEWAY_TEST_URL'] = 'http://127.0.0.1:4000'
    if sys.argv[1:] == ['--health']:
        check_health(GatewayClient())
        return 0
    if sys.argv[1:]:
        raise ValueError('Only the fixed adapter suite or --health is supported')
    os.environ['GATEWAY_TEST_MASTER_KEY'] = entry_environment('/run/secrets/gateway.json')['LITELLM_MASTER_KEY']
    test_adapters.STACK = ProviderCounts()
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_adapters)
    return 0 if unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())

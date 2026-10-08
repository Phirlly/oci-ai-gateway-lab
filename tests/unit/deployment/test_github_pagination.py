"""Journal discovery requires complete, same-repository pagination."""

import unittest

from deployment.credential_errors import DeliveryError
from deployment.github_pagination import next_page


class GitHubPaginationTests(unittest.TestCase):
    def test_name_and_numeric_repository_paths_are_supported(self):
        for path in ('/repos/example/gateway/deployments', '/repositories/17/deployments'):
            with self.subTest(path=path):
                link = '<https://api.github.com' + path + '?task=gateway_submission&per_page=100&page=2>; rel="next"'
                self.assertEqual(next_page(link, 'example/gateway', 17, 1), 2)
        self.assertIsNone(next_page(None, 'example/gateway', 17, 1))

    def test_foreign_paths_filters_repeated_pages_and_malformed_links_fail(self):
        urls = [
            'https://evil.example/repos/example/gateway/deployments?task=gateway_submission&per_page=100&page=2',
            'https://api.github.com/repositories/18/deployments?task=gateway_submission&per_page=100&page=2',
            'https://api.github.com/repos/example/gateway/deployments?task=other&per_page=100&page=2',
            'https://api.github.com/repos/example/gateway/deployments?task=gateway_submission&per_page=100&page=1',
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(DeliveryError):
                next_page('<' + url + '>; rel="next"', 'example/gateway', 17, 1)
        with self.assertRaises(DeliveryError):
            next_page('malformed', 'example/gateway', 17, 1)

    def test_missing_next_cannot_hide_a_later_last_page(self):
        link = '<https://api.github.com/repositories/17/deployments?task=gateway_submission&per_page=100&page=2>; rel="last"'
        with self.assertRaises(DeliveryError):
            next_page(link, 'example/gateway', 17, 1)

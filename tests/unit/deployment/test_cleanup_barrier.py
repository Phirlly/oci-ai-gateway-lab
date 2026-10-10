"""Cleanup begins durably before key deletion and prevents all Apply paths."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.submission_records import Intent, target_identity
from .handoff_fixture import HandoffFixture


class CleanupBarrierTests(unittest.TestCase):
    def test_new_cleanup_records_round_trip_without_changing_old_versions(self):
        for kind in ('cleanup-start', 'cleanup-complete'):
            with self.subTest(kind=kind):
                record = Intent('a' * 64, 'b' * 64, kind, 'c' * 32, 'd' * 64, 'e' * 64)
                self.assertEqual(record.payload()['version'], 3)
                self.assertNotIn('retry_of', record.payload())
                self.assertEqual(Intent.parse(record.payload()), record)
                for version in (1, 2):
                    with self.assertRaises(DeliveryError):
                        Intent.parse({**record.payload(), 'version': version})
        for kind in ('create-stack', 'apply', 'destroy'):
            record = Intent('a' * 64, 'b' * 64, kind, 'c' * 32, 'd' * 64, 'e' * 64)
            self.assertEqual(record.payload()['version'], 1)
            with self.assertRaises(DeliveryError):
                Intent.parse({**record.payload(), 'version': 3})

    def test_cleanup_blocks_unbound_apply_and_bound_credential_shortcut(self):
        for bound in (False, True):
            f = HandoffFixture()
            if bound:
                f.permissions_started()
                f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
                f.advance()
            else:
                f.base_succeeded()
            f.journal.submit(target_identity(f.target.config), 'cleanup-start', 'f' * 64,
                             f.package.digest, lambda intent: intent)
            writes, jobs = list(f.vault.mutations), len(f.orm.jobs)
            with self.subTest(bound=bound), self.assertRaisesRegex(DeliveryError, 'Cleanup|cleanup'):
                f.advance()
            with self.assertRaises(DeliveryError):
                ensure_apply(f.orm, f.journal, f.target, f.package, f.orm.stacks[0]['id'],
                             model_key_ocid=None, retry_failed=True)
            self.assertEqual(f.vault.mutations, writes)
            self.assertEqual(len(f.orm.jobs), jobs)

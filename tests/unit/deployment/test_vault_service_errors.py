"""Conditional rejection requires an exact, bounded service/request match."""

import json
import unittest

from deployment.vault_service_errors import staging_etag_rejected

SECRET = 'ocid1.vaultsecret.oc1.iad.example'
MESSAGE = f'Entity Secret with ID {SECRET} has a computed tag of newer, but is passed a tag of older'


def request(**changes):
    return json.dumps({'secretId': SECRET, 'ifMatch': 'older',
                       'secretContentName': 'runtime-' + 'a' * 32,
                       'secretContentStage': 'PENDING', 'secretContentContent': 'eA=='} | changes)


def error(**changes):
    return 'ServiceError:\n' + json.dumps({'status': 409, 'code': 'Conflict', 'message': MESSAGE} | changes)


class VaultServiceErrorTests(unittest.TestCase):
    def test_exact_observed_conflict_and_documented_precondition_are_rejections(self):
        self.assertTrue(staging_etag_rejected(error(), request()))
        self.assertTrue(staging_etag_rejected(error(status=412, code='NoEtagMatch'), request()))
        self.assertTrue(staging_etag_rejected(error(), request(secretContentName='intent-' + 'a' * 32)))

    def test_unrelated_conflicts_and_mismatched_identity_or_tags_are_uncertain(self):
        for message in ('generic conflict', MESSAGE.replace(SECRET, SECRET + 'other'),
                        MESSAGE.replace('older', 'other'), MESSAGE.replace('newer', 'older'),
                        'prefix ' + MESSAGE, MESSAGE + ' extra', MESSAGE + '\n',
                        MESSAGE.replace('newer', '\nnewer'), None):
            with self.subTest(message=message):
                self.assertFalse(staging_etag_rejected(error(message=message), request()))
        for status, code in ((400, 'Conflict'), (409, 'NoEtagMatch'), (409, 'IncorrectState'),
                             (412, 'Conflict'), ('409', 'Conflict')):
            with self.subTest(status=status, code=code):
                self.assertFalse(staging_etag_rejected(error(status=status, code=code), request()))

    def test_malformed_contaminated_or_oversized_diagnostics_cannot_authorize_retry(self):
        for stderr in ('debug\n' + error(), error() + '{}', error().replace('409', '409,"status":412'),
                       error(extra=float('nan')), error(extra='x' * 16384),
                       'ServiceError:\n[]', 'ServiceError:\n{"status":409,', None):
            with self.subTest(stderr=str(stderr)[:70]):
                self.assertFalse(staging_etag_rejected(stderr, request()))

    def test_only_exact_conditional_pending_credential_payload_is_eligible(self):
        for changes in ({'ifMatch': ''}, {'ifMatch': 'older\n'}, {'ifMatch': None},
                        {'secretId': 'wrong'}, {'secretContentStage': 'CURRENT'},
                        {'secretContentName': 'cleanup-' + 'a' * 32},
                        {'secretContentName': 'runtime-invalid'}, {'currentVersionNumber': 3},
                        {'secretContentContent': None}):
            with self.subTest(changes=changes):
                self.assertFalse(staging_etag_rejected(error(), request(**changes)))
        for content in ('{', '[]', 'null', 'x' * 32769, None):
            with self.subTest(content=str(content)[:30]):
                self.assertFalse(staging_etag_rejected(error(), content))

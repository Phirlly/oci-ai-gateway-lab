"""Downloaded ZIP content is verified without filesystem extraction."""

import io
import stat
import unittest
import zipfile
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.foundation_package import FoundationPackage, SOURCE_FILES, archive_digest
from .foundation_fixtures import archive_bytes


class ArchiveAttestationTests(unittest.TestCase):
    def test_container_timestamps_do_not_change_content_identity(self):
        expected = archive_digest(archive_bytes())
        self.assertEqual(expected, archive_digest(archive_bytes(timestamp=(2024, 1, 1, 0, 0, 0))))

    def test_changed_lockfile_cannot_attest(self):
        package = FoundationPackage(archive_bytes())
        with self.assertRaises(DeliveryError):
            package.verify(archive_bytes(changed='.terraform.lock.hcl'))

    def test_extra_traversal_and_duplicate_members_are_rejected(self):
        for name in ('../secret', '/absolute', 'foundation/versions.tf', 'foundation/test.tf'):
            with self.subTest(name=name), self.assertRaises(DeliveryError):
                archive_digest(archive_bytes(extra=name))

    def test_symlink_replacing_regular_member_is_rejected(self):
        content = archive_bytes(member_modes={'versions.tf': stat.S_IFLNK})
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(len(archive.infolist()), 8)
        with self.assertRaises(DeliveryError):
            archive_digest(content)

    def test_compressed_input_size_limit_is_enforced(self):
        with self.assertRaises(DeliveryError):
            archive_digest(b'x' * (1024 * 1024 + 1))

    def test_small_compressed_archive_cannot_exceed_member_or_total_expansion(self):
        cases = ({'versions.tf': b'x' * 300000}, {name: b'x' * 150000 for name in SOURCE_FILES})
        for data in cases:
            content = archive_bytes(member_data=data, compression=zipfile.ZIP_DEFLATED)
            self.assertLess(len(content), 1024 * 1024)
            with self.subTest(members=len(data)), self.assertRaises(DeliveryError):
                archive_digest(content)

    def test_encryption_flag_is_rejected_before_opening_member(self):
        content = archive_bytes()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
        entries[0].flag_bits |= 1
        with patch.object(zipfile.ZipFile, 'infolist', return_value=entries):
            with self.assertRaises(DeliveryError):
                archive_digest(content)

    def test_corrupted_crc_cannot_attest(self):
        content = archive_bytes(member_data={'versions.tf': b'crc-sentinel-payload'})
        damaged = content.replace(b'crc-sentinel-payload', b'bad-sentinel-payload')
        self.assertNotEqual(content, damaged)
        with self.assertRaises(DeliveryError):
            archive_digest(damaged)

    def test_invalid_zip_is_a_sanitized_failure(self):
        with self.assertRaises(DeliveryError) as error:
            archive_digest(b'secret-sentinel')
        self.assertNotIn('sentinel', str(error.exception))

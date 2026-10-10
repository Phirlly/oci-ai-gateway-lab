"""Runner signing material stays private, bounded and outside process arguments."""

import configparser
import tempfile
import unittest
from pathlib import Path

from deployment.credential_errors import DeliveryError
from deployment.runner_credentials import runner_connection, local_connection

TENANCY = "ocid1.tenancy.oc1..example"
SIGNING = {
    "OCI_USER_OCID": "ocid1.user.oc1..example",
    "OCI_FINGERPRINT": ":".join(["ab"] * 16),
    "OCI_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nc3ludGhldGlj\n-----END PRIVATE KEY-----\n",
    "OCI_PRIVATE_KEY_PASSPHRASE": "protected-passphrase",
}


class RunnerCredentialTests(unittest.TestCase):
    def test_connection_files_are_private_and_removed_after_use(self):
        with runner_connection(SIGNING, TENANCY) as connection:
            path = Path(connection.config_file)
            config = configparser.ConfigParser(interpolation=None)
            config.read(path)
            key = Path(config["DEFAULT"]["key_file"])
            self.assertEqual(config["DEFAULT"]["tenancy"], TENANCY)
            self.assertEqual(key.read_text(), SIGNING["OCI_PRIVATE_KEY"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(connection.profile, "DEFAULT")
            self.assertNotIn("protected-passphrase", repr(connection))
        self.assertFalse(path.exists())
        self.assertFalse(key.exists())

    def test_failed_operation_still_removes_signing_files(self):
        with self.assertRaises(RuntimeError):
            with runner_connection(SIGNING, TENANCY) as connection:
                path = Path(connection.config_file)
                raise RuntimeError("synthetic")
        self.assertFalse(path.parent.exists())

    def test_missing_or_injected_credentials_fail_without_echoing_values(self):
        for field in ("OCI_USER_OCID", "OCI_FINGERPRINT", "OCI_PRIVATE_KEY"):
            with self.subTest(field=field), self.assertRaises(DeliveryError):
                with runner_connection({**SIGNING, field: ""}, TENANCY):
                    self.fail("Invalid credentials reached caller")
        for field in ("OCI_USER_OCID", "OCI_FINGERPRINT", "OCI_PRIVATE_KEY_PASSPHRASE"):
            with self.subTest(field=field), self.assertRaises(DeliveryError) as error:
                with runner_connection({**SIGNING, field: "secret-sentinel\n[bad]"}, TENANCY):
                    self.fail("Injected config reached caller")
            self.assertNotIn("secret-sentinel", str(error.exception))

    def test_model_and_presenter_secrets_are_not_required_for_connection(self):
        with runner_connection(SIGNING, TENANCY) as connection:
            self.assertTrue(Path(connection.config_file).is_file())

    def test_mismatched_pem_labels_fail_before_creating_connection(self):
        key = SIGNING['OCI_PRIVATE_KEY'].replace('END PRIVATE KEY', 'END RSA PRIVATE KEY')
        with self.assertRaises(DeliveryError):
            with runner_connection({**SIGNING, 'OCI_PRIVATE_KEY': key}, TENANCY):
                self.fail('Mismatched PEM labels reached the caller')

    def test_oracle_tagged_key_is_preserved_but_arbitrary_trailers_are_rejected(self):
        key = SIGNING['OCI_PRIVATE_KEY'] + 'OCI_API_KEY\n'
        with runner_connection({**SIGNING, 'OCI_PRIVATE_KEY': key}, TENANCY) as connection:
            config = configparser.ConfigParser(interpolation=None)
            config.read(connection.config_file)
            self.assertEqual(Path(config['DEFAULT']['key_file']).read_text(), key)
        for trailer in ('unexpected', 'OCI_API_KEY\nextra', 'OCI_API_KEY\nOCI_API_KEY'):
            with self.subTest(trailer=trailer), self.assertRaises(DeliveryError):
                with runner_connection({**SIGNING, 'OCI_PRIVATE_KEY': SIGNING['OCI_PRIVATE_KEY'] + trailer}, TENANCY):
                    self.fail('Arbitrary trailer reached the caller')

    def test_explicit_local_profile_must_match_configured_tenancy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_text("[DEFAULT]\ntenancy=" + TENANCY +
                            "\n[Other]\ntenancy=ocid1.tenancy.oc1..other\n")
            self.assertEqual(local_connection(path, "DEFAULT", TENANCY).profile, "DEFAULT")
            with self.assertRaises(DeliveryError):
                local_connection(path, "Other", TENANCY)
            with self.assertRaises(DeliveryError):
                local_connection(path, "Missing", TENANCY)

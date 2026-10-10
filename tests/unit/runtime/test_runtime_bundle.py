"""Only a complete current bundle bound to this deployment and VM may start runtime."""

import json
import unittest
from runtime.gateway_http import GatewayError
from runtime.runtime_bundle import BundlePending, load_bundle, validate_settings
from .bundle_fixture import INSTANCE, NOW, SETTINGS, bundle


class RuntimeBundleTests(unittest.TestCase):
    def load(self, value, **kwargs):
        return load_bundle(json.dumps(value).encode(), SETTINGS, INSTANCE, now=kwargs.get("now", NOW))

    def test_complete_bundle_exposes_validated_configuration_without_secret_repr(self):
        result = self.load(bundle())
        self.assertEqual(result.public_ip, "8.8.4.4")
        self.assertEqual(result.presenter.email, SETTINGS["presenter_email"])
        self.assertEqual(result.credentials["oci_api_key"], "synthetic-oci-key")
        self.assertNotIn("synthetic-oci-key", repr(result))

    def test_placeholder_is_waiting_not_valid_runtime_content(self):
        with self.assertRaises(BundlePending):
            load_bundle(b"UNCONFIGURED", SETTINGS, INSTANCE, now=NOW)

    def test_wrong_deployment_or_instance_cannot_use_bundle(self):
        for section, field, replacement in (
            ("identity", "compartment_ocid", "ocid1.compartment.oc1..other"),
            ("identity", "secret_ocid", "ocid1.vaultsecret.oc1.iad.other"),
            ("runtime", "instance_ocid", "ocid1.instance.oc1.iad.other"),
            ("runtime", "external_model_id", "other-model"),
        ):
            value = bundle()
            value[section][field] = replacement
            with self.subTest(field=field), self.assertRaises(GatewayError):
                self.load(value)

    def test_expired_or_nonruntime_records_do_not_start_services(self):
        for replacement in ({"expires_at": "2026-10-09T00:00:00Z"},
                            {"kind": "creation-intent"}, {"schema_version": 1}):
            with self.subTest(fields=tuple(replacement)), self.assertRaises(GatewayError):
                self.load(bundle() | replacement)

    def test_missing_credentials_and_private_addresses_are_rejected(self):
        value = bundle()
        del value["credentials"]["gateway_salt_key"]
        with self.assertRaises(GatewayError):
            self.load(value)
        value = bundle()
        value["runtime"]["public_ip"] = "169.254.169.254"
        with self.assertRaises(GatewayError):
            self.load(value)

    def test_oversized_duplicate_or_unknown_fields_fail_without_echoing_content(self):
        for raw in (b"x" * 16385, b'{"kind":"secret-sentinel","kind":"runtime-bundle"}',
                    json.dumps(bundle() | {"secret-sentinel": True}).encode()):
            with self.subTest(length=len(raw)), self.assertRaises(GatewayError) as raised:
                load_bundle(raw, SETTINGS, INSTANCE, now=NOW)
            self.assertNotIn("secret-sentinel", str(raised.exception))

    def test_settings_cannot_include_credentials_or_change_schema(self):
        self.assertEqual(validate_settings(SETTINGS), SETTINGS)
        for value in (SETTINGS | {"api_key": "secret"}, SETTINGS | {"schema_version": 2}):
            with self.assertRaises(GatewayError):
                validate_settings(value)

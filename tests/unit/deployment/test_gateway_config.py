"""Full settings preserve types locally and encode exactly once for ORM."""

import json
import unittest

from deployment.credential_errors import DeliveryError
from deployment.deployment_config import FoundationConfig, load_config
from .gateway_config_fixture import GATEWAY_SETTINGS
from .orm_fixtures import KEY_ID, SETTINGS


class GatewayConfigurationTests(unittest.TestCase):
    def test_full_document_roundtrips_typed_values_and_recovered_binding(self):
        config = load_config(json.dumps(GATEWAY_SETTINGS))
        self.assertEqual(config.values, GATEWAY_SETTINGS)
        self.assertIs(type(config.values["instance_ocpus"]), int)
        variables = config.orm_variables(model_key_ocid=KEY_ID)
        self.assertEqual(variables["instance_ocpus"], "2")
        self.assertEqual(variables["presenter_email"], "presenter@example.test")
        self.assertEqual(config.read_binding(variables), KEY_ID)
        with self.assertRaises(TypeError):
            config.values["instance_ocpus"] = 4

    def test_legacy_five_field_document_remains_exactly_compatible(self):
        config = load_config(json.dumps(SETTINGS))
        self.assertIs(type(config), FoundationConfig)
        self.assertEqual(config.orm_variables(model_key_ocid=None), SETTINGS)

    def test_missing_unknown_secret_or_derived_fields_fail_without_exposing_values(self):
        cases = [
            {**GATEWAY_SETTINGS, "api_key": "sensitive-sentinel"},
            {**GATEWAY_SETTINGS, "oci_model_key_ocid": KEY_ID},
            {**GATEWAY_SETTINGS, "profile": "sensitive-sentinel"},
            {key: value for key, value in GATEWAY_SETTINGS.items() if key != "presenter_email"},
        ]
        for value in cases:
            with self.subTest(fields=sorted(value)), self.assertRaises(DeliveryError) as error:
                load_config(json.dumps(value))
            self.assertNotIn("sensitive-sentinel", str(error.exception))

    def test_wrong_types_unsafe_text_and_unsupported_values_are_rejected(self):
        cases = {
            "schema_version": [1, True, "2", 3],
            "instance_ocpus": [True, "2", 0, 17, 1.5],
            "instance_memory_gbs": [0, "16", True, 257],
            "boot_volume_size_gbs": [1, 501],
            "availability_domain_number": [0, 4],
            "model_key_ttl_days": [0, 31],
            "inference_region": ["https://evil.invalid", "../iad"],
            "external_provider": ["openai", "anthropic\n"],
            "external_model_id": ["model\n", "https://evil.invalid"],
            "presenter_email": ["no-domain", "name\n@example.test", "name@example.test#x"],
            "instance_shape": ["VM.Standard.A1.Flex", "unknown"],
            "image_name": ["latest", "Canonical-Ubuntu-22.04-latest"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(DeliveryError):
                    load_config(json.dumps({**GATEWAY_SETTINGS, field: value}))

    def test_conflicting_stack_settings_do_not_pass_as_resume(self):
        config = load_config(json.dumps(GATEWAY_SETTINGS))
        variables = config.orm_variables(model_key_ocid=KEY_ID)
        variables["external_model_id"] = "another-model"
        with self.assertRaises(DeliveryError):
            config.read_binding(variables)

    def test_memory_must_fit_supported_flexible_shape_ratio(self):
        with self.assertRaises(DeliveryError):
            load_config(json.dumps({**GATEWAY_SETTINGS, "instance_ocpus": 1,
                                    "instance_memory_gbs": 128}))

"""Only implemented foundation settings enter Resource Manager variables."""

import json
import traceback
import unittest

from deployment.credential_errors import DeliveryError
from deployment.deployment_config import FoundationConfig, load_config
from .orm_fixtures import KEY_ID, SETTINGS


class FoundationConfigurationTests(unittest.TestCase):
    def test_json_and_mapping_produce_identical_unquoted_string_variables(self):
        config = load_config(json.dumps(SETTINGS).encode())
        self.assertEqual(config.orm_variables(model_key_ocid=None), SETTINGS)
        self.assertEqual(config, FoundationConfig(SETTINGS))
        with self.assertRaises(TypeError):
            config.values["region"] = "other"

    def test_operator_cannot_supply_credentials_unknown_fields_or_derived_binding(self):
        for field in ("api_key", "profile", "unexpected", "oci_model_key_ocid"):
            with self.subTest(field=field), self.assertRaises(DeliveryError):
                load_config(json.dumps({**SETTINGS, field: None}))

    def test_duplicate_fields_invalid_json_and_nonobject_are_rejected(self):
        duplicate = json.dumps(SETTINGS)[:-1] + ', "region": "us-chicago-1"}'
        for value in (duplicate, "[1]", "null", "{", b"\xff", 5):
            with self.subTest(value=repr(value)), self.assertRaises(DeliveryError):
                load_config(value)

    def test_required_fields_types_and_terraform_patterns_are_enforced(self):
        invalid = {
            "tenancy_ocid": "ocid1.tenancy.oc2..example",
            "compartment_ocid": "ocid1.tenancy.oc1..example",
            "region": "../us-ashburn-1", "deployment_id": "Name With Spaces",
            "oci_model_id": "model', request.principal.type='user",
        }
        for field, wrong in invalid.items():
            for value in (wrong, None, True, 1, ""):
                with self.subTest(field=field, value=value), self.assertRaises(DeliveryError):
                    FoundationConfig({**SETTINGS, field: value})
            with self.subTest(missing=field), self.assertRaises(DeliveryError):
                FoundationConfig({key: value for key, value in SETTINGS.items() if key != field})

    def test_total_input_and_each_variable_have_separate_byte_limits(self):
        with self.assertRaises(DeliveryError):
            load_config(" " * (48 * 1024) + json.dumps(SETTINGS))
        field, prefix = "tenancy_ocid", "ocid1.tenancy.oc1.."
        maximum = prefix + "a" * (8192 - len(field) - len(prefix))
        self.assertEqual(FoundationConfig({**SETTINGS, field: maximum}).values[field], maximum)
        with self.assertRaises(DeliveryError):
            FoundationConfig({**SETTINGS, field: maximum + "a"})

    def test_initial_binding_is_omitted_and_existing_binding_is_retained(self):
        config = FoundationConfig(SETTINGS)
        self.assertNotIn("oci_model_key_ocid", config.orm_variables(model_key_ocid=None))
        variables = config.orm_variables(model_key_ocid=KEY_ID)
        self.assertEqual(config.read_binding(variables), KEY_ID)
        self.assertIsNone(config.read_binding(SETTINGS))
        self.assertEqual(variables["oci_model_key_ocid"], KEY_ID)

    def test_invalid_derived_values_and_changed_stack_variables_are_rejected(self):
        config = FoundationConfig(SETTINGS)
        for value in ("null", "", 1, "ocid1.key.oc1.iad.example", KEY_ID + "a" * 8192):
            with self.subTest(value=str(value)[:20]), self.assertRaises(DeliveryError):
                config.orm_variables(model_key_ocid=value)
        for value in (None, "null", ""):
            with self.subTest(binding=value), self.assertRaises(DeliveryError):
                config.read_binding({**SETTINGS, "oci_model_key_ocid": value})
        with self.assertRaises(DeliveryError):
            config.read_binding({**SETTINGS, "region": "us-chicago-1"})

    def test_invalid_input_is_not_exposed_in_exception(self):
        with self.assertRaises(DeliveryError) as error:
            load_config('{"secret-sentinel": "secret-sentinel"}')
        self.assertNotIn("secret-sentinel", "".join(traceback.format_exception(error.exception)))

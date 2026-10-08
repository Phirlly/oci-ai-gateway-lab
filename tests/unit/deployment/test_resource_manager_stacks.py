"""Stack discovery requires identity, ownership and exact configuration."""

import unittest

from deployment.credential_errors import DeliveryError
from deployment.deployment_config import FoundationConfig
from deployment.resource_manager_stacks import StackTarget, find_stack, parse_stack
from .orm_fixtures import CONTROLLER, KEY_ID, SETTINGS, STACK_ID, TAGS, stack_data


class StackInspectionTests(unittest.TestCase):
    def setUp(self):
        self.target = StackTarget(FoundationConfig(SETTINGS), CONTROLLER)

    def test_empty_and_unrelated_untagged_resources_mean_not_observed(self):
        self.assertIsNone(find_stack({"data": []}, self.target))
        for tags in (None, {}):
            unrelated = stack_data(**{"display-name": "another", "freeform-tags": tags})
            self.assertIsNone(find_stack({"data": [unrelated]}, self.target))

    def test_ownership_survives_display_name_change(self):
        renamed = stack_data(**{"display-name": "renamed"})
        self.assertEqual(find_stack({"data": [renamed]}, self.target), STACK_ID)

    def test_name_collision_or_other_controller_cannot_be_adopted(self):
        for tags in ({}, {**TAGS, "controller_id": "d" * 64}):
            with self.subTest(tags=tags), self.assertRaises(DeliveryError):
                find_stack({"data": [stack_data(**{"freeform-tags": tags})]}, self.target)

    def test_duplicate_ids_and_multiple_owned_stacks_are_rejected(self):
        for other in (STACK_ID, STACK_ID + "2"):
            with self.subTest(other=other), self.assertRaises(DeliveryError):
                find_stack({"data": [stack_data(), stack_data(id=other)]}, self.target)

    def test_full_read_preserves_exact_binding_and_etag(self):
        data = stack_data(variables={**SETTINGS, "oci_model_key_ocid": KEY_ID})
        snapshot = parse_stack({"data": data, "etag": "version-2"}, self.target, STACK_ID)
        self.assertEqual(snapshot.model_key_ocid, KEY_ID)
        self.assertEqual(snapshot.etag, "version-2")
        self.assertEqual(snapshot.state, "ACTIVE")

    def test_mismatched_full_resource_and_unknown_state_are_rejected(self):
        changes = [
            {"id": STACK_ID + "2"}, {"compartment-id": "wrong"},
            {"freeform-tags": {}}, {"lifecycle-state": "UNKNOWN_ENUM_VALUE"},
            {"variables": {**SETTINGS, "region": "us-chicago-1"}},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DeliveryError):
                parse_stack({"data": stack_data(**change), "etag": "v"}, self.target, STACK_ID)
        with self.assertRaises(DeliveryError):
            parse_stack({"data": stack_data()}, self.target, STACK_ID)

    def test_malformed_discovery_and_invalid_controller_are_sanitized(self):
        for response in ({}, {"data": {}}, {"data": [None]}, {"data": [{"id": "secret-sentinel"}]}):
            with self.subTest(response=response), self.assertRaises(DeliveryError) as error:
                find_stack(response, self.target)
            self.assertNotIn("secret-sentinel", str(error.exception))
        with self.assertRaises(DeliveryError):
            StackTarget(FoundationConfig(SETTINGS), "not-an-owner-hash")

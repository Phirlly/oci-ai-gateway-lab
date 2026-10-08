"""Prove key ownership, slot selection, expiry and readiness independently."""

import unittest
from copy import deepcopy

from deployment.credential_errors import DeliveryError
from deployment.model_key_state import owned_candidates, parse_model_key
from .model_key_fixture import key_data
from .record_fixtures import IDENTITY, KEY_ID, NOW
from .vault_fixture import record


class ModelKeyStateTests(unittest.TestCase):
    def test_extra_slot_is_allowed_and_named_gateway_is_selected(self):
        data = key_data()
        data["keys"].insert(0, {**data["keys"][0], "key-name": "standby", "key": "other"})
        parsed = parse_model_key({"data": data}, record("creation-intent"), now=NOW, require_secret=True)
        self.assertEqual(parsed.key_id, KEY_ID)
        self.assertEqual(parsed.secret, "model-sentinel")
        self.assertNotIn("sentinel", repr(parsed))

    def test_equivalent_aware_expiry_is_accepted_but_naive_or_changed_is_rejected(self):
        data = key_data()
        data["keys"][0]["time-expiry"] = "2030-01-02T00:00:00+00:00"
        parse_model_key({"data": data}, record(), now=NOW, require_active=True)
        for value in ("2030-01-02T00:00:00", "2030-01-03T00:00:00Z", None):
            with self.subTest(value=value):
                data["keys"][0]["time-expiry"] = value
                with self.assertRaises(DeliveryError):
                    parse_model_key({"data": data}, record(), now=NOW)

    def test_missing_duplicate_or_malformed_gateway_slot_is_rejected(self):
        data = key_data()
        for slots in ([], data["keys"] * 2, "bad", [None], [{"key-name": "standby"}]):
            with self.subTest(slot_count=len(slots)):
                with self.assertRaises(DeliveryError):
                    parse_model_key({"data": {**data, "keys": slots}}, record(), now=NOW)

    def test_foreign_identity_or_wrong_exact_key_cannot_authorize_binding(self):
        data = key_data()
        variants = [
            {"id": "ocid1.key.oc1.iad.wrong"},
            {"id": "ocid1.generativeaiapikey.oc1.ord.other"},
            {"compartment-id": "other"},
            {"freeform-tags": {**data["freeform-tags"], "operation_id": "b" * 32}},
            {"freeform-tags": {**data["freeform-tags"], "stack_ocid": "other"}},
        ]
        for changes in variants:
            with self.subTest(fields=list(changes)):
                with self.assertRaises(DeliveryError):
                    parse_model_key({"data": {**data, **changes}}, record(), now=NOW,
                                    expected_key_id=KEY_ID, require_active=True)

    def test_creating_resource_and_inactive_slot_can_be_saved_but_not_bound(self):
        data = key_data()
        data["lifecycle-state"] = "CREATING"
        data["keys"][0]["state"] = "INACTIVE"
        parse_model_key({"data": data}, record("creation-intent"), now=NOW, require_secret=True)
        with self.assertRaises(DeliveryError):
            parse_model_key({"data": data}, record(), now=NOW, require_active=True)

    def test_missing_or_invalid_one_time_secret_is_rejected_without_echo(self):
        for value in (None, "", "sentinel\n", 1):
            data = key_data()
            data["keys"][0]["key"] = value
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(DeliveryError) as error:
                    parse_model_key({"data": data}, record("creation-intent"), now=NOW, require_secret=True)
                self.assertNotIn("sentinel", str(error.exception))

    def test_discovery_uses_collection_items_and_full_ownership(self):
        own = key_data()
        foreign = deepcopy(own)
        foreign.update(id="ocid1.generativeaiapikey.oc1.ord.foreign", **{
            "display-name": "unrelated", "freeform-tags": {}})
        self.assertEqual(owned_candidates({"data": {"items": [foreign, own]}}, IDENTITY), (KEY_ID,))
        for response in ({"data": []}, {"data": {"items": [own, own]}},
                         {"data": {"items": [{**own, "freeform-tags": {}}]}}):
            with self.assertRaises(DeliveryError):
                owned_candidates(response, IDENTITY)

    def test_unrelated_untagged_keys_do_not_block_discovery_or_prove_ownership(self):
        foreign = key_data()
        foreign.update(id="ocid1.generativeaiapikey.oc1.ord.foreign",
                       **{"display-name": "unrelated", "freeform-tags": None})
        self.assertEqual(owned_candidates({"data": {"items": [foreign]}}, IDENTITY), ())
        del foreign["freeform-tags"]
        self.assertEqual(owned_candidates({"data": {"items": [foreign]}}, IDENTITY), ())
        foreign["display-name"] = IDENTITY["deployment_id"] + "-model"
        with self.assertRaises(DeliveryError):
            owned_candidates({"data": {"items": [foreign]}}, IDENTITY)

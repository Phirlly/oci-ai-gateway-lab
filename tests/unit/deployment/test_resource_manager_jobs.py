"""Job state and captured inputs remain independent from the current stack."""

import unittest

from deployment.credential_errors import DeliveryError
from deployment.deployment_config import FoundationConfig
from deployment.resource_manager_jobs import active_job_id, parse_job
from deployment.resource_manager_stacks import StackTarget
from .orm_fixtures import CONTROLLER, JOB_ID, KEY_ID, SETTINGS, STACK_ID, TAGS, job_data


class JobInspectionTests(unittest.TestCase):
    def setUp(self):
        self.target = StackTarget(FoundationConfig(SETTINGS), CONTROLLER)

    def test_accepted_running_and_canceling_jobs_remain_active(self):
        for state in ("ACCEPTED", "IN_PROGRESS", "CANCELING"):
            with self.subTest(state=state):
                response = {"data": [job_data(**{"lifecycle-state": state})]}
                self.assertEqual(active_job_id(response, self.target, STACK_ID), JOB_ID)

    def test_terminal_history_is_not_selected_as_active(self):
        for state in ("SUCCEEDED", "FAILED", "CANCELED"):
            with self.subTest(state=state):
                row = job_data(**{"lifecycle-state": state, "freeform-tags": None})
                self.assertIsNone(active_job_id({"data": [row]}, self.target, STACK_ID))

    def test_multiple_active_or_duplicate_jobs_fail(self):
        first = job_data(**{"lifecycle-state": "ACCEPTED"})
        for second in (first, job_data(id=JOB_ID + "2", **{"lifecycle-state": "CANCELING"})):
            with self.subTest(second=second["id"]), self.assertRaises(DeliveryError):
                active_job_id({"data": [first, second]}, self.target, STACK_ID)

    def test_wrong_stack_compartment_unknown_state_and_bad_list_fail(self):
        changes = [{"stack-id": STACK_ID + "2"}, {"compartment-id": "wrong"},
                   {"lifecycle-state": "UNKNOWN_ENUM_VALUE"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DeliveryError):
                active_job_id({"data": [job_data(**change)]}, self.target, STACK_ID)
        for response in ({}, {"data": {}}, {"data": [None]}):
            with self.subTest(response=response), self.assertRaises(DeliveryError):
                active_job_id(response, self.target, STACK_ID)

    def test_full_job_reads_its_own_captured_binding(self):
        snapshot = parse_job({"data": job_data(variables={**SETTINGS, "oci_model_key_ocid": KEY_ID})},
                             self.target, STACK_ID, JOB_ID)
        self.assertEqual(snapshot.model_key_ocid, KEY_ID)
        self.assertEqual(snapshot.operation, "APPLY")
        self.assertEqual(snapshot.state, "SUCCEEDED")
        initial = parse_job({"data": job_data()}, self.target, STACK_ID, JOB_ID)
        self.assertIsNone(initial.model_key_ocid)

    def test_exact_job_identity_ownership_operation_and_inputs_are_required(self):
        changes = [
            {"id": JOB_ID + "2"}, {"stack-id": STACK_ID + "2"},
            {"freeform-tags": {**TAGS, "operation_id": "invalid"}},
            {"freeform-tags": {**TAGS, "controller_id": "d" * 64, "operation_id": "a" * 32}},
            {"operation": "UNKNOWN"}, {"variables": {**SETTINGS, "oci_model_id": "different"}},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DeliveryError):
                parse_job({"data": job_data(**change)}, self.target, STACK_ID, JOB_ID)

"""Infrastructure observations cannot declare application readiness."""

import unittest
from unittest.mock import patch

from deployment.credential_errors import CloudReadError, DeliveryError
from deployment.deployment_config import FoundationConfig
from deployment.deployment_status import inspect_deployment
from deployment.resource_manager_stacks import StackTarget
from .orm_fixtures import CONTROLLER, JOB_ID, KEY_ID, SETTINGS, STACK_ID, ReadOnlyORM, job_data


class DeploymentStatusTests(unittest.TestCase):
    def setUp(self):
        self.client = ReadOnlyORM()
        self.target = StackTarget(FoundationConfig(SETTINGS), CONTROLLER)

    def test_no_stack_is_only_not_observed_not_authority_to_create(self):
        self.client.stacks = []
        result = inspect_deployment(self.client, self.target)
        self.assertEqual(result.summary(), {
            "infrastructure": "NOT_OBSERVED", "active_job": None,
            "requested_job": None, "demo": "NOT_VERIFIED",
        })
        self.assertEqual(len(self.client.calls), 1)

    def test_expected_stack_missing_or_different_stops(self):
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target, expected_stack_id=STACK_ID + "2")
        self.client.stacks = []
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target, expected_stack_id=STACK_ID)

    def test_wrong_client_region_and_invalid_ids_stop_before_reads(self):
        self.client.region = "us-chicago-1"
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target)
        self.assertEqual(self.client.calls, [])
        self.client.region = SETTINGS["region"]
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target, job_id="invalid")
        self.assertEqual(self.client.calls, [])

    def test_read_error_is_not_reported_as_absence(self):
        with patch.object(self.client, "list_stacks", side_effect=CloudReadError("read failed")):
            with self.assertRaises(CloudReadError):
                inspect_deployment(self.client, self.target)

    def test_canceling_job_is_observed_through_exact_get(self):
        self.client.jobs = [job_data(**{"lifecycle-state": "CANCELING"})]
        result = inspect_deployment(self.client, self.target, job_id=JOB_ID)
        self.assertEqual(result.active_job.state, "CANCELING")
        self.assertEqual(result.requested_job, result.active_job)
        self.assertEqual(self.client.calls.count(("get_job", JOB_ID)), 1)

    def test_unowned_or_conflicting_active_job_blocks_inspection(self):
        self.client.jobs = [job_data(**{"lifecycle-state": "IN_PROGRESS", "freeform-tags": {}})]
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target)
        self.client.jobs = [job_data(**{"lifecycle-state": "IN_PROGRESS"})]
        with self.assertRaises(DeliveryError):
            inspect_deployment(self.client, self.target, job_id=JOB_ID + "2")

    def test_job_finishing_between_list_and_get_is_no_longer_active(self):
        self.client.jobs = [job_data(**{"lifecycle-state": "IN_PROGRESS"})]
        with patch.object(self.client, "get_job", return_value={"data": job_data()}):
            result = inspect_deployment(self.client, self.target, job_id=JOB_ID)
        self.assertIsNone(result.active_job)
        self.assertEqual(result.requested_job.state, "SUCCEEDED")

    def test_requested_running_job_is_active_even_before_list_visibility(self):
        response = {"data": job_data(**{"lifecycle-state": "IN_PROGRESS"})}
        with patch.object(self.client, "get_job", return_value=response):
            result = inspect_deployment(self.client, self.target, job_id=JOB_ID)
        self.assertEqual(result.active_job, result.requested_job)
        self.assertEqual(result.active_job.state, "IN_PROGRESS")

    def test_successful_job_never_means_ready_or_replaces_current_binding(self):
        self.client.stacks[0]["variables"]["oci_model_key_ocid"] = KEY_ID
        self.client.jobs = [job_data(**{"failure-details": {"message": "secret-sentinel"}})]
        result = inspect_deployment(self.client, self.target, job_id=JOB_ID)
        self.assertEqual(result.stack.model_key_ocid, KEY_ID)
        self.assertIsNone(result.requested_job.model_key_ocid)
        self.assertEqual(result.summary()["demo"], "NOT_VERIFIED")
        self.assertNotIn("secret-sentinel", str(result.summary()))
        self.assertNotIn(STACK_ID, str(result.summary()))

    def test_stack_lifecycle_is_observed_without_a_vm_or_ready_claim(self):
        for state in ("CREATING", "ACTIVE", "FAILED", "DELETING", "DELETED"):
            with self.subTest(state=state):
                self.client.stacks[0]["lifecycle-state"] = state
                result = inspect_deployment(self.client, self.target)
                self.assertEqual(result.summary()["infrastructure"], state)
                self.assertEqual(result.summary()["demo"], "NOT_VERIFIED")

"""Compose read-only infrastructure observations; application checks are separate."""

from dataclasses import dataclass

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .resource_manager_jobs import ACTIVE_STATES, JobSnapshot, active_job_id, parse_job
from .resource_manager_stacks import StackSnapshot, find_stack, parse_stack


@dataclass(frozen=True, repr=False)
class DeploymentObservation:
    stack: StackSnapshot | None
    active_job: JobSnapshot | None = None
    requested_job: JobSnapshot | None = None

    def summary(self):
        def job_summary(job):
            return None if job is None else {"operation": job.operation, "state": job.state}

        return {
            "infrastructure": self.stack.state if self.stack else "NOT_OBSERVED",
            "active_job": job_summary(self.active_job),
            "requested_job": job_summary(self.requested_job),
            "demo": "NOT_VERIFIED",
        }


def inspect_deployment(client, target, *, expected_stack_id=None, job_id=None):
    """A point-in-time observation, not a lock or authorization for later writes."""
    if client.region != target.config.values["region"]:
        raise DeliveryError("Resource Manager client must use the configured hosting region.")
    if ((expected_stack_id is not None and not valid_ocid(expected_stack_id, "ormstack"))
            or (job_id is not None and not valid_ocid(job_id, "ormjob"))):
        raise DeliveryError("Invalid expected Resource Manager identifier.")
    stack_id = find_stack(client.list_stacks(target.compartment_id), target)
    if (expected_stack_id is not None and stack_id != expected_stack_id) or (job_id and stack_id is None):
        raise DeliveryError("The expected stack was not observed; no new submission is authorized.")
    if stack_id is None:
        return DeploymentObservation(None)
    stack = parse_stack(client.get_stack(stack_id), target, stack_id)
    active_id = active_job_id(client.list_jobs(target.compartment_id, stack_id), target, stack_id)
    if job_id is not None and active_id is not None and active_id != job_id:
        raise DeliveryError("Another active job must be reconciled before proceeding.")
    selected = parse_job(client.get_job(active_id), target, stack_id, active_id) if active_id else None
    active = selected if selected and selected.state in ACTIVE_STATES else None
    requested = selected if job_id is not None and job_id == active_id else None
    if job_id is not None and requested is None:
        requested = parse_job(client.get_job(job_id), target, stack_id, job_id)
        if requested.state in ACTIVE_STATES:
            active = requested
    return DeploymentObservation(stack, active, requested)

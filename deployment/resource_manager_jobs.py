"""Read-only job observations, including the job's captured variables."""

import re
from dataclasses import dataclass

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid

ACTIVE_STATES = {"ACCEPTED", "IN_PROGRESS", "CANCELING"}
JOB_STATES = ACTIVE_STATES | {"SUCCEEDED", "FAILED", "CANCELED"}
JOB_OPERATIONS = {"PLAN", "APPLY", "DESTROY", "IMPORT_TF_STATE", "PLAN_ROLLBACK", "APPLY_ROLLBACK"}


@dataclass(frozen=True, repr=False)
class JobSnapshot:
    job_id: str
    state: str
    operation: str
    operation_id: str
    model_key_ocid: str | None


def active_job_id(response, target, stack_id):
    try:
        rows = response["data"]
        if not isinstance(rows, list):
            raise ValueError
        seen, active = set(), []
        for row in rows:
            job_id, state = row["id"], row["lifecycle-state"]
            if (not valid_ocid(job_id, "ormjob") or job_id in seen
                    or row["stack-id"] != stack_id
                    or row["compartment-id"] != target.compartment_id
                    or state not in JOB_STATES):
                raise ValueError
            seen.add(job_id)
            if state in ACTIVE_STATES:
                active.append(job_id)
        if len(active) > 1:
            raise ValueError
        return active[0] if active else None
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("Job discovery has malformed or conflicting active jobs.") from None


def parse_job(response, target, stack_id, expected_id):
    try:
        data = response["data"]
        operation_id = data["freeform-tags"]["operation_id"]
        if (not valid_ocid(expected_id, "ormjob") or data["id"] != expected_id
                or data["stack-id"] != stack_id or not target.owns(data)
                or data["lifecycle-state"] not in JOB_STATES
                or data["operation"] not in JOB_OPERATIONS
                or not isinstance(operation_id, str)
                or re.fullmatch(r"[a-f0-9]{32}", operation_id) is None):
            raise ValueError
        binding = target.config.read_binding(data["variables"])
        return JobSnapshot(expected_id, data["lifecycle-state"], data["operation"], operation_id, binding)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError("Exact owned job metadata could not be verified.") from None

"""Synthetic Resource Manager data, separate from credential-version fixtures."""

from copy import deepcopy

SETTINGS = {
    "tenancy_ocid": "ocid1.tenancy.oc1..example",
    "compartment_ocid": "ocid1.compartment.oc1..example",
    "region": "us-ashburn-1",
    "deployment_id": "gateway-test",
    "oci_model_id": "example.chat-model",
}
CONTROLLER = "c" * 64
STACK_ID = "ocid1.ormstack.oc1.iad.example"
JOB_ID = "ocid1.ormjob.oc1.iad.example"
KEY_ID = "ocid1.generativeaiapikey.oc1.ord.example"
TAGS = {"solution": "oci-ai-gateway-lab", "deployment_id": "gateway-test",
        "controller_id": CONTROLLER}


def stack_data(**changes):
    data = {
        "id": STACK_ID, "compartment-id": SETTINGS["compartment_ocid"],
        "display-name": "gateway-test", "freeform-tags": dict(TAGS),
        "lifecycle-state": "ACTIVE", "variables": dict(SETTINGS),
    }
    data.update(changes)
    return data


def job_data(**changes):
    data = {
        "id": JOB_ID, "stack-id": STACK_ID,
        "compartment-id": SETTINGS["compartment_ocid"],
        "freeform-tags": {**TAGS, "operation_id": "a" * 32},
        "lifecycle-state": "SUCCEEDED", "operation": "APPLY",
        "variables": dict(SETTINGS),
    }
    data.update(changes)
    return data


class ReadOnlyORM:
    region = SETTINGS["region"]

    def __init__(self):
        self.stacks = [stack_data()]
        self.jobs = []
        self.calls = []

    def list_stacks(self, compartment_id):
        self.calls.append(("list_stacks", compartment_id))
        return {"data": deepcopy(self.stacks)}

    def get_stack(self, stack_id):
        self.calls.append(("get_stack", stack_id))
        return {"data": deepcopy(self.stacks[0]), "etag": "stack-version"}

    def list_jobs(self, compartment_id, stack_id):
        self.calls.append(("list_jobs", compartment_id, stack_id))
        return {"data": deepcopy(self.jobs)}

    def get_job(self, job_id):
        self.calls.append(("get_job", job_id))
        return {"data": deepcopy(next(row for row in self.jobs if row["id"] == job_id))}

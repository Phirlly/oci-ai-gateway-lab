"""Fixed Resource Manager reads and journal-controlled submission commands."""

from .oci_cli import OCICommand
from .resource_manager_download import download_job_package


class ResourceManagerCLI(OCICommand):
    def list_stacks(self, compartment_id):
        return self.request(("resource-manager", "stack", "list", "--all"),
                            {"compartmentId": compartment_id}, empty_list=True)

    def get_stack(self, stack_id):
        return self.request(("resource-manager", "stack", "get"), {"stackId": stack_id})

    def list_jobs(self, compartment_id, stack_id):
        return self.request(("resource-manager", "job", "list", "--all"),
                            {"compartmentId": compartment_id, "stackId": stack_id}, empty_list=True)

    def get_job(self, job_id):
        return self.request(("resource-manager", "job", "get"), {"jobId": job_id})

    def create_stack(self, payload):
        return self.request(("resource-manager", "stack", "create"), payload, mutation=True)

    def update_stack(self, payload):
        return self.request(("resource-manager", "stack", "update", "--force"), payload, mutation=True)

    def create_apply(self, payload):
        return self.request(("resource-manager", "job", "create-apply-job"), payload, mutation=True)

    def get_job_package(self, job_id):
        return download_job_package(self, job_id)

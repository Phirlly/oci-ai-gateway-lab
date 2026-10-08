"""Fixed Resource Manager reads; infrastructure mutations are not exposed here."""

from .oci_cli import OCICommand


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

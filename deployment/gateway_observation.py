"""Read attested infrastructure and runtime identity without invoking any model."""

from dataclasses import dataclass

from .cloud_context import resolve_runtime_context
from .credential_errors import DeliveryError
from .removed_state import require_no_managed_resources
from .resource_manager_jobs import JobSnapshot
from .resource_manager_stacks import find_stack
from .submission_recovery import reconcile_jobs, submission_scope, verified_stack


@dataclass(frozen=True, repr=False)
class GatewayObservation:
    phase: str
    stack_id: str | None = None
    job: JobSnapshot | None = None
    context: dict | None = None


def observe_gateway(client, journal, target, package, compute):
    scope = submission_scope(client, journal, target, package)
    intents = journal.read(scope)
    stack_id = find_stack(client.list_stacks(target.compartment_id), target)
    if stack_id is None:
        if intents:
            raise DeliveryError('Recorded deployment was not observed; reconcile retained history.')
        return GatewayObservation('NOT_DEPLOYED')
    response = client.get_stack(stack_id)
    stack = verified_stack(response, target, stack_id, intents)
    if any(item.package_hash != package.digest for item in intents):
        raise DeliveryError('Deployment history no longer matches its original package.')
    if stack.state != 'ACTIVE':
        return GatewayObservation('STACK_' + stack.state, stack_id)
    jobs = reconcile_jobs(client, target, stack_id, intents)
    selected = [job for operation, job in jobs.items() if any(
        item.operation_id == operation and item.request_hash == response['data']['freeform-tags'].get('request_hash')
        for item in intents)]
    if not selected:
        if jobs:
            raise DeliveryError('Current stack request has no attested job.')
        return GatewayObservation('STACK_ACTIVE', stack_id)
    # One retry has the same request hash; select its recorded latest operation.
    from .apply_attempts import latest_applies
    latest_ids = {item.operation_id for item in latest_applies(intents).values()}
    selected = [job for job in selected if job.operation == 'DESTROY' or job.operation_id in latest_ids]
    if len(selected) != 1:
        raise DeliveryError('Current infrastructure job is ambiguous.')
    job = selected[0]
    if (stack.model_key_ocid != job.model_key_ocid
            or response['data']['freeform-tags'].get('package_hash') != package.digest):
        raise DeliveryError('Current stack binding or package differs from its attested job.')
    if job.operation == 'DESTROY':
        if job.state == 'SUCCEEDED':
            package.verify(client.get_job_package(job.job_id))
            require_no_managed_resources(client.get_job_state(job.job_id))
            return GatewayObservation('REMOVED', stack_id, job)
        return GatewayObservation('DESTROY_' + job.state, stack_id, job)
    if any(item.kind in ('cleanup-start', 'cleanup-complete') for item in intents):
        return GatewayObservation('CLEANUP_STARTED', stack_id, job)
    if job.state != 'SUCCEEDED':
        return GatewayObservation('APPLY_' + job.state, stack_id, job)
    package.verify(client.get_job_package(job.job_id))
    context = resolve_runtime_context(compute, client.list_job_resources(job.job_id, target.compartment_id), target.config)
    return GatewayObservation('DEPLOYED' if job.model_key_ocid else 'CREDENTIALS_NOT_BOUND', stack_id, job, context)

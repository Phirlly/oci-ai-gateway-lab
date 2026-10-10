"""Recover base resource identity without clearing a later permission binding."""

from .apply_attempts import latest_applies
from .credential_errors import DeliveryError
from .resource_manager_jobs import ACTIVE_STATES
from .submission_records import apply_request_hash
from .submission_recovery import reconcile_jobs, submission_scope, verified_stack


def recover_base(client, journal, target, package, stack_id):
    """Historical base success is identity evidence, never permission evidence."""
    scope = submission_scope(client, journal, target, package)
    intents = journal.read(scope)
    if any(intent.kind in ('cleanup-start', 'cleanup-complete') for intent in intents):
        raise DeliveryError('Cleanup is recorded; credential preparation must stop.')
    if any(intent.kind == 'destroy' for intent in intents):
        raise DeliveryError('Destroy is recorded; credential preparation must stop.')
    response = client.get_stack(stack_id)
    stack = verified_stack(response, target, stack_id, intents)
    if stack.state != 'ACTIVE':
        raise DeliveryError('Foundation history requires an ACTIVE stack.')
    jobs = reconcile_jobs(client, target, stack_id, intents)
    current_hash = apply_request_hash(
        stack_id, target.config.orm_variables(model_key_ocid=stack.model_key_ocid), package.digest,
    )
    tags = response['data']['freeform-tags']
    attempts = latest_applies(intents)
    current = attempts.get(current_hash)
    if (current is None or tags.get('request_hash') != current_hash
            or tags.get('package_hash') != package.digest):
        raise DeliveryError('Current foundation request is unverified; explicit recovery is required.')
    if any(job.state in ACTIVE_STATES and operation != current.operation_id
           for operation, job in jobs.items()):
        raise DeliveryError('Another active job blocks credential preparation.')
    base_hash = apply_request_hash(
        stack_id, target.config.orm_variables(model_key_ocid=None), package.digest,
    )
    selected = attempts.get(base_hash)
    if selected is None:
        raise DeliveryError('A recorded base Apply is required.')
    base = jobs[selected.operation_id]
    if base.state != 'SUCCEEDED':
        raise DeliveryError('Base Apply must succeed before credential preparation.')
    package.verify(client.get_job_package(base.job_id))
    return stack, base

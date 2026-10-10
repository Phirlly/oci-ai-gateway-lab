"""Retain cleanup authority before Destroy; never depend on the guest VM."""

from dataclasses import dataclass

from .apply_attempts import latest_applies
from .cleanup_keys import cleanup_keys
from .cleanup_vault import CleanupVault
from .credential_errors import DeliveryError
from .destroy_submission import ensure_destroy
from .foundation_resources import vault_target
from .resource_manager_jobs import ACTIVE_STATES, JobSnapshot
from .resource_manager_stacks import find_stack
from .submission_records import apply_request_hash, digest
from .submission_recovery import reconcile_jobs, submission_scope, verified_stack


@dataclass(frozen=True, repr=False)
class RemovalProgress:
    phase: str
    stack_id: str
    job: JobSnapshot | None = None


def _record(journal, scope, intents, kind, request_hash, package_hash):
    found = [item for item in intents if item.kind == kind]
    if found:
        if len(found) != 1 or found[0].request_hash != request_hash or found[0].package_hash != package_hash:
            raise DeliveryError('Retained cleanup authority conflicts with the original deployment.')
        return found[0]
    return journal.submit(scope, kind, request_hash, package_hash, lambda intent: intent)


def advance_removal(client, journal, target, package, *, vault, keys, inference_region):
    scope = submission_scope(client, journal, target, package)
    intents = journal.read(scope)
    stack_id = find_stack(client.list_stacks(target.compartment_id), target)
    if stack_id is None:
        raise DeliveryError('Owned stack is not observed; retained history must be reconciled.')
    stack = verified_stack(client.get_stack(stack_id), target, stack_id, intents)
    if stack.state != 'ACTIVE' or any(item.package_hash != package.digest for item in intents):
        raise DeliveryError('Remove requires an ACTIVE original stack and unchanged package history.')
    jobs = reconcile_jobs(client, target, stack_id, intents)
    destroying = any(item.kind == 'destroy' for item in intents)
    active = [job for job in jobs.values() if job.state in ACTIVE_STATES]
    if active and not destroying:
        return RemovalProgress('WAIT_FOR_INFRASTRUCTURE', stack_id, active[0])
    variables = target.config.orm_variables(model_key_ocid=stack.model_key_ocid)
    start_hash = digest({'operation': 'CLEANUP', 'stack_id': stack_id, 'variables': variables,
                         'package_hash': package.digest, 'inference_region': inference_region})
    starts = [item for item in intents if item.kind == 'cleanup-start']
    completions = [item for item in intents if item.kind == 'cleanup-complete']
    if (destroying or completions) and not starts:
        raise DeliveryError('Remove cannot invent cleanup authority for an older Destroy.')
    start = _record(journal, scope, intents, 'cleanup-start', start_hash, package.digest)
    complete_hash = digest({'operation': 'CLEANUP_COMPLETE', 'start_operation_id': start.operation_id,
                            'request_hash': start_hash})
    if completions:
        _record(journal, scope, intents, 'cleanup-complete', complete_hash, package.digest)
    else:
        if destroying:
            raise DeliveryError('Destroy has no verified key-cleanup receipt; explicit recovery is required.')
        base_hash = apply_request_hash(stack_id, target.config.orm_variables(model_key_ocid=None), package.digest)
        base = latest_applies(intents).get(base_hash)
        successful = base is not None and jobs[base.operation_id].state == 'SUCCEEDED'
        if successful:
            if vault is None or keys is None or vault.region != target.config.values['region']:
                raise DeliveryError('Owned credential history requires the hosting Vault and inference key clients.')
            job = jobs[base.operation_id]
            package.verify(client.get_job_package(job.job_id))
            destination = vault_target(client.list_job_resources(job.job_id, target.compartment_id),
                                       target.config, stack_id, inference_region)
            store = CleanupVault(vault, destination, start.operation_id)
            if not cleanup_keys(keys, store, package_hash=package.digest,
                                config_hash=digest(dict(target.config.values))):
                return RemovalProgress('KEY_DELETION_PENDING', stack_id)
        elif stack.model_key_ocid is not None or any(job.model_key_ocid is not None for job in jobs.values()):
            raise DeliveryError('A derived key binding without a successful base needs explicit recovery.')
        # No successful base means this controller could never prepare credentials.
        _record(journal, scope, intents, 'cleanup-complete', complete_hash, package.digest)
    job = ensure_destroy(client, journal, target, package, stack_id)
    return RemovalProgress('DESTROY', stack_id, job)

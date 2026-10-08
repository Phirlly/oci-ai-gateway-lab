"""Submit one owned-stack Destroy after caller-controlled model-key cleanup."""

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .resource_manager_jobs import ACTIVE_STATES
from .resource_manager_stacks import find_stack
from .submission_records import destroy_request_hash
from .submission_recovery import reconcile_jobs, submission_scope, verified_job, verified_stack
from .submission_upload import upload_inputs


def ensure_destroy(client, journal, target, package, stack_id):
    """Caller proves keys removed or never attempted; job success is not total removal."""
    scope = submission_scope(client, journal, target, package)
    intents = journal.read(scope)
    if (not valid_ocid(stack_id, 'ormstack')
            or find_stack(client.list_stacks(target.compartment_id), target) != stack_id):
        raise DeliveryError('Expected owned stack was not observed; no Destroy is authorized.')
    response = client.get_stack(stack_id)
    stack = verified_stack(response, target, stack_id, intents)
    if stack.state != 'ACTIVE':
        raise DeliveryError('Stack must be ACTIVE before Destroy reconciliation.')
    variables = target.config.orm_variables(model_key_ocid=stack.model_key_ocid)
    jobs = reconcile_jobs(client, target, stack_id, intents)
    request_hash = destroy_request_hash(stack_id, variables, package.digest)
    selected = [intent for intent in intents if intent.kind == 'destroy']
    if selected:
        if len(selected) != 1 or selected[0].request_hash != request_hash:
            raise DeliveryError('Existing Destroy inputs differ; explicit recovery is required.')
        job = jobs[selected[0].operation_id]
        tags = response['data']['freeform-tags']
        if tags.get('request_hash') != request_hash or tags.get('package_hash') != package.digest:
            raise DeliveryError('Recorded Destroy was superseded; explicit recovery is required.')
        if any(other.state in ACTIVE_STATES and other.job_id != job.job_id for other in jobs.values()):
            raise DeliveryError('Another active job blocks Destroy reconciliation.')
        return job
    if any(job.state in ACTIVE_STATES for job in jobs.values()):
        raise DeliveryError('An active job must finish before Destroy.')

    def submit(intent):
        tags = {**response['data']['freeform-tags'], **target.tags,
                'request_hash': request_hash, 'package_hash': package.digest}
        upload_inputs(client, target, package, stack, intents, variables, tags)
        created = client.create_destroy({
            'stackId': stack_id, 'executionPlanStrategy': 'AUTO_APPROVED',
            'jobOperationDetailsIsProviderUpgradeRequired': False,
            'freeformTags': {**target.tags, 'operation_id': intent.operation_id,
                             'request_hash': request_hash, 'package_hash': package.digest},
        })
        try:
            identifier = created['data']['id']
            if not valid_ocid(identifier, 'ormjob'):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise DeliveryError('Destroy response is unverified; recover its recorded intent.') from None
        return verified_job(client, target, stack_id, identifier, intent)

    return journal.submit(scope, 'destroy', request_hash, package.digest, submit)

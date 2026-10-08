"""Upload exact inputs once per recorded Apply; recover instead of resubmitting."""

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .resource_manager_jobs import ACTIVE_STATES
from .resource_manager_stacks import find_stack
from .submission_records import apply_request_hash
from .submission_recovery import reconcile_jobs, submission_scope, verified_job, verified_stack
from .submission_upload import upload_inputs


def ensure_apply(client, journal, target, package, stack_id, *, model_key_ocid):
    """Caller must establish key authority before supplying a derived binding."""
    scope = submission_scope(client, journal, target, package)
    variables = target.config.orm_variables(model_key_ocid=model_key_ocid)
    intents = journal.read(scope)
    if any(intent.kind == 'destroy' for intent in intents):
        raise DeliveryError('Destroy is recorded; this deployment cannot submit another Apply.')
    if (not valid_ocid(stack_id, 'ormstack')
            or find_stack(client.list_stacks(target.compartment_id), target) != stack_id):
        raise DeliveryError('Expected stack was not observed; no Apply is authorized.')
    response = client.get_stack(stack_id)
    stack = verified_stack(response, target, stack_id, intents)
    if stack.state != 'ACTIVE':
        raise DeliveryError('Stack must be ACTIVE before Apply reconciliation.')
    if stack.model_key_ocid is not None and stack.model_key_ocid != model_key_ocid:
        raise DeliveryError('Existing model-key binding must be preserved.')
    jobs = reconcile_jobs(client, target, stack_id, intents)
    request_hash = apply_request_hash(stack_id, variables, package.digest)
    selected = [i for i in intents if i.kind == 'apply' and i.request_hash == request_hash]
    if len(selected) > 1:
        raise DeliveryError('Duplicate Apply intents require reconciliation.')

    def result(job):
        if job.state == 'SUCCEEDED':
            package.verify(client.get_job_package(job.job_id))
        return job

    if selected:
        requested = jobs[selected[0].operation_id]
        tags = response['data']['freeform-tags']
        if (tags.get('request_hash') != request_hash or tags.get('package_hash') != package.digest
                or response['data']['variables'] != variables):
            raise DeliveryError('A later stack update superseded this request; explicit recovery is required.')
        if any(job.state in ACTIVE_STATES and job.job_id != requested.job_id for job in jobs.values()):
            raise DeliveryError('Another active submission must finish first.')
        return result(requested)
    if any(job.state in ACTIVE_STATES for job in jobs.values()):
        raise DeliveryError('An active submission must finish before new work.')

    def submit(intent):
        tags = {**response['data']['freeform-tags'], **target.tags,
                'request_hash': request_hash, 'package_hash': package.digest}
        upload_inputs(client, target, package, stack, intents, variables, tags)
        created = client.create_apply({
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
            raise DeliveryError('Apply response is unverified; recover its recorded intent.') from None
        return result(verified_job(client, target, stack_id, identifier, intent))

    return journal.submit(scope, 'apply', request_hash, package.digest, submit)

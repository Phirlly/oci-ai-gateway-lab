"""Validate persisted submission identity against exact Resource Manager reads."""

from .apply_attempts import latest_applies
from .credential_errors import DeliveryError
from .foundation_package import FoundationPackage
from .resource_manager_jobs import active_job_id, parse_job
from .resource_manager_stacks import parse_stack
from .submission_records import apply_request_hash, destroy_request_hash, digest, target_identity


def submission_scope(client, journal, target, package):
    if (client.region != target.config.values['region']
            or journal.controller_id != target.controller_id
            or not isinstance(package, FoundationPackage)):
        raise DeliveryError('Submission controller, region or package is inconsistent.')
    return target_identity(target.config)


def stack_request_hash(target, package_hash):
    return digest({'variables': target.config.orm_variables(model_key_ocid=None),
                   'package_hash': package_hash, 'terraform_version': '1.5.x',
                   'working_directory': 'foundation'})


def verified_stack(response, target, stack_id, intents):
    snapshot = parse_stack(response, target, stack_id)
    creates = [intent for intent in intents if intent.kind == 'create-stack']
    data = response['data']
    source = data.get('config-source')
    tags = data['freeform-tags']
    if (len(creates) != 1 or not isinstance(source, dict)
            or source.get('config-source-type') != 'ZIP_UPLOAD'
            or source.get('working-directory') != 'foundation'
            or data.get('terraform-version') != '1.5.x'
            or data.get('custom-terraform-provider') is not None
            or type(data.get('is-third-party-provider-experience-enabled')) not in (bool, type(None))
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tags.items())):
        raise DeliveryError('Stack source or retained creation intent could not be verified.')
    creation = creates[0]
    if (tags.get('creation_operation_id') != creation.operation_id
            or creation.request_hash != stack_request_hash(target, creation.package_hash)):
        raise DeliveryError('Stack creation identity conflicts with its journal.')
    return snapshot


def verified_job(client, target, stack_id, job_id, intent):
    if intent.kind not in ('apply', 'destroy'):
        raise DeliveryError('Recorded operation is not a supported infrastructure job.')
    response = client.get_job(job_id)
    job = parse_job(response, target, stack_id, job_id)
    data = response['data']
    source = data.get('config-source')
    tags = data['freeform-tags']
    request_hash = apply_request_hash if intent.kind == 'apply' else destroy_request_hash
    if (job.operation != intent.kind.upper() or job.operation_id != intent.operation_id
            or tags.get('request_hash') != intent.request_hash
            or tags.get('package_hash') != intent.package_hash
            or not isinstance(source, dict) or source.get('config-source-record-type') != 'ZIP_UPLOAD'
            or data.get('working-directory') != 'foundation'
            or data.get('is-provider-upgrade-required') is not False
            or type(data.get('is-third-party-provider-experience-enabled')) not in (bool, type(None))
            or request_hash(stack_id, data['variables'], intent.package_hash) != intent.request_hash):
        raise DeliveryError('Job inputs conflict with the recorded submission.')
    return job


def reconcile_jobs(client, target, stack_id, intents):
    latest_applies(intents)
    response = client.list_jobs(target.compartment_id, stack_id)
    active = active_job_id(response, target, stack_id)
    records = {intent.operation_id: intent for intent in intents if intent.kind in ('apply', 'destroy')}
    candidates = {}
    for row in response['data']:
        tags = row.get('freeform-tags') or {}
        if not isinstance(tags, dict):
            raise DeliveryError('Malformed job ownership.')
        operation = tags.get('operation_id')
        if operation is not None and not isinstance(operation, str):
            raise DeliveryError('Malformed job operation identity.')
        if target.owns(row) and operation not in records:
            raise DeliveryError('Owned job has no retained submission record.')
        if operation in records:
            if operation in candidates:
                raise DeliveryError('Multiple jobs match one submission record.')
            candidates[operation] = row['id']
    if set(candidates) != set(records):
        raise DeliveryError('Recorded job was not observed; no new submission is authorized.')
    jobs = {operation: verified_job(client, target, stack_id, job_id, records[operation])
            for operation, job_id in candidates.items()}
    for intent in records.values():
        if intent.retry_of is not None and jobs[intent.retry_of].state != 'FAILED':
            raise DeliveryError('Apply retry requires its original job to remain FAILED.')
    if active and active not in candidates.values():
        raise DeliveryError('An unrelated active job blocks submission.')
    return jobs

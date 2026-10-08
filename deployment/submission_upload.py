"""Shared exact configuration upload/readback before a recorded job submission."""

from .credential_errors import DeliveryError
from .resource_manager_jobs import ACTIVE_STATES
from .submission_recovery import reconcile_jobs, verified_stack


def upload_inputs(client, target, package, stack, intents, variables, tags):
    with package.path() as path:
        client.update_stack({
            'stackId': stack.stack_id, 'ifMatch': stack.etag, 'configSource': str(path),
            'workingDirectory': 'foundation', 'terraformVersion': '1.5.x',
            'variables': variables, 'freeformTags': tags,
        })
    response = client.get_stack(stack.stack_id)
    updated = verified_stack(response, target, stack.stack_id, intents)
    if (updated.state != 'ACTIVE' or updated.etag == stack.etag
            or response['data']['variables'] != variables
            or response['data']['freeform-tags'] != tags):
        raise DeliveryError('Updated stack was not confirmed; recover before submission.')
    jobs = reconcile_jobs(client, target, stack.stack_id, intents)
    if any(job.state in ACTIVE_STATES for job in jobs.values()):
        raise DeliveryError('Active job appeared before submission.')

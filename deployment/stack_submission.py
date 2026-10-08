"""Create one foundation stack after durable intent, or recover that stack."""

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .resource_manager_stacks import find_stack
from .submission_recovery import stack_request_hash, submission_scope, verified_stack


def ensure_stack(client, journal, target, package):
    scope = submission_scope(client, journal, target, package)
    intents = journal.read(scope)
    stack_id = find_stack(client.list_stacks(target.compartment_id), target)
    if stack_id is not None:
        return verified_stack(client.get_stack(stack_id), target, stack_id, intents)
    if intents:
        raise DeliveryError('Recorded stack was not observed; recover before creating anything.')

    def create(intent):
        with package.path() as path:
            response = client.create_stack({
                'compartmentId': target.compartment_id,
                'displayName': target.config.values['deployment_id'],
                'configSource': str(path), 'workingDirectory': 'foundation',
                'terraformVersion': '1.5.x',
                'variables': target.config.orm_variables(model_key_ocid=None),
                'freeformTags': {**target.tags, 'creation_operation_id': intent.operation_id},
            })
        try:
            identifier = response['data']['id']
            if not valid_ocid(identifier, 'ormstack'):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise DeliveryError('Stack submission response is unverified; recover its intent.') from None
        return verified_stack(client.get_stack(identifier), target, identifier, [intent])

    return journal.submit(scope, 'create-stack', stack_request_hash(target, package.digest),
                          package.digest, create)

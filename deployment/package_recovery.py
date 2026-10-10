"""Use an existing deployment's original attested archive, never today's build."""

from .credential_errors import DeliveryError
from .foundation_package import FoundationPackage
from .resource_manager_stacks import find_stack
from .submission_records import target_identity
from .submission_recovery import verified_stack


def deployment_package(client, journal, target, build):
    if (client.region != target.config.values["region"]
            or journal.controller_id != target.controller_id):
        raise DeliveryError("Deployment controller or region does not match.")
    intents = journal.read(target_identity(target.config))
    stack_id = find_stack(client.list_stacks(target.compartment_id), target)
    if stack_id is None:
        if intents:
            raise DeliveryError("Recorded stack was not observed; recover before building a new deployment.")
        return build()
    verified_stack(client.get_stack(stack_id), target, stack_id, intents)
    creation = next(item for item in intents if item.kind == "create-stack")
    if any(item.package_hash != creation.package_hash for item in intents):
        raise DeliveryError("Deployment history contains different packages; explicit recovery is required.")
    package = FoundationPackage(client.get_stack_package(stack_id))
    if package.digest != creation.package_hash:
        raise DeliveryError("Stack archive differs from the original recorded deployment package.")
    return package

"""Select the original Apply or its single same-input recovery attempt."""

from .credential_errors import DeliveryError


def latest_applies(intents):
    groups = {}
    for intent in intents:
        if intent.kind == 'apply':
            groups.setdefault(intent.request_hash, []).append(intent)
    selected = {}
    for request, attempts in groups.items():
        originals = [i for i in attempts if i.retry_of is None]
        retries = [i for i in attempts if i.retry_of is not None]
        if len(originals) != 1 or len(retries) > 1:
            raise DeliveryError('Apply history requires one original and at most one retry.')
        original = originals[0]
        selected[request] = original
        if retries:
            retry = retries[0]
            if (retry.retry_of != original.operation_id
                    or (retry.controller_id, retry.target_hash, retry.package_hash)
                    != (original.controller_id, original.target_hash, original.package_hash)):
                raise DeliveryError('Apply retry does not match its original submission.')
            selected[request] = retry
    return selected

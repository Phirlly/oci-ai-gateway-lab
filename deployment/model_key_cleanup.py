"""Delete proven-owned keys; preserve unknown outcomes and unrelated resources."""

from dataclasses import dataclass

from .credential_errors import DeliveryError, MutationUncertain
from .credential_identity import valid_identity, valid_ocid
from .model_key_state import RESOURCE_STATES, owned_candidates


@dataclass(frozen=True, repr=False)
class KeyCleanupObservation:
    removed: tuple
    pending: tuple
    not_observed: tuple

    @property
    def phase(self):
        if self.pending or self.not_observed:
            return 'UNRESOLVED'
        return 'KEYS_REMOVED' if self.removed else 'NO_KEYS_OBSERVED'


def cleanup_candidates(response, identity):
    try:
        data = response['data']
        rows = data['items']
        if (not isinstance(rows, list) or len(rows) > 256
                or any(container.get(name) for container in (response, data)
                       for name in ('opc-next-page', 'opc-next-cursor', 'next-page'))):
            raise ValueError
        identifiers = owned_candidates(response, identity)
        return {row['id']: row for row in rows if row['id'] in identifiers}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError('Complete model-key cleanup discovery could not be verified.') from None


def exact_cleanup_key(client, identity, identifier, expected):
    response = client.get(identifier)
    try:
        row, etag = response['data'], response['etag']
        if (owned_candidates({'data': {'items': [row]}}, identity) != (identifier,)
                or row['freeform-tags']['operation_id'] != expected['freeform-tags']['operation_id']
                or row['lifecycle-state'] not in RESOURCE_STATES
                or not isinstance(etag, str) or not etag):
            raise ValueError
        return row['lifecycle-state'], etag
    except (KeyError, TypeError, ValueError):
        raise DeliveryError('Exact key ownership or deletion state could not be verified.') from None


def remove_model_keys(client, identity, *, known_key_ids=()):
    """Caller supplies verified saved identity; absence cannot resolve a lost create."""
    if (not valid_identity(identity) or client.region != identity['inference_region']
            or not isinstance(known_key_ids, (tuple, list, set, frozenset))
            or len(known_key_ids) > 256
            or any(not valid_ocid(value, 'generativeaiapikey') for value in known_key_ids)):
        raise DeliveryError('Verified cleanup identity, key IDs and inference region are required.')
    candidates = cleanup_candidates(client.list(identity['compartment_ocid']), identity)
    snapshots = {identifier: exact_cleanup_key(client, identity, identifier, row)
                 for identifier, row in candidates.items()}
    removed, pending = [], []
    for identifier, (state, etag) in snapshots.items():
        if state == 'DELETING':
            pending.append(identifier)
            continue
        if state != 'DELETED':
            try:
                # The fixed adapter returns only after exact DELETED/404 readback.
                client.delete(identifier, etag)
            except MutationUncertain:
                observed, _ = exact_cleanup_key(client, identity, identifier, candidates[identifier])
                if observed != 'DELETED':
                    pending.append(identifier)
                    continue
        removed.append(identifier)
    return KeyCleanupObservation(tuple(sorted(removed)), tuple(sorted(pending)),
                                 tuple(sorted(set(known_key_ids) - set(candidates))))

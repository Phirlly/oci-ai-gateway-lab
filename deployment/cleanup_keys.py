"""Delete only manifest-owned keys, saving terminal evidence before Destroy."""

from .cleanup_records import encoded, key_receipt, legacy_receipt_name, manifest_context, parse_manifest
from .credential_errors import DeliveryError, MutationUncertain
from .model_key_cleanup import cleanup_candidates, exact_cleanup_key


def cleanup_keys(client, store, *, package_hash, config_hash):
    identity = dict(store.target.identity)
    if client.region != identity['inference_region']:
        raise DeliveryError('Cleanup key client must use the original inference region.')
    history = store.read()
    context = manifest_context(store, package_hash, config_hash)
    name = 'cleanup-' + store.operation
    candidates = cleanup_candidates(client.list(identity['compartment_ocid']), identity)
    known = {record.model_key_ocid: record.operation_id for record in history.records if record.model_key_ocid}
    if name in history.documents:
        manifest = parse_manifest(history.documents[name], context)
    else:
        # Exact GET can recover a retained DELETED key omitted by LIST.
        for identifier in known.keys() - candidates.keys():
            candidates[identifier] = client.get(identifier)['data']
        if len(candidates) > 16:
            raise DeliveryError('Too many owned keys for bounded cleanup; explicit recovery is required.')
        for identifier, row in candidates.items():
            exact_cleanup_key(client, identity, identifier, row)
        entries = [{'key_id': identifier, 'operation_id': row['freeform-tags']['operation_id']}
                   for identifier, row in sorted(candidates.items())]
        manifest = parse_manifest(encoded({**context, 'keys': entries}), context)
    owned = {row['key_id']: row['operation_id'] for row in manifest['keys']}
    operations = {record.operation_id for record in history.records}
    if (not candidates.keys() <= owned.keys() or any(owned.get(k) != v for k, v in known.items())
            or not operations <= set(owned.values())):
        raise DeliveryError('Owned key creation or changed cleanup inventory remains unresolved.')
    receipts = {identifier: key_receipt(store, manifest, identifier) for identifier in owned}
    aliases = {identifier: {receipt[0], legacy_receipt_name(store, identifier)}
               for identifier, receipt in receipts.items()}
    allowed_names = {name} | {alias for names in aliases.values() for alias in names}
    if not history.documents.keys() <= allowed_names:
        raise DeliveryError('Unexpected cleanup evidence requires explicit recovery.')
    for identifier, names in aliases.items():
        for receipt_name in names:
            if receipt_name in history.documents and history.documents[receipt_name] != receipts[identifier][1]:
                raise DeliveryError('Saved key-removal evidence conflicts with its manifest.')
    # All identities are read/verified before the first deletion.
    snapshots = {}
    for identifier, operation in owned.items():
        if not aliases[identifier] & history.documents.keys():
            snapshots[identifier] = exact_cleanup_key(
                client, identity, identifier, {'freeform-tags': {'operation_id': operation}})
    store.save(name, encoded(manifest))
    complete = True
    for identifier, (state, etag) in snapshots.items():
        if state == 'DELETING':
            complete = False
            continue
        if state != 'DELETED':
            try:
                client.delete(identifier, etag)
            except MutationUncertain:
                # A later404 is ambiguous and remains a sanitized read failure.
                state, _ = exact_cleanup_key(client, identity, identifier,
                                            {'freeform-tags': {'operation_id': owned[identifier]}})
                if state != 'DELETED':
                    complete = False
                    continue
        store.save(*receipts[identifier])
    return complete

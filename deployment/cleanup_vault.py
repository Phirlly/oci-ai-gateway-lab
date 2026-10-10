"""Read cleanup history and retain private named evidence without moving CURRENT."""

import re
from dataclasses import dataclass

from .credential_errors import DeliveryError, MutationUncertain
from .credential_records import MAX_RECORD_BYTES, parse_record
from .vault_state import read_secret_metadata, read_version_content


@dataclass(frozen=True, repr=False)
class CleanupHistory:
    etag: str
    current_number: int
    records: tuple
    documents: dict


class CleanupVault:
    def __init__(self, client, target, operation):
        if not isinstance(operation, str) or re.fullmatch('[a-f0-9]{32}', operation) is None:
            raise DeliveryError('Cleanup requires its recorded operation identity.')
        self.client, self.target, self.operation = client, target, operation

    def _document_name(self, name):
        return (name == 'cleanup-' + self.operation
                or re.fullmatch('removed-[a-f0-9]{32}', name)
                or re.fullmatch('removed-' + self.operation + '-[a-f0-9]{32}', name))

    def read(self):
        etag, current = read_secret_metadata(self.client, self.target)
        response = self.client.versions(self.target.secret_id)
        try:
            rows = response['data']
            if (not isinstance(rows, list) or not 1 <= len(rows) <= 64
                    or any(response.get(k) for k in ('opc-next-page', 'opc-next-cursor', 'next-page'))):
                raise ValueError
            names, numbers, records, documents = set(), set(), [], {}
            current_seen = False
            for row in rows:
                name, number = row['name'], row['version-number']
                if (row['secret-id'] != self.target.secret_id or not isinstance(name, str)
                        or type(number) is not int or number <= 0 or name in names or number in numbers):
                    raise ValueError
                names.add(name)
                numbers.add(number)
                actual, _, stages, content = read_version_content(self.client, self.target, name=name)
                if actual != number or (('CURRENT' in stages) != (number == current)):
                    raise ValueError
                current_seen |= number == current
                if name == 'unconfigured' and number == 1 and content == b'UNCONFIGURED':
                    continue
                if self._document_name(name):
                    if number == current:
                        raise ValueError
                    documents[name] = content
                    continue
                record = parse_record(content, dict(self.target.identity))
                if name != record.version_name or (number == current and record.kind != 'runtime-bundle'):
                    raise ValueError
                records.append(record)
            intents = [r for r in records if r.kind == 'creation-intent']
            runtimes = [r for r in records if r.kind == 'runtime-bundle']
            if (not current_seen or len(intents) > 1 or len(runtimes) > 1
                    or (runtimes and (not intents or runtimes[0].operation_id != intents[0].operation_id
                                     or runtimes[0].expires_at != intents[0].expires_at
                                     or runtimes[0].runtime_context != intents[0].runtime_context))):
                raise ValueError
            return CleanupHistory(etag, current, tuple(records), documents)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise DeliveryError('Owned cleanup credential history could not be verified.') from None

    def save(self, name, content):
        if (not isinstance(name, str) or not self._document_name(name)
                or not isinstance(content, bytes) or not 0 < len(content) <= MAX_RECORD_BYTES):
            raise DeliveryError('Invalid bounded cleanup evidence.')
        before = self.read()
        if name in before.documents:
            if before.documents[name] != content:
                raise DeliveryError('Saved cleanup evidence conflicts; preserve it for recovery.')
            return
        try:
            self.client.stage(self.target.secret_id, name, content, before.etag)
        except MutationUncertain:
            pass
        after = self.read()
        if after.current_number != before.current_number or after.documents.get(name) != content:
            raise DeliveryError('Cleanup evidence upload was not confirmed; no deletion is authorized.')

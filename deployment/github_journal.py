"""Retained deployment payloads; only a newly confirmed write invokes submit."""

import re
import uuid

from .apply_attempts import latest_applies
from .credential_errors import DeliveryError, MutationUncertain
from .github_pagination import TASK, next_page
from .submission_records import Intent, controller_identity


class GitHubJournal:
    def __init__(self, api, repository, repository_id, environment, commit):
        if (not isinstance(repository, str)
                or re.fullmatch(r'[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+', repository) is None
                or not isinstance(commit, str) or re.fullmatch('[a-f0-9]{40}', commit) is None):
            raise DeliveryError('Journal repository and exact commit are required.')
        self.controller_id = controller_identity(repository_id, environment)
        self.api, self.repository, self.repository_id = api, repository, repository_id
        self.commit = commit
        self.path = '/repos/' + repository

    def _verify_repository(self):
        data, _ = self.api.request('GET', self.path)
        if (not isinstance(data, dict) or type(data.get('id')) is not int
                or data['id'] != self.repository_id):
            raise DeliveryError('Journal repository identity changed.')

    @staticmethod
    def _entry(data):
        try:
            if (type(data['id']) is not int or data['id'] <= 0 or data['task'] != TASK
                    or not isinstance(data['sha'], str)
                    or re.fullmatch('[a-f0-9]{40}', data['sha']) is None
                    or data['ref'] != data['sha']):
                raise ValueError
            return data['id'], data['sha'], Intent.parse(data['payload'])
        except (KeyError, TypeError, ValueError):
            raise DeliveryError('Journal record metadata could not be verified.') from None

    def read(self, target_hash):
        self._verify_repository()
        entries, ids, operations, requests = [], set(), set(), set()
        page = 1
        while True:
            rows, headers = self.api.request(
                'GET', self.path + f'/deployments?task={TASK}&per_page=100&page={page}')
            if not isinstance(rows, list) or len(rows) > 100:
                raise DeliveryError('Incomplete journal discovery.')
            for row in rows:
                entry = self._entry(row)
                identifier, _, intent = entry
                key = (intent.controller_id, intent.target_hash, intent.kind,
                       intent.request_hash, intent.retry_of)
                if identifier in ids or intent.operation_id in operations or key in requests:
                    raise DeliveryError('Duplicate journal records require reconciliation.')
                ids.add(identifier)
                operations.add(intent.operation_id)
                requests.add(key)
                if intent.controller_id == self.controller_id and intent.target_hash == target_hash:
                    exact, _ = self.api.request('GET', self.path + f'/deployments/{identifier}')
                    if self._entry(exact) != entry:
                        raise DeliveryError('Journal record changed or disappeared.')
                    entries.append(intent)
            following = next_page(headers.get('link'), self.repository, self.repository_id, page)
            if following is None:
                latest_applies(entries)
                return entries
            if following > 25 or not rows:
                raise DeliveryError('Journal pagination limit or empty intermediate page reached.')
            page = following

    def submit(self, target_hash, kind, request_hash, package_hash, callback, *, retry_of=None):
        """Never replay a callback for an existing or uncertain persisted intent."""
        prior = self.read(target_hash)
        if retry_of is None and any(
                i.kind == kind and (kind in ('create-stack', 'destroy', 'cleanup-start', 'cleanup-complete')
                                    or i.request_hash == request_hash)
                for i in prior):
            raise DeliveryError('Submission is already recorded; recover it before proceeding.')
        intent = Intent(self.controller_id, target_hash, kind, uuid.uuid4().hex,
                        request_hash, package_hash, retry_of)
        latest_applies([*prior, intent])
        data, _ = self.api.request('POST', self.path + '/deployments', {
            'ref': self.commit, 'task': TASK, 'payload': intent.payload(),
            'environment': 'gateway-submissions', 'auto_merge': False, 'required_contexts': [],
            'transient_environment': False, 'production_environment': False,
        }, expected=201)
        try:
            identifier, commit, returned = self._entry(data)
            if commit != self.commit or returned != intent:
                raise DeliveryError('Unexpected created journal record.')
            exact, _ = self.api.request('GET', self.path + f'/deployments/{identifier}')
            if self._entry(exact) != (identifier, commit, intent):
                raise DeliveryError('Journal readback mismatch.')
        except DeliveryError:
            raise MutationUncertain('Journal creation was not confirmed; recover before submitting.') from None
        return callback(intent)

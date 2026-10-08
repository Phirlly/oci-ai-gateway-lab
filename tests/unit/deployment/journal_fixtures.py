"""In-memory GitHub API for journal state transitions, without real tokens."""

from copy import deepcopy

from deployment.credential_errors import MutationUncertain
from deployment.github_journal import GitHubJournal

REPO = 'example/gateway'
SHA = 'a' * 40


class JournalAPI:
    def __init__(self):
        self.rows = []
        self.calls = []
        self.lose_create_reply = False
        self.change_readback = False

    def request(self, method, path, body=None, *, expected=200):
        self.calls.append((method, path, deepcopy(body), expected))
        if path == '/repos/' + REPO:
            return {'id': 17}, {}
        if method == 'POST':
            row = {'id': len(self.rows) + 1, 'sha': body['ref'], 'ref': body['ref'],
                   'task': body['task'], 'payload': deepcopy(body['payload'])}
            self.rows.append(row)
            if self.lose_create_reply:
                raise MutationUncertain('Uncertain journal write.')
            return deepcopy(row), {}
        if '?' in path:
            return deepcopy(self.rows), {}
        row = deepcopy(next(r for r in self.rows if path.endswith('/' + str(r['id']))))
        if self.change_readback:
            row['payload']['operation_id'] = 'f' * 32
        return row, {}


def journal(api):
    return GitHubJournal(api, REPO, 17, 'demo', SHA)

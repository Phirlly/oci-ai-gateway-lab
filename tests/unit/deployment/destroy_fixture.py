"""Synthetic Destroy jobs share the existing stack/journal setup."""

from copy import deepcopy

from deployment.credential_errors import MutationUncertain
from .orm_fixtures import JOB_ID, job_data
from .submission_fixtures import SubmissionORM, submission_fixture


class DestroyORM(SubmissionORM):
    def create_destroy(self, payload):
        self.calls.append(('create_destroy', deepcopy(payload)))
        row = job_data(**{
            'id': JOB_ID + str(len(self.jobs)), 'operation': 'DESTROY',
            'variables': deepcopy(self.stacks[0]['variables']),
            'freeform-tags': payload['freeformTags'], 'lifecycle-state': 'ACCEPTED',
            'config-source': {'config-source-record-type': 'ZIP_UPLOAD'},
            'working-directory': 'foundation', 'is-provider-upgrade-required': False,
        })
        self.jobs.append(row)
        if self.fail == 'create_destroy':
            raise MutationUncertain('Synthetic lost Destroy reply.')
        return {'data': deepcopy(row)}


def destroy_fixture():
    f = submission_fixture()
    f.orm = DestroyORM(f.package)
    return f

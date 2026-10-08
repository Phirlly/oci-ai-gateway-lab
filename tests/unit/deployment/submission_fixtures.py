"""Synthetic ORM state with separate durable journal and lost-reply controls."""

from copy import deepcopy
from types import SimpleNamespace

from deployment.credential_errors import CloudReadError, MutationUncertain
from deployment.deployment_config import FoundationConfig
from deployment.foundation_package import FoundationPackage
from deployment.resource_manager_stacks import StackTarget
from .journal_fixtures import JournalAPI, journal
from .orm_fixtures import JOB_ID, SETTINGS, STACK_ID, ReadOnlyORM, job_data, stack_data
from .foundation_fixtures import archive_bytes


class SubmissionORM(ReadOnlyORM):
    def __init__(self, package):
        super().__init__()
        self.stacks = []
        self.package = package
        self.etag = 'initial'
        self.fail = None

    def get_stack(self, stack_id):
        result = super().get_stack(stack_id)
        result['etag'] = self.etag
        return result

    def create_stack(self, payload):
        self.calls.append(('create_stack', deepcopy(payload)))
        self.stacks = [stack_data(**{
            'variables': payload['variables'], 'freeform-tags': payload['freeformTags'],
            'terraform-version': '1.5.x',
            'is-third-party-provider-experience-enabled': True,
            'config-source': {'config-source-type': 'ZIP_UPLOAD', 'working-directory': 'foundation'},
        })]
        if self.fail == 'create_stack':
            raise MutationUncertain('Synthetic lost stack reply.')
        return {'data': deepcopy(self.stacks[0])}

    def update_stack(self, payload):
        self.calls.append(('update_stack', deepcopy(payload)))
        assert payload['ifMatch'] == self.etag
        self.stacks[0].update({'variables': payload['variables'], 'freeform-tags': payload['freeformTags']})
        self.etag += '-updated'
        if self.fail == 'update_stack':
            raise MutationUncertain('Synthetic lost update reply.')
        return {'data': deepcopy(self.stacks[0])}

    def create_apply(self, payload):
        self.calls.append(('create_apply', deepcopy(payload)))
        row = job_data(**{
            'id': JOB_ID + str(len(self.jobs)), 'variables': deepcopy(self.stacks[0]['variables']),
            'freeform-tags': payload['freeformTags'], 'lifecycle-state': 'ACCEPTED',
            'config-source': {'config-source-record-type': 'ZIP_UPLOAD'},
            'working-directory': 'foundation', 'is-provider-upgrade-required': False,
            'is-third-party-provider-experience-enabled': True,
        })
        self.jobs.append(row)
        if self.fail == 'create_apply':
            raise MutationUncertain('Synthetic lost Apply reply.')
        return {'data': deepcopy(row)}

    def get_job_package(self, job_id):
        self.calls.append(('get_job_package', job_id))
        if self.fail == 'download':
            raise CloudReadError('Synthetic delayed job archive.')
        return self.package.content


def submission_fixture():
    api = JournalAPI()
    durable = journal(api)
    package = FoundationPackage(archive_bytes())
    target = StackTarget(FoundationConfig(SETTINGS), durable.controller_id)
    return SimpleNamespace(api=api, journal=durable, package=package,
                           target=target, orm=SubmissionORM(package))

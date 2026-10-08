"""Shared service fakes for testing the complete foundation handoff sequence."""

from copy import deepcopy

from deployment.credential_handoff import advance_handoff
from .inventory_fixture import inventory
from .model_key_fixture import MemoryKeys
from .orm_fixtures import SETTINGS
from .record_fixtures import EXPIRES, IDENTITY, NOW
from .submission_fixtures import SubmissionORM, submission_fixture
from .vault_fixture import MemoryVault


class HandoffORM(SubmissionORM):
    def __init__(self, package):
        super().__init__(package)
        self.inventories = {}
        self.archives = {}
        self.before_apply = None

    def create_apply(self, payload):
        if self.before_apply:
            self.before_apply()
        return super().create_apply(payload)

    def list_job_resources(self, job_id, compartment_id):
        self.calls.append(('list_job_resources', job_id, compartment_id))
        assert compartment_id == SETTINGS['compartment_ocid']
        job = next(row for row in self.jobs if row['id'] == job_id)
        assert job['lifecycle-state'] == 'SUCCEEDED'
        return deepcopy(self.inventories.get(job_id, inventory()))

    def get_job_package(self, job_id):
        content = super().get_job_package(job_id)
        return self.archives.get(job_id, content)


class HandoffFixture:
    def __init__(self):
        submission = submission_fixture()
        self.journal, self.target, self.package = submission.journal, submission.target, submission.package
        self.api = submission.api
        self.orm = HandoffORM(self.package)
        self.vault = MemoryVault()
        self.vault.region = SETTINGS['region']
        self.keys = MemoryKeys(self.vault)

    def advance(self, **inputs):
        options = dict(inference_region=IDENTITY['inference_region'], now=lambda: NOW)
        return advance_handoff(self.orm, self.journal, self.target, self.package,
                               vault=self.vault, keys=self.keys, **(options | inputs))

    def base_succeeded(self):
        self.advance()
        self.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'

    def permissions_started(self):
        self.base_succeeded()
        return self.advance(external_api_key='external-sentinel', demo_password='demo-sentinel',
                            expires_at=EXPIRES)

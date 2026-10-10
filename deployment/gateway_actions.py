"""Coordinate the four presenter-facing actions with no implicit model retries."""

from datetime import datetime, timedelta, timezone

from demo.verification import PresenterUnavailable, check_health, presenter_client, verify_demo
from runtime.gateway_http import GatewayError, GatewayHTTP
from runtime.password_policy import valid_presenter_password
from runtime.presenter import Presenter
from runtime.runtime_bundle import MODEL_ALIASES

from .action_wait import PollBudget, PollTimeout
from .apply_submission import ensure_apply
from .credential_errors import ActivationPending, DeliveryError
from .credential_handoff import advance_handoff
from .credential_records import valid_secret
from .gateway_observation import observe_gateway
from .removal_handoff import advance_removal
from .removed_state import require_no_managed_resources
from .submission_records import target_identity


class GatewayActions:
    def __init__(self, orm, journal, target, package, compute, *, vault=None, keys=None, progress=None):
        self.orm, self.journal, self.target, self.package = orm, journal, target, package
        self.compute, self.vault, self.keys, self.progress = compute, vault, keys, progress
        settings = target.config.values
        self.presenter = Presenter(settings['deployment_id'], settings['presenter_email'], MODEL_ALIASES)

    def _result(self, status, context=None, report=None):
        result = {'status': status, 'ready': bool(report and report['ready']),
                  'username': self.presenter.email, 'compare_url': None,
                  'verification': report if report is not None else 'NOT_RUN'}
        if context:
            result['compare_url'] = 'https://' + context['public_ip'] + '/ui/playground/?tab=compare'
        return result

    def _verify(self, context, password):
        public = GatewayHTTP('https://' + context['public_ip'])
        try:
            report = verify_demo(public, self.presenter, password)
        except (GatewayError, TimeoutError) as error:
            return self._not_ready(context, error)
        return self._result('Ready' if report['ready'] else 'Verification failed', context, report)

    def _not_ready(self, context, error):
        result = self._result('Deployed; not ready', context)
        result.update(verification='FAILED', error=(str(error) if not isinstance(error, TimeoutError)
                                                   else 'Gateway request timed out; verification was not retried'))
        return result

    def _wait_frontend(self, context, password):
        public = GatewayHTTP('https://' + context['public_ip'])
        budget = PollBudget(1200, progress=self.progress)
        while True:
            try:
                check_health(public)
            except (GatewayError, TimeoutError):
                # Before initialization/TLS issuance, only non-inference health is polled.
                budget.pause('Waiting for trusted HTTPS and gateway/database health')
                continue
            try:
                presenter_client(public, self.presenter, password)
                return
            except PresenterUnavailable:
                budget.pause('Waiting for presenter login; check DEMO_PASSWORD if initialization has completed')

    def deploy(self, external_api_key, password):
        if not valid_presenter_password(password):
            raise DeliveryError('DEMO_PASSWORD needs12-256 characters with uppercase, lowercase, a number and a symbol.')
        history = self.journal.read(target_identity(self.target.config))
        if not history and not valid_secret(external_api_key):
            raise DeliveryError('Initial Deploy requires ANTHROPIC_API_KEY before any cloud resources are created.')
        expiry = (datetime.now(timezone.utc) + timedelta(days=self.target.config.values['model_key_ttl_days'])).strftime('%Y-%m-%dT%H:%M:%SZ')
        budget = PollBudget(3600, progress=self.progress)
        while True:
            try:
                result = advance_handoff(
                    self.orm, self.journal, self.target, self.package, vault=self.vault, keys=self.keys,
                    compute=self.compute, inference_region=self.target.config.values['inference_region'],
                    external_api_key=external_api_key, demo_password=password, expires_at=expiry)
            except ActivationPending:
                budget.pause('Waiting for the saved model key to activate')
                continue
            if result.phase == 'CREDENTIALS_PUBLISHED':
                try:
                    self._wait_frontend(result.runtime_context, password)
                except (GatewayError, TimeoutError, PollTimeout) as error:
                    return self._not_ready(result.runtime_context, error)
                return self._verify(result.runtime_context, password)
            if result.stack_state not in ('ACTIVE', 'CREATING'):
                raise DeliveryError('Resource Manager stack is not deployable; inspect its state before retrying.')
            if result.job is not None and result.job.state == 'FAILED':
                retried = ensure_apply(self.orm, self.journal, self.target, self.package, result.stack_id,
                                       model_key_ocid=result.job.model_key_ocid, retry_failed=True)
                if retried.state == 'FAILED':
                    raise DeliveryError('Apply failed after the single attested recovery attempt; inspect Resource Manager.')
            elif result.job is not None and result.job.state == 'CANCELED':
                raise DeliveryError('Apply was canceled; explicit recovery is required.')
            budget.pause('Waiting for infrastructure and credential publication')

    def status(self):
        observed = observe_gateway(self.orm, self.journal, self.target, self.package, self.compute)
        result = self._result(observed.phase, observed.context)
        if observed.context:
            try:
                check_health(GatewayHTTP('https://' + observed.context['public_ip']))
                result['health'] = 'PASS'
            except (GatewayError, TimeoutError):
                result['health'] = 'UNAVAILABLE'
        return result

    def verify(self, password):
        if not isinstance(password, str) or not 0 < len(password) <= 256:
            raise DeliveryError('Verify samples requires the current DEMO_PASSWORD.')
        observed = observe_gateway(self.orm, self.journal, self.target, self.package, self.compute)
        if observed.phase != 'DEPLOYED' or observed.context is None:
            raise DeliveryError('Verify samples requires a completed bound deployment; run Deploy or Status first.')
        return self._verify(observed.context, password)

    def remove(self):
        budget = PollBudget(3600, progress=self.progress)
        while True:
            result = advance_removal(self.orm, self.journal, self.target, self.package,
                                     vault=self.vault, keys=self.keys,
                                     inference_region=self.target.config.values['inference_region'])
            if result.phase == 'DESTROY':
                if result.job.state == 'SUCCEEDED':
                    self.package.verify(self.orm.get_job_package(result.job.job_id))
                    require_no_managed_resources(self.orm.get_job_state(result.job.job_id))
                    output = self._result('Removed')
                    output['retained'] = 'Resource Manager stack/history; Vault and secret may remain scheduled for deletion'
                    return output
                if result.job.state in ('FAILED', 'CANCELED'):
                    raise DeliveryError('Destroy did not succeed; preserve stack/history for explicit recovery.')
            budget.pause('Waiting for owned key cleanup and Resource Manager Destroy')

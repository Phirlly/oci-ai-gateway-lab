"""Advance foundation and credentials without polling or reporting demo readiness."""

import re
from dataclasses import dataclass

from .apply_submission import ensure_apply
from .credential_errors import DeliveryError
from .cloud_context import resolve_runtime_context
from .deployment_config import PATTERNS
from .gateway_config import GatewayConfig
from .foundation_history import recover_base
from .foundation_resources import vault_target
from .model_key_provisioning import ModelKeyProvisioner
from .resource_manager_jobs import JobSnapshot
from .secret_delivery import HandoffReceipt, SecretDelivery
from .stack_submission import ensure_stack


@dataclass(frozen=True, repr=False)
class FoundationHandoff:
    phase: str
    stack_id: str
    stack_state: str
    job: JobSnapshot | None = None
    credentials: HandoffReceipt | None = None
    runtime_context: dict | None = None


def advance_handoff(client, journal, target, package, *, vault, keys, inference_region,
                    external_api_key=None, demo_password=None, expires_at=None, now=None, compute=None):
    """One serialized controller; creation inputs are ignored when a bundle exists."""
    if (not isinstance(inference_region, str)
            or re.fullmatch(PATTERNS['region'], inference_region) is None
            or keys.region != inference_region
            or vault.region != target.config.values['region']):
        raise DeliveryError('Explicit inference and hosting client regions must match deployment inputs.')
    full = isinstance(target.config, GatewayConfig)
    if full and (not package.is_gateway or compute is None
                 or compute.region != target.config.values['region']
                 or inference_region != target.config.values['inference_region']):
        raise DeliveryError('Gateway handoff requires its full package and matching Compute and inference clients.')
    stack = ensure_stack(client, journal, target, package)
    if stack.state != 'ACTIVE':
        return FoundationHandoff('FOUNDATION', stack.stack_id, stack.state)
    if stack.model_key_ocid is None:
        job = ensure_apply(client, journal, target, package, stack.stack_id, model_key_ocid=None)
        if job.state != 'SUCCEEDED':
            return FoundationHandoff('FOUNDATION', stack.stack_id, stack.state, job)

    stack, base = recover_base(client, journal, target, package, stack.stack_id)

    def destination(job):
        resources = client.list_job_resources(job.job_id, target.compartment_id)
        owned = vault_target(resources, target.config, stack.stack_id, inference_region)
        context = resolve_runtime_context(compute, resources, target.config) if full else None
        return owned, context

    owned_vault, context = destination(base)
    delivery = SecretDelivery(vault, owned_vault, now=now)
    credentials = ModelKeyProvisioner(delivery, keys).prepare(
        external_api_key=external_api_key, demo_password=demo_password,
        expires_at=expires_at, stack_key_ocid=stack.model_key_ocid, runtime_context=context,
    )
    job = ensure_apply(client, journal, target, package, stack.stack_id,
                       model_key_ocid=credentials.model_key_ocid)
    if job.state != 'SUCCEEDED':
        return FoundationHandoff('PERMISSIONS', stack.stack_id, stack.state, job, credentials, context)
    if destination(job) != (owned_vault, context):
        raise DeliveryError('Permission Apply changed the credential destination; explicit recovery is required.')
    published = delivery.publish(credentials.version_name, job.model_key_ocid)
    return FoundationHandoff('CREDENTIALS_PUBLISHED', stack.stack_id, stack.state, job, published, context)

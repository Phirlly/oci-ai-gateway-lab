"""Strict nonsecret identities persisted by the submission journal."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from .credential_errors import DeliveryError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def controller_identity(repository_id, environment):
    if (type(repository_id) is not int or repository_id <= 0
            or not isinstance(environment, str)
            or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', environment) is None):
        raise DeliveryError('Invalid journal controller identity.')
    return digest(['api.github.com', repository_id, environment.lower()])


def target_identity(config):
    return digest({key: config.values[key] for key in
                   ('tenancy_ocid', 'compartment_ocid', 'region', 'deployment_id')})


@dataclass(frozen=True, repr=False)
class Intent:
    controller_id: str
    target_hash: str
    kind: str
    operation_id: str
    request_hash: str
    package_hash: str

    def __post_init__(self):
        if self.kind not in ('create-stack', 'apply', 'destroy'):
            raise DeliveryError('Unsupported submission operation.')
        for name, value in asdict(self).items():
            if name == 'kind':
                continue
            length = 32 if name == 'operation_id' else 64
            if not isinstance(value, str) or re.fullmatch('[a-f0-9]{%d}' % length, value) is None:
                raise DeliveryError('Invalid submission identity.')

    def payload(self):
        return {'version': 1, **asdict(self)}

    @classmethod
    def parse(cls, payload):
        try:
            if (not isinstance(payload, dict) or type(payload['version']) is not int
                    or payload['version'] != 1
                    or set(payload) != {'version', *cls.__dataclass_fields__}):
                raise ValueError
            return cls(**{k: v for k, v in payload.items() if k != 'version'})
        except (KeyError, TypeError, ValueError):
            raise DeliveryError('Invalid submission journal payload.') from None


def apply_request_hash(stack_id, variables, package_hash):
    return digest({'stack_id': stack_id, 'variables': variables, 'package_hash': package_hash})


def destroy_request_hash(stack_id, variables, package_hash):
    return digest({'operation': 'DESTROY', 'stack_id': stack_id,
                   'variables': variables, 'package_hash': package_hash})

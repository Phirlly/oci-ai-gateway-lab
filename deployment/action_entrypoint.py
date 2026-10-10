"""Thin GitHub/local entrypoint: protected connection, fixed action, safe result."""

import argparse
import json
import os
from contextlib import nullcontext
from pathlib import Path

from runtime.gateway_http import GatewayError

from .compute_cli import ComputeCLI
from .credential_errors import DeliveryError
from .deployment_config import load_config
from .foundation_package import GatewayPackage
from .gateway_actions import GatewayActions
from .gateway_config import GatewayConfig
from .github_http import GitHubHTTP
from .github_journal import GitHubJournal
from .model_keys_cli import ModelKeysCLI
from .package_recovery import deployment_package
from .resource_manager_cli import ResourceManagerCLI
from .resource_manager_stacks import StackTarget
from .runner_credentials import local_connection, runner_connection
from .vault_cli import VaultCLI

ACTIONS = ('Deploy', 'Status', 'Verify samples', 'Remove')
ROOT = Path(__file__).resolve().parents[1]


def create_actions(config, connection, environment, action):
    try:
        repository_id = int(environment['GITHUB_REPOSITORY_ID'])
        journal = GitHubJournal(GitHubHTTP(environment.get('GITHUB_TOKEN') or environment.get('GH_TOKEN')),
                                environment['GITHUB_REPOSITORY'], repository_id, 'gateway', environment['GITHUB_SHA'])
    except (KeyError, TypeError, ValueError):
        raise DeliveryError('Explicit GitHub repository, numeric ID, commit and token are required for retained recovery records.') from None
    settings = config.values
    connection_args = {'profile': connection.profile, 'config_file': connection.config_file}
    orm = ResourceManagerCLI(settings['region'], **connection_args)
    target = StackTarget(config, journal.controller_id)
    package = deployment_package(orm, journal, target, lambda: GatewayPackage.build(ROOT))
    if not package.is_gateway:
        raise DeliveryError('This workflow needs a fresh full-gateway deployment identity; preserve older foundation recovery records.')
    compute = ComputeCLI(settings['region'], **connection_args)
    vault = VaultCLI(settings['region'], **connection_args) if action in ('Deploy', 'Remove') else None
    keys = ModelKeysCLI(settings['inference_region'], **connection_args) if action in ('Deploy', 'Remove') else None
    return GatewayActions(orm, journal, target, package, compute, vault=vault, keys=keys,
                          progress=lambda phase: print(phase, flush=True))


def _settings(options, environment):
    if options.settings:
        if environment.get('DEPLOYMENT_CONFIG'):
            raise DeliveryError('Choose either --settings or DEPLOYMENT_CONFIG, not two configuration sources.')
        with Path(options.settings).open('rb') as source:
            content = source.read(48 * 1024 + 1)
    else:
        content = environment.get('DEPLOYMENT_CONFIG', '')
    config = load_config(content)
    if not isinstance(config, GatewayConfig):
        raise DeliveryError('The four-action workflow requires the complete schema_version2 settings example.')
    return config


def _report(result, environment):
    print(json.dumps(result, sort_keys=True, indent=2), flush=True)
    destination = environment.get('GITHUB_STEP_SUMMARY')
    if destination:
        lines = ['**' + result['status'] + '**', '']
        if result.get('compare_url'):
            lines += ['[Open LiteLLM Compare](' + result['compare_url'] + ')', '',
                      'Username: `' + result['username'] + '`', 'Password: your configured `DEMO_PASSWORD`.', '']
        if result.get('error'):
            lines.append(result['error'])
        if result.get('retained'):
            lines.append(result['retained'])
        report = result.get('verification')
        if isinstance(report, dict):
            lines += ['', '| Model | Sample | Streaming | Result | Attempts | Seconds |', '|---|---|---|---|---|---|']
            for row in report['samples']:
                lines.append('| {model} | {sample} | {stream} | {status} | {attempts} | {seconds} |'.format(**row))
        elif report:
            lines.append('Model verification: ' + report)
        with Path(destination).open('a', encoding='utf-8') as output:
            output.write('\n'.join(lines) + '\n')


def main(argv=None, environment=None):
    environment = os.environ if environment is None else environment
    parser = argparse.ArgumentParser(description='Deploy, inspect, verify or remove the OCI AI Gateway.')
    parser.add_argument('--action', choices=ACTIONS, required=True)
    parser.add_argument('--settings', help='One nonsecret deployment.tfvars.json; Actions uses DEPLOYMENT_CONFIG instead')
    parser.add_argument('--profile', default='DEFAULT', help='Local OCI profile (never stored in deployment settings)')
    parser.add_argument('--oci-config', default='~/.oci/config', help='Local OCI signing configuration')
    options = parser.parse_args(argv)
    try:
        config = _settings(options, environment)
        tenancy = config.values['tenancy_ocid']
        connection = (runner_connection(environment, tenancy) if environment.get('GITHUB_ACTIONS') == 'true'
                      or environment.get('OCI_PRIVATE_KEY') else nullcontext(local_connection(options.oci_config, options.profile, tenancy)))
        with connection as selected:
            actions = create_actions(config, selected, environment, options.action)
            if options.action == 'Deploy':
                result = actions.deploy(environment.get('ANTHROPIC_API_KEY'), environment.get('DEMO_PASSWORD'))
            elif options.action == 'Verify samples':
                result = actions.verify(environment.get('DEMO_PASSWORD'))
            elif options.action == 'Status':
                result = actions.status()
            else:
                result = actions.remove()
        code = int(options.action in ('Deploy', 'Verify samples') and not result['ready'])
    except (DeliveryError, GatewayError, TimeoutError) as error:
        result, code = {'status': 'Failed', 'ready': False, 'error': str(error)}, 1
    except Exception:
        result, code = {'status': 'Failed', 'ready': False,
                        'error': 'Deployment inputs or execution could not be verified; preserve existing resources and recovery records.'}, 1
    _report(result, environment)
    return code

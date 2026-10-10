"""Bind an attested instance to its owned primary reserved address."""

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .foundation_resources import resource_ids
from .gateway_config import GatewayConfig
from .runtime_context import valid_runtime_context

RESOURCE_KINDS = {
    'oci_core_instance.gateway': ('oci_core_instance', 'instance'),
    'oci_core_public_ip.gateway': ('oci_core_public_ip', 'publicip'),
    'oci_core_subnet.gateway': ('oci_core_subnet', 'subnet'),
}
INSTANCE_STATES = {'PROVISIONING', 'RUNNING', 'STARTING', 'STOPPING', 'STOPPED',
                   'CREATING_IMAGE', 'MOVING'}


def resolve_runtime_context(client, resources, config):
    if not isinstance(config, GatewayConfig) or client.region != config.values['region']:
        raise DeliveryError('Runtime metadata client must match the gateway hosting region.')
    ids = resource_ids(resources, config, RESOURCE_KINDS)
    instance_id, public_id, subnet = (ids[name] for name in RESOURCE_KINDS)
    settings = config.values
    tags = {'solution': 'oci-ai-gateway-lab', 'deployment_id': settings['deployment_id']}

    def owned(row, identifier, tagged=True):
        return (row['id'] == identifier and row['compartment-id'] == settings['compartment_ocid']
                and (not tagged or all(row['freeform-tags'].get(k) == v for k, v in tags.items())))

    try:
        instance = client.get_instance(instance_id)['data']
        region = {'iad': 'us-ashburn-1', 'phx': 'us-phoenix-1'}.get(instance['region'], instance['region'])
        if (not owned(instance, instance_id) or region != settings['region']
                or instance['lifecycle-state'] not in INSTANCE_STATES):
            raise ValueError
        public = client.get_public_ip(public_id)['data']
        private_id = public['assigned-entity-id']
        if (not owned(public, public_id) or public['lifetime'] != 'RESERVED' or public['scope'] != 'REGION'
                or public['lifecycle-state'] != 'ASSIGNED' or public['assigned-entity-type'] != 'PRIVATE_IP'
                or not valid_ocid(private_id, 'privateip')):
            raise ValueError
        private = client.get_private_ip(private_id)['data']
        vnic_id = private['vnic-id']
        if (not owned(private, private_id, False) or private['is-primary'] is not True
                or private['subnet-id'] != subnet or not valid_ocid(vnic_id, 'vnic')):
            raise ValueError
        vnic = client.get_vnic(vnic_id)['data']
        if (not owned(vnic, vnic_id) or vnic['lifecycle-state'] != 'AVAILABLE' or vnic['is-primary'] is not True
                or vnic['subnet-id'] != subnet or vnic['private-ip'] != private['ip-address']
                or vnic['public-ip'] != public['ip-address']):
            raise ValueError
        response = client.list_vnic_attachments(settings['compartment_ocid'], instance_id, vnic_id)
        rows = response['data']
        if (not isinstance(rows, list) or len(rows) != 1
                or any(response.get(k) for k in ('opc-next-page', 'opc-next-cursor', 'next-page'))):
            raise ValueError
        attachment = rows[0]
        if (not valid_ocid(attachment['id'], 'vnicattachment') or attachment['instance-id'] != instance_id
                or attachment['vnic-id'] != vnic_id or attachment['compartment-id'] != settings['compartment_ocid']
                or attachment['lifecycle-state'] != 'ATTACHED'):
            raise ValueError
        context = {'instance_ocid': instance_id, 'public_ip_ocid': public_id, 'public_ip': public['ip-address'],
                   **{key: settings[key] for key in ('presenter_email', 'external_provider', 'external_model_id')}}
        if not valid_runtime_context(context):
            raise ValueError
        return context
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError('Exact owned VM, primary network and public address could not be verified.') from None

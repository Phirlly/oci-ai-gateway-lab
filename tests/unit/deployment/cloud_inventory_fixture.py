"""Synthetic exact VM/address/subnet metadata chain; no cloud calls."""

from copy import deepcopy

from .gateway_config_fixture import CONTEXT, GATEWAY_SETTINGS
from .inventory_fixture import inventory

SUBNET_ID = 'ocid1.subnet.oc1.iad.example'
PRIVATE_ID = 'ocid1.privateip.oc1.iad.example'
VNIC_ID = 'ocid1.vnic.oc1.iad.example'
TAGS = {'solution': 'oci-ai-gateway-lab', 'deployment_id': GATEWAY_SETTINGS['deployment_id']}


def cloud_inventory():
    result = inventory()
    for kind, identifier in [('oci_core_instance', CONTEXT['instance_ocid']),
                             ('oci_core_public_ip', CONTEXT['public_ip_ocid']),
                             ('oci_core_subnet', SUBNET_ID)]:
        result['data']['items'].append({'resource-address': kind + '.gateway', 'resource-type': kind,
                                       'resource-id': identifier, 'region': GATEWAY_SETTINGS['region']})
    return result


class CloudMetadata:
    region = GATEWAY_SETTINGS['region']

    def __init__(self):
        owned = {'compartment-id': GATEWAY_SETTINGS['compartment_ocid'], 'freeform-tags': TAGS}
        self.instance = {**owned, 'id': CONTEXT['instance_ocid'], 'lifecycle-state': 'RUNNING', 'region': 'iad'}
        self.public = {**owned, 'id': CONTEXT['public_ip_ocid'], 'lifecycle-state': 'ASSIGNED',
                       'lifetime': 'RESERVED', 'scope': 'REGION', 'assigned-entity-type': 'PRIVATE_IP',
                       'assigned-entity-id': PRIVATE_ID, 'ip-address': CONTEXT['public_ip']}
        self.private = {'id': PRIVATE_ID, 'compartment-id': owned['compartment-id'],
                        'vnic-id': VNIC_ID, 'is-primary': True, 'subnet-id': SUBNET_ID, 'ip-address': '10.42.0.2'}
        self.vnic = {**owned, 'id': VNIC_ID, 'lifecycle-state': 'AVAILABLE', 'is-primary': True,
                     'subnet-id': SUBNET_ID, 'private-ip': '10.42.0.2', 'public-ip': CONTEXT['public_ip']}
        self.attachments = [{'id': 'ocid1.vnicattachment.oc1.iad.example',
                             'compartment-id': owned['compartment-id'], 'instance-id': CONTEXT['instance_ocid'],
                             'vnic-id': VNIC_ID, 'lifecycle-state': 'ATTACHED'}]

    def get_instance(self, identifier):
        return {'data': deepcopy(self.instance)}

    def get_public_ip(self, identifier):
        assert identifier == CONTEXT['public_ip_ocid']
        return {'data': deepcopy(self.public)}

    def get_private_ip(self, identifier):
        assert identifier == PRIVATE_ID
        return {'data': deepcopy(self.private)}

    def get_vnic(self, identifier):
        assert identifier == VNIC_ID
        return {'data': deepcopy(self.vnic)}

    def list_vnic_attachments(self, compartment, instance, vnic):
        assert (compartment, instance, vnic) == (GATEWAY_SETTINGS['compartment_ocid'], CONTEXT['instance_ocid'], VNIC_ID)
        return {'data': deepcopy(self.attachments)}

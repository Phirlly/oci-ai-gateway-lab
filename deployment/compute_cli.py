"""Read-only Compute/network metadata used to bind the runtime to its host."""

from .oci_cli import OCICommand


class ComputeCLI(OCICommand):
    def get_instance(self, identifier):
        return self.request(('compute', 'instance', 'get'), {'instanceId': identifier})

    def get_public_ip(self, identifier):
        return self.request(('network', 'public-ip', 'get'), {'publicIpId': identifier})

    def get_private_ip(self, identifier):
        return self.request(('network', 'private-ip', 'get'), {'privateIpId': identifier})

    def get_vnic(self, identifier):
        return self.request(('network', 'vnic', 'get'), {'vnicId': identifier})

    def list_vnic_attachments(self, compartment, instance, vnic):
        return self.request(('compute', 'vnic-attachment', 'list', '--all'),
                            {'compartmentId': compartment, 'instanceId': instance, 'vnicId': vnic},
                            empty_list=True)

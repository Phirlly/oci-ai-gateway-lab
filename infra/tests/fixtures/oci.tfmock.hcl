# Synthetic provider values only. No OCI requests or real account identifiers.
mock_data "oci_identity_availability_domains" {
  defaults = { availability_domains = [{ name = "synthetic:US-ASHBURN-AD-1" }] }
}

mock_data "oci_core_images" {
  defaults = { images = [{ id = "ocid1.image.oc1.iad.synthetic" }] }
}

mock_data "oci_core_private_ips" {
  defaults = { private_ips = [{ id = "ocid1.privateip.oc1.iad.synthetic", is_primary = true, ip_address = "10.42.0.2" }] }
}

mock_resource "oci_core_instance" {
  defaults = { id = "ocid1.instance.oc1.iad.synthetic", private_ip = "10.42.0.2" }
}

mock_resource "oci_core_vcn" {
  defaults = { id = "ocid1.vcn.oc1.iad.synthetic" }
}
mock_resource "oci_core_subnet" {
  defaults = { id = "ocid1.subnet.oc1.iad.synthetic" }
}
mock_resource "oci_core_security_list" {
  defaults = { id = "ocid1.securitylist.oc1.iad.synthetic" }
}
mock_resource "oci_core_route_table" {
  defaults = { id = "ocid1.routetable.oc1.iad.synthetic" }
}
mock_resource "oci_core_internet_gateway" {
  defaults = { id = "ocid1.internetgateway.oc1.iad.synthetic" }
}
mock_data "oci_identity_region_subscriptions" {
  defaults = {
    region_subscriptions = [
      {
        region_name    = "us-phoenix-1"
        region_key     = "PHX"
        is_home_region = true
        state          = "READY"
      },
      {
        region_name    = "us-ashburn-1"
        region_key     = "IAD"
        is_home_region = false
        state          = "READY"
      }
    ]
  }
}

mock_resource "oci_kms_vault" {
  defaults = {
    id                  = "ocid1.vault.oc1.iad.aaaaaaaaexamplevault"
    management_endpoint = "https://example-management.invalid"
  }
}

mock_resource "oci_kms_key" {
  defaults = {
    id = "ocid1.key.oc1.iad.aaaaaaaaexamplekey"
  }
}

mock_resource "oci_vault_secret" {
  defaults = {
    id = "ocid1.vaultsecret.oc1.iad.aaaaaaaaexamplesecret"
  }
}

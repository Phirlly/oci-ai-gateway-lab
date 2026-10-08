# Synthetic provider values only. No OCI requests or real account identifiers.
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

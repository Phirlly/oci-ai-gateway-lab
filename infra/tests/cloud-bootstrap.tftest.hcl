mock_provider "oci" {
  source          = "./tests/fixtures"
  override_during = plan
}
mock_provider "oci" {
  alias           = "home"
  source          = "./tests/fixtures"
  override_during = plan
}
variables {
  tenancy_ocid               = "ocid1.tenancy.oc1..aaaaaaaaexampletenancy"
  compartment_ocid           = "ocid1.compartment.oc1..aaaaaaaaexamplecompartment"
  region                     = "us-ashburn-1"
  deployment_id              = "gateway-test"
  oci_model_id               = "example.chat-model"
  schema_version             = 2
  inference_region           = "us-ashburn-1"
  external_provider          = "anthropic"
  external_model_id          = "synthetic-external"
  presenter_email            = "presenter@example.invalid"
  instance_shape             = "VM.Standard.E4.Flex"
  instance_ocpus             = 1
  instance_memory_gbs        = 8
  boot_volume_size_gbs       = 50
  availability_domain_number = 1
  image_name                 = "Canonical-Ubuntu-24.04-2026.09.18-0"
  model_key_ttl_days         = 7
}
run "metadata_is_secret_free_bounded_and_has_resumable_bootstrap" {
  command = plan
  assert {
    condition     = length(oci_core_instance.gateway.metadata.user_data) < 32000
    error_message = "Encoded user_data must fit OCI's metadata budget."
  }
  assert {
    condition     = length(yamldecode(base64decode(oci_core_instance.gateway.metadata.user_data)).runcmd) == 4 && yamldecode(base64decode(oci_core_instance.gateway.metadata.user_data)).runcmd[0] == "set -eu" && !can(yamldecode(base64decode(oci_core_instance.gateway.metadata.user_data)).packages)
    error_message = "Cloud-init only extracts local files and enables a timer before network installation."
  }
  assert {
    condition     = !strcontains(base64decode(oci_core_instance.gateway.metadata.user_data), "public_ip") && strcontains(base64decode(oci_core_instance.gateway.metadata.user_data), "gz+b64")
    error_message = "Runtime assets must be embedded; public IP is a later attested handoff."
  }
  assert {
    condition     = length(oci_identity_policy.runtime_bundle.statements) == 1 && one(oci_identity_policy.runtime_bundle.statements) == "Allow any-user to read secret-bundles in compartment id ${var.compartment_ocid} where all {request.principal.type='instance', request.instance.id='ocid1.instance.oc1.iad.synthetic', target.secret.id='ocid1.vaultsecret.oc1.iad.aaaaaaaaexamplesecret', request.operation='GetSecretBundle'}"
    error_message = "Grant only the exact instance's read of this secret bundle."
  }
}

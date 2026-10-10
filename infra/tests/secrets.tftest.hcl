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
  tenancy_ocid               = "ocid1.tenancy.oc1..aaaaaaaaexampletenancy"
  compartment_ocid           = "ocid1.compartment.oc1..aaaaaaaaexamplecompartment"
  region                     = "us-ashburn-1"
  deployment_id              = "gateway-test"
  oci_model_id               = "example.chat-model"
}

run "placeholder_uses_owned_vault_and_encryption_key" {
  command = plan
  assert {
    condition = (
      oci_kms_vault.runtime.vault_type == "DEFAULT" &&
      oci_kms_vault.runtime.compartment_id == var.compartment_ocid &&
      oci_kms_key.runtime.compartment_id == var.compartment_ocid &&
      oci_kms_key.runtime.management_endpoint == oci_kms_vault.runtime.management_endpoint &&
      oci_kms_key.runtime.key_shape[0].algorithm == "AES" &&
      oci_kms_key.runtime.key_shape[0].length == 32 &&
      oci_kms_key.runtime.protection_mode == "HSM"
    )
    error_message = "Use an owned DEFAULT vault with an AES-256 HSM key in the requested compartment."
  }
  assert {
    condition = (
      oci_vault_secret.runtime.compartment_id == var.compartment_ocid &&
      oci_vault_secret.runtime.vault_id == oci_kms_vault.runtime.id &&
      oci_vault_secret.runtime.key_id == oci_kms_key.runtime.id &&
      oci_vault_secret.runtime.secret_content[0].content_type == "BASE64" &&
      base64decode(oci_vault_secret.runtime.secret_content[0].content) == "UNCONFIGURED" &&
      oci_vault_secret.runtime.secret_content[0].stage == "CURRENT"
    )
    error_message = "Terraform must create only a CURRENT placeholder encrypted by this vault's key."
  }
  assert {
    condition = alltrue([
      for tags in [
        oci_kms_vault.runtime.freeform_tags,
        oci_kms_key.runtime.freeform_tags,
        oci_vault_secret.runtime.freeform_tags
      ] : tags["solution"] == "oci-ai-gateway-lab" && tags["deployment_id"] == var.deployment_id
    ])
    error_message = "Every foundation resource must carry solution and deployment ownership metadata."
  }
  assert {
    condition = (
      output.runtime_vault_ocid == oci_kms_vault.runtime.id &&
      output.runtime_key_ocid == oci_kms_key.runtime.id &&
      output.runtime_secret_ocid == oci_vault_secret.runtime.id
    )
    error_message = "Handoff outputs must reference this stack's exact vault/key/secret."
  }
}

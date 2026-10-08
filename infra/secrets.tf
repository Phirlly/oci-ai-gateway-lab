resource "oci_kms_vault" "runtime" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.deployment_id}-runtime"
  vault_type     = "DEFAULT"
  freeform_tags  = local.ownership_tags

  depends_on = [data.oci_identity_region_subscriptions.tenancy]
}

resource "oci_kms_key" "runtime" {
  compartment_id      = var.compartment_ocid
  display_name        = "${var.deployment_id}-runtime"
  management_endpoint = oci_kms_vault.runtime.management_endpoint
  protection_mode     = "HSM"
  freeform_tags       = local.ownership_tags

  key_shape {
    algorithm = "AES"
    length    = 32
  }
}

resource "oci_vault_secret" "runtime" {
  compartment_id = var.compartment_ocid
  vault_id       = oci_kms_vault.runtime.id
  key_id         = oci_kms_key.runtime.id
  secret_name    = "${var.deployment_id}-runtime"
  freeform_tags  = local.ownership_tags

  secret_content {
    content_type = "BASE64"
    content      = base64encode("UNCONFIGURED")
    name         = "unconfigured"
    stage        = "CURRENT"
  }

  lifecycle {
    # Deployment workflow owns real contents and version promotion outside
    # Terraform. current_version_number is computed-only in provider 9.8.0.
    ignore_changes = [secret_content]
  }
}

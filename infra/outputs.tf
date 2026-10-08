output "home_region" {
  description = "Discovered IAM home region, independent of runtime hosting."
  value       = local.home_region
}

output "oci_model_key_ocid" {
  description = "Nonsecret model-key binding; absent before the credential handoff."
  value       = var.oci_model_key_ocid
}

output "runtime_key_ocid" {
  description = "Encryption key owned by this deployment."
  value       = oci_kms_key.runtime.id
}

output "runtime_secret_ocid" {
  description = "Runtime secret container; contents are delivered outside Terraform."
  value       = oci_vault_secret.runtime.id
}

output "runtime_vault_ocid" {
  description = "Vault owned by this deployment."
  value       = oci_kms_vault.runtime.id
}

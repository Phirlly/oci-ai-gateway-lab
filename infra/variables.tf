variable "compartment_ocid" {
  description = "Existing OC1 compartment for this deployment; tenancy root is not supported."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1\\.compartment\\.oc1\\.\\.[a-zA-Z0-9]+$", var.compartment_ocid))
    error_message = "compartment_ocid must be an OC1 compartment OCID."
  }
}

variable "deployment_id" {
  description = "Stable deployment name, unique within the tenancy: 3-40 lowercase letters, digits or hyphens."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.deployment_id))
    error_message = "deployment_id must start with a lowercase letter and contain 3-40 lowercase letters, digits or hyphens."
  }
}

variable "oci_model_id" {
  description = "Exact OCI model ID to authorize. Availability and bearer compatibility require deployment preflight."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,254}$", var.oci_model_id))
    error_message = "oci_model_id must be a nonempty model identifier containing only letters, digits, dots, underscores, colons or hyphens."
  }
}

variable "oci_model_key_ocid" {
  description = "Workflow-derived GenAI key OCID, recovered before every resumed Apply. Null only for the initial unconfigured phase."
  type        = string
  default     = null

  validation {
    condition     = var.oci_model_key_ocid == null || can(regex("^ocid1\\.generativeaiapikey\\.oc1\\.[a-z0-9-]+\\.[a-zA-Z0-9._-]+$", var.oci_model_key_ocid))
    error_message = "oci_model_key_ocid must be null or an OC1 Generative AI API-key OCID; never pass a key value."
  }
}

variable "region" {
  description = "OC1 hosting region. Must already be subscribed and READY."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]{2,}-[a-z0-9-]+-[0-9]+$", var.region))
    error_message = "region must be an OCI region name, such as us-ashburn-1."
  }
}

variable "tenancy_ocid" {
  description = "OC1 tenancy used to discover the IAM home region."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.oc1\\.\\.[a-zA-Z0-9]+$", var.tenancy_ocid))
    error_message = "tenancy_ocid must be an OC1 tenancy OCID."
  }
}

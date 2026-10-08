# Resource Manager supplies authentication. Local verification can inherit
# OCI_CONFIG_FILE_PROFILE or the default OCI profile; no credentials enter tfvars.
provider "oci" {
  region = var.region
}

provider "oci" {
  alias  = "home"
  region = local.home_region
}

data "oci_identity_region_subscriptions" "tenancy" {
  tenancy_id = var.tenancy_ocid

  lifecycle {
    postcondition {
      condition     = length([for subscription in self.region_subscriptions : subscription.region_name if subscription.is_home_region]) == 1
      error_message = "Tenancy subscriptions must identify exactly one home region."
    }
    postcondition {
      condition     = anytrue([for subscription in self.region_subscriptions : subscription.region_name == var.region && subscription.state == "READY"])
      error_message = "The hosting region must have a READY tenancy subscription."
    }
  }
}

locals {
  home_regions = [
    for subscription in data.oci_identity_region_subscriptions.tenancy.region_subscriptions :
    subscription.region_name if subscription.is_home_region
  ]
  # Invalid discovery is blocked by the data-source postcondition. The fallback
  # avoids an incidental index error obscuring that diagnostic.
  home_region = length(local.home_regions) == 1 ? local.home_regions[0] : var.region
}

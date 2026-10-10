data "oci_identity_availability_domains" "gateway" {
  compartment_id = var.compartment_ocid
  lifecycle {
    postcondition {
      condition     = length(self.availability_domains) >= var.availability_domain_number
      error_message = "The requested availability domain is absent in this region."
    }
  }
}

data "oci_core_images" "gateway" {
  compartment_id = var.compartment_ocid
  display_name   = var.image_name
  shape          = var.instance_shape
  state          = "AVAILABLE"
  lifecycle {
    postcondition {
      condition     = length(self.images) == 1
      error_message = "The exact Ubuntu image must have one AVAILABLE match for the selected shape and region."
    }
  }
}

resource "oci_core_instance" "gateway" {
  compartment_id       = var.compartment_ocid
  availability_domain  = try(data.oci_identity_availability_domains.gateway.availability_domains[var.availability_domain_number - 1].name, "unavailable")
  display_name         = "${var.deployment_id}-gateway"
  shape                = var.instance_shape
  freeform_tags        = local.ownership_tags
  preserve_boot_volume = false
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }
  source_details {
    source_type             = "image"
    source_id               = try(data.oci_core_images.gateway.images[0].id, "unavailable")
    boot_volume_size_in_gbs = tostring(var.boot_volume_size_gbs)
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.gateway.id
    assign_public_ip = "false"
    freeform_tags    = local.ownership_tags
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  metadata = { user_data = base64encode(local.cloud_init) }
  lifecycle {
    precondition {
      condition     = var.instance_memory_gbs >= var.instance_ocpus && var.instance_memory_gbs <= 64 * var.instance_ocpus
      error_message = "Memory must be between1 and64GB per OCPU within the demo limits."
    }
    precondition {
      condition     = length(base64encode(local.cloud_init)) < 32000
      error_message = "Embedded runtime exceeds OCI's user_data metadata budget."
    }
    precondition {
      condition     = anytrue([for subscription in data.oci_identity_region_subscriptions.tenancy.region_subscriptions : subscription.region_name == var.inference_region && subscription.state == "READY"])
      error_message = "The inference region must already have a READY tenancy subscription."
    }
  }
}

data "oci_core_private_ips" "gateway" {
  subnet_id  = oci_core_subnet.gateway.id
  ip_address = oci_core_instance.gateway.private_ip
  lifecycle {
    postcondition {
      condition     = length(self.private_ips) == 1 && alltrue([for ip in self.private_ips : ip.is_primary && ip.ip_address == self.ip_address])
      error_message = "Exactly one matching primary private IP is required."
    }
  }
}

resource "oci_core_public_ip" "gateway" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.deployment_id}-gateway"
  lifetime       = "RESERVED"
  private_ip_id  = try(data.oci_core_private_ips.gateway.private_ips[0].id, null)
  freeform_tags  = local.ownership_tags
}

resource "oci_identity_policy" "runtime_bundle" {
  provider       = oci.home
  compartment_id = var.compartment_ocid
  name           = "${var.deployment_id}-runtime-read"
  description    = "This instance may retrieve only its runtime secret bundle."
  freeform_tags  = local.ownership_tags
  statements = [
    "Allow any-user to read secret-bundles in compartment id ${var.compartment_ocid} where all {request.principal.type='instance', request.instance.id='${oci_core_instance.gateway.id}', target.secret.id='${oci_vault_secret.runtime.id}', request.operation='GetSecretBundle'}"
  ]
}

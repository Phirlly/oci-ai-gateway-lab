resource "oci_core_vcn" "gateway" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.deployment_id}-network"
  cidr_blocks    = ["10.42.0.0/16"]
  dns_label      = "gateway"
  freeform_tags  = local.ownership_tags
}

resource "oci_core_internet_gateway" "gateway" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.gateway.id
  display_name   = "${var.deployment_id}-internet"
  enabled        = true
  freeform_tags  = local.ownership_tags
}

resource "oci_core_route_table" "gateway" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.gateway.id
  display_name   = "${var.deployment_id}-routes"
  freeform_tags  = local.ownership_tags
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.gateway.id
  }
}

resource "oci_core_security_list" "gateway" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.gateway.id
  display_name   = "${var.deployment_id}-https"
  freeform_tags  = local.ownership_tags
  dynamic "ingress_security_rules" {
    for_each = toset([80, 443])
    content {
      protocol    = "6"
      source      = "0.0.0.0/0"
      source_type = "CIDR_BLOCK"
      stateless   = false
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
  egress_security_rules {
    protocol         = "all"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    stateless        = false
  }
}

resource "oci_core_subnet" "gateway" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.gateway.id
  cidr_block                 = "10.42.0.0/24"
  display_name               = "${var.deployment_id}-public"
  dns_label                  = "public"
  route_table_id             = oci_core_route_table.gateway.id
  security_list_ids          = [oci_core_security_list.gateway.id]
  prohibit_public_ip_on_vnic = false
  prohibit_internet_ingress  = false
  freeform_tags              = local.ownership_tags
}

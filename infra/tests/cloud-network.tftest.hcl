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
run "owned_network_exposes_only_http_and_https" {
  command = plan
  assert {
    condition     = toset([for rule in oci_core_security_list.gateway.ingress_security_rules : rule.tcp_options[0].min]) == toset([80, 443]) && alltrue([for rule in oci_core_security_list.gateway.ingress_security_rules : rule.protocol == "6" && rule.tcp_options[0].min == rule.tcp_options[0].max && rule.source == "0.0.0.0/0"])
    error_message = "Only TCP80/443 may be granted inbound."
  }
  assert {
    condition     = oci_core_subnet.gateway.security_list_ids == toset([oci_core_security_list.gateway.id]) && oci_core_subnet.gateway.route_table_id == oci_core_route_table.gateway.id
    error_message = "The subnet must use its owned security list and route table."
  }
  assert {
    condition     = length(oci_core_security_list.gateway.egress_security_rules) == 1 && one(oci_core_security_list.gateway.egress_security_rules).protocol == "all" && one(oci_core_security_list.gateway.egress_security_rules).destination == "0.0.0.0/0"
    error_message = "The model gateway requires outbound provider connectivity."
  }
}

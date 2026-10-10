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
run "exact_image_cpu_vm_and_owned_public_address" {
  command = plan
  assert {
    condition     = oci_core_instance.gateway.source_details[0].source_id == "ocid1.image.oc1.iad.synthetic" && oci_core_instance.gateway.shape == "VM.Standard.E4.Flex" && oci_core_instance.gateway.shape_config[0].memory_in_gbs == 8
    error_message = "The VM must use the selected exact image and configured CPU shape."
  }
  assert {
    condition     = oci_core_instance.gateway.create_vnic_details[0].assign_public_ip == "false" && oci_core_public_ip.gateway.lifetime == "RESERVED" && data.oci_core_private_ips.gateway.ip_address == oci_core_instance.gateway.private_ip && data.oci_core_private_ips.gateway.subnet_id == oci_core_subnet.gateway.id
    error_message = "Manage a reserved public IP and discover the VM address in its owned subnet."
  }
  assert {
    condition     = oci_core_instance.gateway.instance_options[0].are_legacy_imds_endpoints_disabled && !oci_core_instance.gateway.preserve_boot_volume && !contains(keys(oci_core_instance.gateway.metadata), "ssh_authorized_keys")
    error_message = "Require IMDSv2, remove the owned boot volume, and do not install SSH keys."
  }
}
run "missing_exact_image_fails" {
  command = plan
  override_data {
    target = data.oci_core_images.gateway
    values = { images = [] }
  }
  expect_failures = [data.oci_core_images.gateway]
}
run "unsupported_memory_ratio_fails" {
  command = plan
  variables { instance_memory_gbs = 128 }
  expect_failures = [oci_core_instance.gateway]
}

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

run "reject_non_oc1_tenancy" {
  command = plan
  variables {
    tenancy_ocid = "ocid1.tenancy.oc2..aaaaaaaaexampletenancy"
  }
  expect_failures = [var.tenancy_ocid]
}

run "reject_tenancy_as_target_compartment" {
  command = plan
  variables {
    compartment_ocid = "ocid1.tenancy.oc1..aaaaaaaaexampletenancy"
  }
  expect_failures = [var.compartment_ocid]
}

run "reject_unsafe_compartment" {
  command = plan
  variables {
    compartment_ocid = "ocid1.compartment.oc1..example where any {}"
  }
  expect_failures = [var.compartment_ocid]
}

run "reject_invalid_region" {
  command = plan
  variables {
    region = "../us-ashburn-1"
  }
  expect_failures = [var.region]
}

run "reject_invalid_deployment_name" {
  command = plan
  variables {
    deployment_id = "Gateway with spaces"
  }
  expect_failures = [var.deployment_id]
}

run "reject_policy_injection_in_model" {
  command = plan
  variables {
    oci_model_id = "example', request.principal.type='user"
  }
  expect_failures = [var.oci_model_id]
}

run "reject_empty_model" {
  command = plan
  variables {
    oci_model_id = ""
  }
  expect_failures = [var.oci_model_id]
}

run "reject_wrong_kind_of_key" {
  command = plan
  variables {
    oci_model_key_ocid = "ocid1.key.oc1.iad.aaaaaaaaexamplekey"
  }
  expect_failures = [var.oci_model_key_ocid]
}

run "reject_non_oc1_model_key" {
  command = plan
  variables {
    oci_model_key_ocid = "ocid1.generativeaiapikey.oc2.iad.aaaaaaaaexamplekey"
  }
  expect_failures = [var.oci_model_key_ocid]
}

run "reject_empty_binding_instead_of_null" {
  command = plan
  variables {
    oci_model_key_ocid = ""
  }
  expect_failures = [var.oci_model_key_ocid]
}

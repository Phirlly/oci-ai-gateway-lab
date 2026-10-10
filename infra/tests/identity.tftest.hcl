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

run "initial_phase_has_no_inference_grant" {
  command = plan
  assert {
    condition     = length(oci_identity_policy.model_chat) == 0
    error_message = "A deployment without a generated model key must grant no inference access."
  }
}

run "bound_key_gets_only_scoped_chat_grant" {
  command = plan
  variables {
    # Inference region may differ from both hosting and home region.
    oci_model_key_ocid = "ocid1.generativeaiapikey.oc1.ord.aaaaaaaaexamplekey"
  }
  assert {
    condition     = length(oci_identity_policy.model_chat) == 1
    error_message = "A generated key must have exactly one model policy."
  }
  assert {
    condition = (
      oci_identity_policy.model_chat[0].compartment_id == var.compartment_ocid &&
      oci_identity_policy.model_chat[0].statements == tolist([
        "Allow any-user to use generative-ai-chat in compartment id ${var.compartment_ocid} where all {request.principal.type='generativeaiapikey', request.principal.id='${var.oci_model_key_ocid}', target.model.id='${var.oci_model_id}'}"
      ])
    )
    error_message = "Grant must be compartment-attached and restrict principal type, exact key, model and chat operation."
  }
  assert {
    condition     = output.oci_model_key_ocid == var.oci_model_key_ocid
    error_message = "Handoff output must identify the bound key."
  }
}

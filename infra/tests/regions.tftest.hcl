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
  tenancy_ocid     = "ocid1.tenancy.oc1..aaaaaaaaexampletenancy"
  compartment_ocid = "ocid1.compartment.oc1..aaaaaaaaexamplecompartment"
  region           = "us-ashburn-1"
  deployment_id    = "gateway-test"
  oci_model_id     = "example.chat-model"
}

run "discover_home_independently_of_hosting_region" {
  command = plan
  assert {
    condition     = output.home_region == "us-phoenix-1"
    error_message = "IAM must use the discovered home region even when hosting in Ashburn."
  }
}

run "reject_missing_home_region" {
  command = plan
  override_data {
    target = data.oci_identity_region_subscriptions.tenancy
    values = {
      region_subscriptions = [{
        region_name    = "us-ashburn-1", region_key = "IAD",
        is_home_region = false, state = "READY"
      }]
    }
  }
  expect_failures = [data.oci_identity_region_subscriptions.tenancy]
}

run "reject_ambiguous_home_region" {
  command = plan
  override_data {
    target = data.oci_identity_region_subscriptions.tenancy
    values = {
      region_subscriptions = [
        {
          region_name    = "us-ashburn-1", region_key = "IAD",
          is_home_region = true, state = "READY"
        },
        {
          region_name    = "us-phoenix-1", region_key = "PHX",
          is_home_region = true, state = "READY"
        }
      ]
    }
  }
  expect_failures = [data.oci_identity_region_subscriptions.tenancy]
}

run "reject_missing_hosting_subscription" {
  command = plan
  variables {
    region = "eu-frankfurt-1"
  }
  expect_failures = [data.oci_identity_region_subscriptions.tenancy]
}

run "reject_hosting_subscription_not_ready" {
  command = plan
  override_data {
    target = data.oci_identity_region_subscriptions.tenancy
    values = {
      region_subscriptions = [
        {
          region_name    = "us-phoenix-1", region_key = "PHX",
          is_home_region = true, state = "READY"
        },
        {
          region_name    = "us-ashburn-1", region_key = "IAD",
          is_home_region = false, state = "IN_PROGRESS"
        }
      ]
    }
  }
  expect_failures = [data.oci_identity_region_subscriptions.tenancy]
}

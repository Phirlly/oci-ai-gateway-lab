locals {
  runtime_assets = [
    "runtime/__init__.py", "runtime/bootstrap.py", "runtime/cloud_credentials.py",
    "runtime/gateway_entrypoint.py", "runtime/gateway_http.py", "runtime/host_commands.py",
    "runtime/host_firewall.py", "runtime/password_policy.py", "runtime/presenter.py",
    "runtime/presenter_api.py", "runtime/presenter_state.py", "runtime/runtime_bundle.py",
    "runtime/runtime_files.py", "runtime/compose.cloud.yaml", "runtime/docker-daemon.json",
    "runtime/systemd/docker-guard.conf", "runtime/systemd/oci-ai-gateway-bootstrap.service",
    "runtime/systemd/oci-ai-gateway-bootstrap.timer",
  ]
  runtime_settings = {
    schema_version    = 1
    deployment_id     = var.deployment_id
    tenancy_ocid      = var.tenancy_ocid
    compartment_ocid  = var.compartment_ocid
    secret_ocid       = oci_vault_secret.runtime.id
    region            = var.region
    inference_region  = var.inference_region
    model_id          = var.oci_model_id
    presenter_email   = var.presenter_email
    external_provider = var.external_provider
    external_model_id = var.external_model_id
  }
  cloud_init = "#cloud-config\n${yamlencode({
    write_files = [
      {
        path        = "/opt/oci-ai-gateway/assets.json"
        owner       = "root:root"
        permissions = "0600"
        encoding    = "gz+b64"
        content     = base64gzip(jsonencode({ for name in local.runtime_assets : name => file("${path.module}/../${name}") }))
      },
      {
        path        = "/opt/oci-ai-gateway/install_assets.py"
        owner       = "root:root"
        permissions = "0600"
        content     = file("${path.module}/../runtime/install_assets.py")
      },
      {
        path        = "/etc/oci-ai-gateway.json"
        owner       = "root:root"
        permissions = "0600"
        content     = jsonencode(local.runtime_settings)
      },
    ]
    runcmd = [
      "set -eu",
      ["/usr/bin/python3", "/opt/oci-ai-gateway/install_assets.py"],
      ["/usr/bin/systemctl", "daemon-reload"],
      ["/usr/bin/systemctl", "enable", "--now", "oci-ai-gateway-bootstrap.timer"],
    ]
  })}"
}

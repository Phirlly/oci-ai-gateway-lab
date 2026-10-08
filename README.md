# OCI AI Gateway and Model Choice Lab

Compare an OCI-managed model and an external model through an OCI-hosted LiteLLM
gateway and its bundled Compare UI.

**Under development.** End-to-end OCI deployment is not available yet. Current
code provides local verification with mocked responses, a Terraform foundation
and deployment components.

## Planned Deployment and Demo

GitHub Actions will run Terraform through OCI Resource Manager and deploy
LiteLLM, PostgreSQL and Caddy on an OCI CPU VM.

1. Configure an owned or team repository once: one settings file plus GitHub
   Secrets for OCI access, the external-provider key and presenter password.
2. Choose **Deploy** to provision resources, configure both models, create
   presenter access and run bundled samples.
3. Open the reported Compare URL, log in with the reported username and configured
   password, select both models and submit the supplied sample.
4. Reuse the deployment with **Status** and **Verify samples**; choose **Remove**
   to clean up through OCI, even if the VM is unavailable.

**Ready** requires successful login, both real model routes and HTTPS/sample
verification. OCI permissions and access to the selected models are prerequisites.

## Configuration

Copy [deployment.tfvars.json.example](deployment.tfvars.json.example) to
`deployment.tfvars.json` and replace its placeholders. The current example covers
only the Terraform foundation: tenancy, compartment, hosting region, deployment
name and OCI model. Keep credentials and local profile names outside this file.
Actual settings files are excluded from Git.

## Local Verification

Requires Linux or macOS, Python 3.12, Docker CLI with Compose and a running local
container engine using a Unix-socket Docker context. No OCI account, provider
keys or additional Python packages are needed.

From the repository root:

```sh
python3.12 -m tests.contracts.runtime
```

The runner checks the pinned runtime using mock responses, then removes its
containers, networks, volumes and temporary credentials.
See [local verification and troubleshooting](runtime/LOCAL_TESTING.md) for
Podman, image-pull issues and interrupted cleanup.

License: [MIT](LICENSE).

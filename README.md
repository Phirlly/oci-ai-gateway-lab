# OCI AI Gateway and Model Choice Lab

A reusable OCI-hosted demonstration of access to OCI-managed and external AI models.

**Status: local runtime contracts and Terraform foundation.** Full OCI deployment
is still being implemented. The local profile verifies pinned
LiteLLM/PostgreSQL/Caddy using synthetic accounts and mocked completions.

## Terraform Foundation

The single [infra/](infra/) root currently defines a Vault, AES-256 encryption
key, placeholder runtime secret and conditional model-access policy. IAM uses
the discovered tenancy home region; hosting uses the configured region.

[deployment.tfvars.json.example](deployment.tfvars.json.example) contains the
nonsecret settings implemented so far. Copy it to the ignored
`deployment.tfvars.json` and replace its placeholders:

| Setting | Value |
| --- | --- |
| `tenancy_ocid` | Existing OC1 tenancy |
| `compartment_ocid` | Existing deployment compartment |
| `region` | Subscribed hosting region; example uses Ashburn |
| `deployment_id` | Stable name unique within the tenancy |
| `oci_model_id` | Exact OCI model identifier, verified for the inference region |

Credentials and profile names do not belong in this file. Resource Manager
supplies Terraform authentication; local provider configuration can select
`OCI_CONFIG_FILE_PROFILE` or use the default profile. The generated model-key
OCID is a workflow-derived input, recovered before each resumed Apply.

Terraform creates only `UNCONFIGURED` secret content. The planned deployment
workflow delivers credentials separately and supplies the exact key binding
before inference access is granted. The existing deployment identity needs
region-subscription read access and authority over Vaults, keys, secrets and
compartment policies. The stack cannot grant its own deployment permissions.

Verify this foundation with Terraform **1.16.4**; no OCI credentials are needed:

```sh
terraform -chdir=infra init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra validate
terraform -chdir=infra test
```

Tests are separated into inputs, regions, secrets and identity under
`infra/tests/`. All runs use mocked providers and plan operations. Deployment
files also pass initialization and validation with Terraform **1.5.7**, the
documented Resource Manager CLI version; modern mock tests run separately.

VM/network resources, credential delivery, GitHub deployment, sample automation
and cloud cleanup are not implemented yet. These checks do not prove a live
deployment, effective permissions or preservation of secret versions on reapply.

## Run the Local Contracts

Prerequisites: Linux or macOS, Python 3.12, Docker CLI with Compose, and a running
local container engine exposed through a Unix-socket Docker context. No Python
packages, OCI account or provider API keys are needed.

From this repository's root:

```sh
python3.12 -m tests.contracts.runtime
```

For a Podman machine exposed through the Docker `podman` context:

```sh
GATEWAY_TEST_DOCKER_CONTEXT=podman python3.12 -m tests.contracts.runtime
```

The runner pulls pinned images, generates disposable credentials, starts Caddy
on loopback with an isolated gateway/database, runs the tests and removes its
containers, networks, volumes and temporary inputs. It leaves the container engine running.
The first image download can take several minutes.

Run a focused suite with `--suite configuration`, `--suite health`,
`--suite onboarding`, `--suite access` or `--suite persistence`.
Configuration checks run without starting containers. Suites remain separated
under `tests/contracts/runtime/` by what they prove.

If Docker Hub pulls fail with a certificate-trust error, Docker's official ECR
Public mirror can supply the same pinned images with TLS verification enabled:

```sh
GATEWAY_TEST_DOCKER_CONTEXT=podman \
GATEWAY_TEST_POSTGRES_REGISTRY=public.ecr.aws/docker/library \
GATEWAY_TEST_CADDY_REGISTRY=public.ecr.aws/docker/library \
python3.12 -m tests.contracts.runtime
```

LiteLLM still downloads from GHCR. If corporate HTTPS inspection affects that
registry too, have the approved corporate CA configured for the container engine.
Do not disable TLS verification. A cleanup failure reports the owned project
and retained protected-input directory for recovery; do not run a global prune.

## Recover an Interrupted Cleanup

From the repository root, set the exact project and input directory reported by
the failure, and the Docker context used for that run:

```sh
test_context='podman'
test_project='gateway-contract-REPLACE'
test_inputs='/absolute/path/reported/by/the/runner'
```

Supply the retained file paths and remove that project's containers and storage:

```sh
GATEWAY_CONFIG_FILE="$PWD/tests/contracts/runtime/fixtures/gateway.yaml" \
GATEWAY_ENV_FILE="$test_inputs/gateway.env" \
DATABASE_PASSWORD_FILE="$test_inputs/database-password" \
docker --context "$test_context" compose --project-directory "$PWD" \
  -f runtime/compose.local.yaml -p "$test_project" down --volumes --timeout 10
```

Verify removal, including stopped containers:

```sh
docker --context "$test_context" container ls --all --quiet --filter "label=com.docker.compose.project=$test_project"
docker --context "$test_context" network ls --quiet --filter "label=com.docker.compose.project=$test_project"
docker --context "$test_context" volume ls --quiet --filter "label=com.docker.compose.project=$test_project"
```

Only after **all three commands succeed with empty output**, remove the exact
reported input directory inside this repository's `.tmp/`:

```sh
rm -r -- "$test_inputs"
```

If any command fails or lists remaining resources, retain the inputs and retry
with the same context/project. These commands leave other projects and the
container engine running.

## What This Verifies

- Required configuration and loopback/private-network boundaries.
- Database readiness and availability of the bundled UI HTML page.
- Account invitation, activation, login and rejection paths.
- Session model access, mocked responses and complete streaming.
- Account persistence across gateway restart.

Real OCI/external models, automated cloud setup, public HTTPS/browser access and
cloud cleanup still require implementation and validation. The local Compose
profile and mocked test configuration are for verification, not customer hosting.

License: [MIT](LICENSE).

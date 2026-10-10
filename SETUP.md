# Setup

Development preview: live GitHub deployment acceptance is pending. Budget for
Compute, storage, Vault and model usage while testing.

## Prerequisites

- An owned GitHub repository with Actions enabled. Fork this repository or reuse
  a configured team repository. Deploy only reviewed code.
- An OCI OC1 tenancy, existing compartment and subscribed hosting/inference
  regions. The selected image, shape and model must be available with capacity.
- An OCI signing identity permitted to manage Resource Manager, Compute/network,
  Vault/keys/secrets and Generative AI API keys in that compartment; read regional
  metadata; and create the package's IAM policies in the tenancy home region.
  Your administrator must grant these permissions before deployment.
  [Resource Manager permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/resourcemanagerpolicyreference.htm)
  and [model-key permissions](https://docs.oracle.com/en-us/iaas/Content/generative-ai/api-key-permissions.htm)
  describe the service requirements.
- An Anthropic account/key with access to the configured external model.

The workflow creates the VM/network, reserved public IP, Vault/secret and model
key. No pre-existing hostname, DNS record or Vault is required. Public ports 80/443
support HTTPS and certificate issuance; gateway/database ports stay private.

## Configure once

1. Copy [deployment.tfvars.json.example](deployment.tfvars.json.example) to
   `deployment.tfvars.json`. Replace tenancy/compartment placeholders, choose a
   unique deployment ID and set the presenter email. Review both model IDs,
   regions, exact image build and VM size. Keep this local file out of Git.
2. Create the GitHub environment **gateway** under **Settings → Environments**.
   Restrict it to your reviewed deployment branch. This repository uses `dev`.
3. Add environment variable **DEPLOYMENT_CONFIG** containing the complete JSON
   file. To upload the file unchanged using GitHub CLI:

   ```sh
   gh variable set DEPLOYMENT_CONFIG --env gateway < deployment.tfvars.json
   ```

4. Add these **environment secrets**:

   | Name | Value |
   |---|---|
   | `OCI_USER_OCID` | OCI signing user's OCID |
   | `OCI_FINGERPRINT` | Registered signing key fingerprint |
   | `OCI_PRIVATE_KEY` | Matching PEM private key: unencrypted PKCS8/RSA or encrypted PKCS8 |
   | `OCI_PRIVATE_KEY_PASSPHRASE` | Passphrase for encrypted PKCS8, if used |
   | `ANTHROPIC_API_KEY` | Anthropic API key |
   | `DEMO_PASSWORD` | Presenter password: 12–256 characters including uppercase, lowercase, number and symbol |

`DEMO_PASSWORD` is the browser login password. Never place passwords/API keys in
the settings JSON. GitHub's built-in token records recovery history; no personal
GitHub token is required by the workflow. Local OCI profile names, including
`DEFAULT`, are not deployment settings and are not used on GitHub runners.
Configure only **gateway**. The workflow maintains **gateway-submissions**
automatically for nonsecret recovery records; it needs no secrets or setup.

## Run the demo

Open **Actions → Gateway demo → Run workflow** on the permitted branch. Choose
**Deploy**. It submits Terraform, delivers runtime credentials through Vault,
creates restricted presenter access and runs eight bounded sample requests.

The run summary reports status, Compare URL, username and sample results. Open
the URL only after **Ready**, sign in with `DEMO_PASSWORD`, select `oci-managed`
and `external-anthropic`, then use [the presenter script](demo/PROMPT.md).

**Status** makes no model calls. **Verify samples** repeats the eight requests
using the current presenter password. A failed check reports not ready; it does
not silently retry model calls. Inspect the workflow and Resource Manager job
status before rerunning the same action after an interruption.
For HTTP429, sample results include a recognized error type and bounded numeric
retry guidance when available. These diagnostics omit raw errors and do not
automatically identify the cause or retry the request.

Vault reads wait briefly for new versions and in-progress updates. A confirmed
ETag rejection of credential staging permits up to three attempts, each after
ownership and saved-state checks. Uncertain writes and model-key creation are
not replayed. If credential verification still fails,
retain the saved state and reconcile it before another Deploy. Fresh-creation
handoff errors distinguish intent verification from failures after model-key creation.
Failed runs log any verified OCI HTTP status and recognized service error code;
request contents and detailed error payloads remain suppressed.

## Reuse and adapt

- Reuse the same settings, repository and environment for the same deployment.
  Its original package/settings and credentials are preserved on reruns.
- To change regions, models, image, size or presenter identity, remove the old
  deployment and use a new deployment ID. Do not edit recovery history or stack
  variables manually. Model credentials expire after `model_key_ttl_days`; create
  a new deployment for a later demo beyond that window.
- If the presenter changes their password, update `DEMO_PASSWORD` for verification.
  Deploy does not reset an initialized account.
- The supported routes are OCI's OpenAI-compatible bearer endpoint and Anthropic's
  native adapter. An `OPENAI_API_KEY` secret alone does not add an OpenAI route.
  Changing providers requires a reviewed adapter/configuration change and tests.
- Sample requests and expected categories are separate files under `demo/`.
  Add synthetic workloads there; do not submit customer data for this demo.

## Remove

Choose **Remove** with the same configuration and OCI signing identity. Cleanup
uses OCI APIs and Resource Manager, so it works when the VM is stopped or
unreachable. Provider keys and presenter login are not required.

Removal deletes owned model keys and destroys managed infrastructure. Resource
Manager stack/state, GitHub recovery records and scheduled Vault/secret deletion
may remain. The supplied compartment, OCI identity and Anthropic account/key are
preserved. Keep recovery records until cleanup is confirmed. If deletion evidence
is ambiguous after an interruption, automation stops for reconciliation instead
of reporting success.
Resume interrupted removal with the current controller; do not downgrade it
after cleanup has started.

This single-VM demonstration does not provide high availability, automated
credential rotation or production backup/restore.

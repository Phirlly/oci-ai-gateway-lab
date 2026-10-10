# OCI AI Gateway

Compare an OCI-managed model and Anthropic through LiteLLM Compare, hosted on
OCI. Terraform runs through OCI Resource Manager; a CPU VM runs the pinned
LiteLLM, PostgreSQL and Caddy images.

**Development preview.** The complete GitHub deployment is pending live acceptance.

## Deploy and demonstrate

1. Follow [setup](SETUP.md) once: one settings file and GitHub environment secrets.
2. In **Actions → Gateway demo**, choose **Deploy**.
3. Open the reported Compare URL and sign in with the reported username and your
   configured password. Select both models and run the [sample](demo/PROMPT.md).

| Workflow action | Result |
|---|---|
| Deploy | Provision resources, configure models and presenter, run bundled samples |
| Status | Inspect infrastructure and health without model calls |
| Verify samples | Check login, access, both model routes and streaming |
| Remove | Delete owned model keys and infrastructure, without needing a working VM |

**Ready** requires trusted HTTPS, presenter login and successful samples through
both real model routes. Reuse the same deployment for another demonstration.
OCI supplies hosting, networking, secret delivery, resource automation and managed
inference; Anthropic supplies the external route.

See [configuration and cleanup](SETUP.md) and
[local verification](runtime/LOCAL_TESTING.md). License: [MIT](LICENSE).

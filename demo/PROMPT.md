# Presenter script

1. Open the workflow's Compare URL and sign in with its username and your
   `DEMO_PASSWORD`.
2. Select `oci-managed` and `external-anthropic` in LiteLLM Compare.
3. Submit:

   > Classify this support request as BILLING, ACCESS or TECHNICAL. Reply with
   > exactly one category: My invoice contains the same charge twice.

4. Compare the responses and streaming behavior. Both should return **BILLING**.
   Explain that the same OCI-hosted gateway routes one request to OCI-managed
   inference and the other to Anthropic.
5. Use **Verify samples** to repeat the bundled classifications and streaming
   checks. Its run summary records outcomes and elapsed time; unknown cost is
   not presented as a measured value.

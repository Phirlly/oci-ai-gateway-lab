resource "oci_identity_policy" "model_chat" {
  count    = var.oci_model_key_ocid == null ? 0 : 1
  provider = oci.home

  compartment_id = var.compartment_ocid
  name           = "${var.deployment_id}-model-chat"
  description    = "Chat access for this deployment's exact GenAI key and model."
  freeform_tags  = local.ownership_tags

  statements = [
    "Allow any-user to use generative-ai-chat in compartment id ${var.compartment_ocid} where all {request.principal.type='generativeaiapikey', request.principal.id='${var.oci_model_key_ocid}', target.model.id='${var.oci_model_id}'}"
  ]
}

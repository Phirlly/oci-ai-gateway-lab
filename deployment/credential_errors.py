"""Safe failure categories for credential delivery; never attach raw output."""


class DeliveryError(RuntimeError):
    """Stop delivery and retain the existing records for reconciliation."""


class CloudReadError(DeliveryError):
    """A cloud read could not be verified."""


class VaultReadError(CloudReadError):
    """A Vault read could not be verified."""


class MutationUncertain(DeliveryError):
    """The request may have changed remote state; reconcile before another mutation."""

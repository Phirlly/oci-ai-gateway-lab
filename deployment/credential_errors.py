"""Safe failure categories for credential delivery; never attach raw output."""


class DeliveryError(RuntimeError):
    """Stop delivery and retain the existing records for reconciliation."""


class VaultReadError(DeliveryError):
    """A Vault read could not be verified."""


class MutationUncertain(DeliveryError):
    """The request may have changed Vault; reconcile before another mutation."""

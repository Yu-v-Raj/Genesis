"""Storage failure categories shared by Core persistence adapters."""


class PersistenceError(Exception):
    """Durable storage could not complete an operation; the message is safe to show users."""


class PersistenceConflictError(PersistenceError):
    """A concurrent change was detected, so this write was rejected rather than overwriting it."""

class InvalidConstraints(ValueError):
    """Raises when a constraint doesn't exist"""


class InvalidWindowBounds(InvalidConstraints):
    """Raises when window bounds are too restrictive"""


class ConstraintKeyError(KeyError):
    """Raises when a key path doesn't exist"""


class MissingRelease(Exception):
    """Raised when a required GitHub release asset is missing."""

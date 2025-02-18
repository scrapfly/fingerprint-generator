class InvalidConstraints(ValueError):
    """Raises when a constraint doesn't exist"""


class InvalidScreenConstraints(InvalidConstraints):
    """Raises when screen constraints are impossible"""


class ConstraintKeyError(KeyError):
    """Raises when a key path doesn't exist"""


class MissingRelease(Exception):
    """Raised when a required GitHub release asset is missing."""

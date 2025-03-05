class NetworkError(ValueError):
    """Error with the network"""


class InvalidConstraints(NetworkError):
    """Raises when a constraint isn't possible"""


class InvalidNode(NetworkError):
    """Raises when a node doesn't exist"""


class InvalidWindowBounds(InvalidConstraints):
    """Raises when window bounds are too restrictive"""


class NodePathError(InvalidNode):
    """Raises when a key path doesn't exist"""


class MissingRelease(Exception):
    """Raised when a required GitHub release asset is missing."""

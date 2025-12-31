class PytronError(Exception):
    """Base class for all Pytron exceptions."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class ConfigError(PytronError):
    """Raised when there is an error loading or parsing configuration."""

    pass


class PlatformError(PytronError):
    """Raised when there is a platform-specific issue (e.g. unsupported OS)."""

    pass


class ResourceNotFoundError(PytronError, FileNotFoundError):
    """Raised when a required resource (HTML file, icon, etc.) is not found."""

    pass


class BridgeError(PytronError):
    """Raised when there is an error in the Python-JS bridge communication."""

    pass


class DependencyError(PytronError):
    """Raised when a required dependency is missing."""

    pass

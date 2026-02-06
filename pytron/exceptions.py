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


class BuildError(PytronError):
    """Raised when the build pipeline fails."""

    pass


class ModuleError(BuildError):
    """Raised when a specific build module fails."""

    def __init__(self, message, module_name=None, code=None):
        super().__init__(message, code)
        self.module_name = module_name

    def __str__(self):
        if self.module_name:
            return f"[{self.module_name}] {super().__str__()}"
        return super().__str__()


class EngineError(PytronError):
    """Base class for engine-related errors."""

    pass


class ForgeError(EngineError):
    """Raised when an engine forge/installation process fails."""

    pass


class NativeEngineError(EngineError):
    """Raised when the native engine (pytron_native) cannot be loaded or fails."""

    pass


class RoutingError(PytronError):
    """Raised when a deep link route cannot be matched or a handler fails."""

    pass


class StateError(PytronError):
    """Raised when there is an error in reactive state operations."""

    pass


class UpdateError(PytronError):
    """Raised when an auto-update process fails."""

    pass


class PluginError(PytronError):
    """Base class for plugin-related errors."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load."""

    pass


class PluginDependencyError(PluginError):
    """Raised when a plugin's dependencies cannot be resolved."""

    pass


class ShortcutError(PytronError):
    """Base class for shortcut-related errors."""

    pass


class ShortcutRegistrationError(ShortcutError):
    """Raised when a global shortcut cannot be registered (e.g. conflict)."""

    pass


class TrayError(PytronError):
    """Raised when the system tray icon fails to initialize or update."""

    pass

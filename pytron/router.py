import re
import urllib.parse
import inspect
import logging
from .exceptions import RoutingError


class DeepLink:
    """
    Represents a parsed Deep Link.
    """

    def __init__(self, raw_url: str, params: dict = None):
        self.raw_url = raw_url
        self.parsed = urllib.parse.urlparse(raw_url)
        self.scheme = self.parsed.scheme
        self.netloc = self.parsed.netloc
        self.path = self.parsed.path

        # Parse query params (returns dict of lists)
        self.query = urllib.parse.parse_qs(self.parsed.query)

        # Flatten query params if single value (optional utility)
        self.args = {k: v[0] if len(v) == 1 else v for k, v in self.query.items()}

        # Path parameters extracted from route
        self.params = params or {}

    def __repr__(self):
        return f"<DeepLink scheme='{self.scheme}' path='{self.netloc}{self.path}' params={self.params} args={self.args}>"


class Router:
    """
    Handles matching Deep Links to registered callback functions.
    """

    def __init__(self, logger=None):
        self.routes = []
        self._default_handler = None
        self.logger = logger or logging.getLogger("Pytron.Router")

    def add_route(self, pattern: str, func):
        """
        Registers a route pattern.
        """
        clean_pattern = pattern.strip("/")

        # Check for duplicates
        for route in self.routes:
            if route["pattern"] == clean_pattern:
                raise RoutingError(f"Route pattern '{clean_pattern}' is already registered.")

        # 2. Convert {param} to Regex Group (?P<param>[^/]+)
        # Escape special regex chars but leave our braces
        regex_pattern = re.escape(clean_pattern)

        # Replace escaped braces \{param\} back to capture groups
        # We manually build the regex: replace \{([^}]+)\} with (?P<\1>[^/]+)
        # Note: re.escape escapes {, }, so we look for \\{ and \\}
        regex_pattern = re.sub(
            r"\\{([a-zA-Z0-9_]+)\\}", r"(?P<\1>[^/]+)", regex_pattern
        )

        # Anchor start/end
        regex_pattern = f"^{regex_pattern}$"

        self.routes.append(
            {"pattern": clean_pattern, "regex": re.compile(regex_pattern), "func": func}
        )
        self.logger.debug(f"Registered deep link route: {clean_pattern}")

    def route(self, pattern: str):
        """
        Decorator to register a route.
        """

        def decorator(func):
            self.add_route(pattern, func)
            return func

        return decorator

    def set_default_handler(self, func):
        self._default_handler = func

    def dispatch(self, raw_url: str):
        """
        Parses the URL and calls the matching handler.
        """
        if not raw_url:
            return

        try:
            parsed = urllib.parse.urlparse(raw_url)
            # Reconstruct the "routable path": netloc + path
            # e.g. myapp://user/1 -> netloc="user", path="/1" -> "user/1"
            # e.g. myapp://home -> netloc="home", path="" -> "home"
            routable_path = f"{parsed.netloc}{parsed.path}".strip("/")

            matched = False
            for route in self.routes:
                match = route["regex"].match(routable_path)
                if match:
                    params = match.groupdict()
                    link = DeepLink(raw_url, params)
                    self._invoke_handler(route["func"], link)
                    matched = True
                    break

            if not matched:
                self.logger.debug(f"No route matched for: {routable_path}")
                if self._default_handler:
                    link = DeepLink(raw_url)
                    self._invoke_handler(self._default_handler, link)

        except Exception as e:
            self.logger.error(f"Error dispatching deep link '{raw_url}': {e}")

    def _invoke_handler(self, func, link):
        """
        Invokes the handler, injecting arguments if needed.
        """
        try:
            sig = inspect.signature(func)
            kwargs = {}

            # 1. Check if handler wants the full 'link' object
            if "link" in sig.parameters:
                kwargs["link"] = link

            # 2. Inject path params if they match argument names
            for name, value in link.params.items():
                if name in sig.parameters:
                    kwargs[name] = value

            # 3. Inject query args if they match argument names
            for name, value in link.args.items():
                if name in sig.parameters:
                    kwargs[name] = value

            # Invoke
            func(**kwargs)

        except Exception as e:
            raise RoutingError(
                f"Handler '{func.__name__}' failed for deep link '{link.raw_url}': {e}"
            ) from e
